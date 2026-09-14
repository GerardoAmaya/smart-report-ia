"""Trabajador que copia las fotos a almacenamiento propio.

La cola vive en Postgres, como decidio PLAN.md. Y la cola es la propia tabla de
fotos: el trabajo *es* la fila. Una tabla generica de trabajos seria
infraestructura para un segundo tipo de trabajo que todavia no existe.

Corre en su propio contenedor y no dentro de la API. Adentro, una descarga
trabada ocuparia un hilo web, y no se podria reiniciar uno sin el otro.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app import classify_worker, images, logging_setup, storage
from app.channels import get_channel
from app.config import settings
from app.db import SessionLocal
from app.models import ReportPhoto

log = logging.getLogger("smart_report.worker")


# Fallos que no mejoran reintentando: el archivo no es una imagen, o es mas
# grande de lo que aceptamos. Reintentar eso es gastar ancho de banda para
# llegar a la misma conclusion cinco veces.
class FalloPermanente(Exception):
    pass


def reclaim_stale(session: Session) -> int:
    """Devuelve a la cola lo que quedo tomado por un trabajador muerto.

    Sin esto, un contenedor que se cae a mitad de una descarga deja esas filas
    en processing para siempre, y la cola baja sola sin que nadie lo note.
    """
    corte = datetime.now(UTC) - timedelta(seconds=settings.worker_stale_lock_seconds)
    resultado = session.execute(
        update(ReportPhoto)
        .where(ReportPhoto.status == "processing", ReportPhoto.locked_at < corte)
        .values(status="pending", locked_at=None)
    )
    return resultado.rowcount or 0


def claim(session: Session, limite: int) -> list[ReportPhoto]:
    """Toma hasta `limite` fotos pendientes.

    SKIP LOCKED es lo que permite varios trabajadores sin coordinarlos: el que
    llega segundo salta las filas que el primero ya tiene y agarra otras, en vez
    de esperar a que suelte.

    Se marca processing y se confirma antes de descargar nada. Mantener la
    transaccion abierta durante la descarga tendria la fila bloqueada varios
    segundos, y una transaccion larga en Postgres estorba mucho mas que a esta
    tabla.
    """
    ahora = datetime.now(UTC)
    filas = (
        session.execute(
            select(ReportPhoto)
            .where(
                ReportPhoto.status == "pending",
                (ReportPhoto.next_attempt_at.is_(None)) | (ReportPhoto.next_attempt_at <= ahora),
            )
            .order_by(ReportPhoto.next_attempt_at.nulls_first(), ReportPhoto.created_at)
            .limit(limite)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )

    for foto in filas:
        foto.status = "processing"
        foto.locked_at = ahora
    session.commit()
    return filas


def process_one(session: Session, foto: ReportPhoto) -> None:
    """Descarga, valida, sube el original y la miniatura."""
    canal = get_channel(foto.channel)

    # Se comprueba contra lo declarado antes de pedir nada: bajar veinte megas
    # para despues decidir que sobraban es pagar el ancho de banda del abuso.
    if foto.declared_bytes is not None and foto.declared_bytes > settings.max_photo_bytes:
        raise FalloPermanente(
            f"declara {foto.declared_bytes} bytes, tope {settings.max_photo_bytes}"
        )

    # Un asyncio.run por foto: el adaptador es asincrono porque es red, y montar
    # un bucle cuesta milisegundos al lado de una descarga.
    datos = asyncio.run(canal.fetch_media(foto.external_file_id))

    if len(datos) > settings.max_photo_bytes:
        raise FalloPermanente(f"descargo {len(datos)} bytes, tope {settings.max_photo_bytes}")

    try:
        validada = images.validate(datos)
    except images.ImagenInvalida as exc:
        raise FalloPermanente(str(exc)) from exc

    clave = storage.build_key(foto.report_id, foto.id, kind="original", ext=validada.extension)
    guardado = storage.put(clave, datos, validada.mime)

    miniatura = images.thumbnail(datos)
    clave_min = storage.build_key(foto.report_id, foto.id, kind="thumb", ext="jpg")
    guardada_min = storage.put(clave_min, miniatura, "image/jpeg")

    foto.storage_key = guardado.key
    foto.content_sha256 = guardado.sha256
    foto.bytes = guardado.bytes
    foto.thumbnail_key = guardada_min.key
    foto.thumbnail_bytes = guardada_min.bytes
    # La huella se calcula sobre los bytes originales, no sobre la miniatura:
    # asi dos fotos iguales dan la misma huella aunque una se haya subido
    # antes de que existiera el redimensionado.
    foto.phash = images.perceptual_hash(datos)
    foto.width = validada.width
    foto.height = validada.height
    foto.mime_type = validada.mime
    foto.status = "stored"
    foto.stored_at = datetime.now(UTC)
    foto.locked_at = None
    foto.failure_reason = None


def mark_failure(session: Session, foto: ReportPhoto, motivo: str, permanente: bool) -> None:
    """Anota el fallo y decide si vuelve a la cola.

    La espera crece con los intentos. Un servicio caido se recupera solo si se
    le da tiempo; insistir cada dos segundos lo unico que hace es que el fallo
    salga mas caro.
    """
    foto.attempts = (foto.attempts or 0) + 1
    foto.failure_reason = motivo[:500]
    foto.locked_at = None

    if permanente or foto.attempts >= settings.worker_max_attempts:
        foto.status = "failed"
        foto.next_attempt_at = None
        log.warning("foto %s en failed tras %s intentos: %s", foto.id, foto.attempts, motivo)
        return

    espera = min(300, 2**foto.attempts)
    foto.status = "pending"
    foto.next_attempt_at = datetime.now(UTC) + timedelta(seconds=espera)
    log.info("foto %s reintenta en %ss (intento %s): %s", foto.id, espera, foto.attempts, motivo)


def run_once(session: Session) -> int:
    """Una pasada. Devuelve cuantas fotos se procesaron."""
    reclamadas = reclaim_stale(session)
    if reclamadas:
        log.info("%s fotos reclamadas de un trabajador caido", reclamadas)
        session.commit()

    fotos = claim(session, settings.worker_batch_size)
    if not fotos:
        return 0

    for foto in fotos:
        try:
            process_one(session, foto)
            session.commit()
            log.info("foto %s guardada (%s bytes)", foto.id, foto.bytes)
        except FalloPermanente as exc:
            session.rollback()
            session.refresh(foto)
            mark_failure(session, foto, str(exc), permanente=True)
            session.commit()
        except Exception as exc:
            session.rollback()
            session.refresh(foto)
            mark_failure(session, foto, f"{type(exc).__name__}: {exc}", permanente=False)
            session.commit()

    return len(fotos)


def main() -> int:
    logging_setup.configure()

    corriendo = True

    def parar(*_):
        # Terminar la foto en curso antes de salir: matar a mitad de una subida
        # deja la fila en processing y hay que esperar a que venza el bloqueo.
        nonlocal corriendo
        corriendo = False
        log.info("señal recibida, terminando la tanda en curso")

    signal.signal(signal.SIGTERM, parar)
    signal.signal(signal.SIGINT, parar)

    log.info("trabajador de fotos arriba, bucket %s", settings.s3_bucket)

    while corriendo:
        try:
            with SessionLocal() as session:
                # La base puede no estar lista si el trabajador arranca primero.
                session.execute(text("SELECT 1"))
                # Dos colas en el mismo proceso: el volumen no justifica un
                # contenedor mas, que es algo mas que desplegar y vigilar.
                procesadas = run_once(session) + classify_worker.run_once(session)
        except Exception:
            log.exception("fallo en la pasada del trabajador")
            procesadas = 0

        if procesadas == 0 and corriendo:
            time.sleep(settings.worker_poll_seconds)

    log.info("trabajador detenido")
    return 0


if __name__ == "__main__":
    sys.exit(main())
