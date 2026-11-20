"""Cola de avisos.

Mandar el aviso es una **llamada de red**, asi que no puede vivir en la peticion
que cierra el caso: cuatro mensajes la volverian lenta, y un fallo en el cuarto
dejaria el caso sin cerrar. El cierre es un hecho; avisarlo es un intento.

Mismo patron que las otras dos colas —`FOR UPDATE SKIP LOCKED`, reintentos con
espera creciente, reclamo de filas huerfanas— y en el mismo proceso.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import images, storage
from app.channels import get_channel
from app.config import settings
from app.models import CasePhoto, Notification

log = logging.getLogger("smart_report.notify")

# Tope de Telegram para el pie de una foto. Un aviso mas largo va sin foto: es
# preferible el texto entero que la foto con el texto cortado.
LIMITE_PIE = 1024


class FalloPermanente(Exception):
    """No mejora reintentando."""


def _es_de_la_persona(exc: Exception) -> bool:
    """Quien bloqueo al bot o borro la conversacion no va a recibirlo nunca."""
    texto = str(exc).lower()
    return "blocked" in texto or "chat not found" in texto or "deactivated" in texto


def _es_de_red(exc: Exception) -> bool:
    """Un corte que se arregla solo: se reintenta, con la foto incluida."""
    return isinstance(exc, (OSError, TimeoutError)) or type(exc).__name__ in {
        "NetworkError",
        "TimedOut",
    }


def _foto_del_arreglo(session: Session, aviso: Notification) -> bytes | None:
    """La ultima foto del arreglo, reducida, si el aviso es el de cierre.

    **El cierre va con su prueba.** Quien reporto es quien mejor sabe si de
    verdad se arreglo, y la foto es lo que le deja comprobarlo. Va solo a
    quienes reportaron ese caso, y una vez enviada queda en su chat: la
    retencion de la evidencia ya no la alcanza ahi.

    Cualquier fallo al prepararla devuelve None y el aviso sale como texto: la
    foto acompaña al aviso y no puede ser la razon de que no llegue.
    """
    if aviso.kind != "closed" or len(aviso.body) > LIMITE_PIE:
        return None
    foto = session.execute(
        select(CasePhoto)
        .where(CasePhoto.case_id == aviso.case_id, CasePhoto.deleted_at.is_(None))
        .order_by(CasePhoto.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if foto is None:
        return None
    try:
        return images.para_aviso(storage.get(foto.storage_key))
    except Exception:
        log.warning("aviso %s sale sin foto: no se pudo preparar", aviso.id, exc_info=True)
        return None


def reclaim_stale(session: Session) -> int:
    corte = datetime.now(UTC) - timedelta(seconds=settings.worker_stale_lock_seconds)
    resultado = session.execute(
        update(Notification)
        .where(Notification.status == "processing", Notification.locked_at < corte)
        .values(status="pending", locked_at=None)
    )
    return resultado.rowcount or 0


def claim(session: Session, limite: int) -> list[Notification]:
    ahora = datetime.now(UTC)
    filas = (
        session.execute(
            select(Notification)
            .where(
                Notification.status == "pending",
                (Notification.next_attempt_at.is_(None)) | (Notification.next_attempt_at <= ahora),
            )
            .order_by(Notification.next_attempt_at.nulls_first(), Notification.created_at)
            .limit(limite)
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )
    for fila in filas:
        fila.status = "processing"
        fila.locked_at = ahora
    session.commit()
    return filas


def _enviar(session: Session, aviso: Notification) -> None:
    canal = get_channel(aviso.channel)
    foto = _foto_del_arreglo(session, aviso)
    if foto is not None:
        try:
            asyncio.run(canal.notify_photo(aviso.external_user_id, foto, aviso.body))
            return
        except Exception as exc:
            # De la persona o de la red: lo decide quien llama, igual que sin
            # foto. Cualquier otra cosa es Telegram rechazando la imagen, y
            # entonces el aviso sale como texto en vez de no salir.
            if _es_de_la_persona(exc) or _es_de_red(exc):
                raise
            log.warning("aviso %s sin foto, Telegram la rechazo: %s", aviso.id, exc)
    asyncio.run(canal.notify(aviso.external_user_id, aviso.body))


def process_one(session: Session, aviso: Notification) -> None:
    try:
        _enviar(session, aviso)
    except Exception as exc:
        # Reintentar a quien bloqueo al bot es gastar cuota para llegar a la
        # misma conclusion.
        if _es_de_la_persona(exc):
            raise FalloPermanente(
                f"{type(exc).__name__}: no se puede escribir a esta persona"
            ) from exc
        raise

    aviso.status = "sent"
    aviso.sent_at = datetime.now(UTC)
    aviso.locked_at = None
    aviso.failure_reason = None


def mark_failure(session: Session, aviso: Notification, motivo: str, permanente: bool) -> None:
    aviso.attempts = (aviso.attempts or 0) + 1
    aviso.failure_reason = motivo[:500]
    aviso.locked_at = None

    if permanente or aviso.attempts >= settings.notify_max_attempts:
        aviso.status = "failed"
        aviso.next_attempt_at = None
        log.warning("aviso %s en failed tras %s intentos: %s", aviso.id, aviso.attempts, motivo)
        return

    espera = min(900, 10 * 2**aviso.attempts)
    aviso.status = "pending"
    aviso.next_attempt_at = datetime.now(UTC) + timedelta(seconds=espera)
    log.info("aviso %s reintenta en %ss: %s", aviso.id, espera, motivo)


def run_once(session: Session) -> int:
    reclamados = reclaim_stale(session)
    if reclamados:
        log.info("%s avisos reclamados", reclamados)
        session.commit()

    filas = claim(session, settings.worker_batch_size)
    if not filas:
        return 0

    for aviso in filas:
        try:
            process_one(session, aviso)
            session.commit()
            log.info("aviso %s enviado a %s", aviso.kind, aviso.external_user_id)
        except FalloPermanente as exc:
            session.rollback()
            session.refresh(aviso)
            mark_failure(session, aviso, str(exc), permanente=True)
            session.commit()
        except Exception as exc:
            session.rollback()
            session.refresh(aviso)
            mark_failure(session, aviso, f"{type(exc).__name__}: {exc}", permanente=False)
            session.commit()

    return len(filas)
