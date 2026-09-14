"""Politica de retencion de fotos.

No es un numero suelto, es una politica, y esta escrita en el README. Aca solo
se cumple.

El motivo de fondo no es el espacio. Son fotos de la via publica: llevan caras y
placas de gente que no pidio salir, y PLAN.md ya las llama el dato mas sensible
del sistema. Guardarlas para siempre porque caben no es una decision, es la
ausencia de una.

**Se borran los bytes y queda la fila.** El historial del caso no se evapora: se
sabe que hubo una foto, cuando, y cuando se borro. Lo que desaparece es la
imagen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import logging_setup, storage
from app.config import settings
from app.models import Case, CasePhoto, Report, ReportPhoto

log = logging.getLogger("smart_report.retention")


@dataclass(frozen=True)
class Regla:
    nombre: str
    estados_de_reporte: tuple[str, ...]
    antiguedad: timedelta
    motivo: str


def reglas() -> list[Regla]:
    return [
        Regla(
            nombre="rechazado",
            estados_de_reporte=("rejected",),
            antiguedad=timedelta(hours=settings.retention_rejected_hours),
            motivo="reporte rechazado: no queremos guardar lo que no pedimos",
        ),
        Regla(
            nombre="incompleto",
            estados_de_reporte=("incomplete",),
            antiguedad=timedelta(days=settings.retention_incomplete_days),
            motivo="reporte nunca completado: no es un reporte, es media conversacion",
        ),
        # Viva desde la fase 6, cuando aparecio el cierre. Se escribio en la
        # fase 2 para que la politica estuviera completa, y empezo a borrar sola
        # el dia que hubo cierres, sin que nadie tuviera que volver aqui.
        Regla(
            nombre="cerrado",
            estados_de_reporte=("closed",),
            antiguedad=timedelta(days=settings.retention_closed_days),
            motivo="caso cerrado: la evidencia pierde valor, el reclamo tardio cabe en 90 dias",
        ),
    ]


def expired(session: Session, regla: Regla, limite: int = 500) -> list[ReportPhoto]:
    """Fotos que la regla alcanza y que todavia tienen bytes guardados."""
    corte = datetime.now(UTC) - regla.antiguedad
    stmt = (
        select(ReportPhoto)
        .join(Report, Report.id == ReportPhoto.report_id)
        .where(
            Report.status.in_(regla.estados_de_reporte),
            Report.updated_at < corte,
            ReportPhoto.deleted_at.is_(None),
            ReportPhoto.storage_key.is_not(None),
        )
        .limit(limite)
    )
    return list(session.execute(stmt).scalars().all())


def expired_case_photos(session: Session, limite: int = 500) -> list[CasePhoto]:
    """Fotos de evidencia de casos cerrados hace mas de lo que dice la politica.

    Cuelgan de `closed_at` y no de `updated_at`: un caso reabierto deja
    `closed_at` en nulo, asi que su evidencia vuelve a estar fuera del alcance
    de la retencion mientras siga abierto. Contarlo desde `updated_at` habria
    borrado la foto de un caso que se acababa de reabrir.
    """
    corte = datetime.now(UTC) - timedelta(days=settings.retention_closed_days)
    stmt = (
        select(CasePhoto)
        .join(Case, Case.id == CasePhoto.case_id)
        .where(
            Case.status == "closed",
            Case.closed_at.is_not(None),
            Case.closed_at < corte,
            CasePhoto.deleted_at.is_(None),
        )
        .limit(limite)
    )
    return list(session.execute(stmt).scalars().all())


def purge_case_photo(session: Session, foto: CasePhoto) -> None:
    for clave in (foto.storage_key, foto.thumbnail_key):
        if clave:
            try:
                storage.delete(clave)
            except Exception:
                log.exception("no se pudo borrar %s", clave)
                raise

    foto.deleted_at = datetime.now(UTC)
    foto.storage_key = ""
    foto.thumbnail_key = None


def purge_photo(session: Session, foto: ReportPhoto, motivo: str) -> None:
    """Borra los bytes y deja la fila marcada."""
    for clave in (foto.storage_key, foto.thumbnail_key):
        if clave:
            try:
                storage.delete(clave)
            except Exception:
                # Si el borrado falla, no se marca: marcar sin borrar dejaria
                # bytes huerfanos en el bucket que nadie volveria a mirar.
                log.exception("no se pudo borrar %s", clave)
                raise

    foto.deleted_at = datetime.now(UTC)
    foto.storage_key = None
    foto.thumbnail_key = None
    foto.failure_reason = f"retencion: {motivo}"


def run(session: Session, dry_run: bool = False) -> dict[str, int]:
    """Aplica todas las reglas. Devuelve cuantas fotos toco cada una."""
    resultado: dict[str, int] = {}

    for regla in reglas():
        fotos = expired(session, regla)
        resultado[regla.nombre] = len(fotos)

        if dry_run or not fotos:
            continue

        for foto in fotos:
            purge_photo(session, foto, regla.motivo)
        session.commit()
        log.info("retencion %s: %s fotos borradas", regla.nombre, len(fotos))

    # Las de evidencia van aparte porque cuelgan de `closed_at` y no del estado
    # del reporte: son de la cuadrilla, no de quien reporto.
    evidencias = expired_case_photos(session)
    resultado["evidencia"] = len(evidencias)
    if evidencias and not dry_run:
        for foto in evidencias:
            purge_case_photo(session, foto)
        session.commit()
        log.info("retencion evidencia: %s fotos borradas", len(evidencias))

    return resultado


def orphans(session: Session, limite: int = 1000) -> list[str]:
    """Objetos en el bucket que ninguna fila referencia.

    Aparecen cuando una fila se borra sin pasar por la retencion: un borrado a
    mano, una restauracion parcial, o —como paso aqui— un script de depuracion
    equivocado. Sin este barrido esos bytes quedan fuera del alcance de la
    politica para siempre: nadie los encuentra y nadie los borra, que es el peor
    sitio donde puede quedar una foto de la via publica.

    Se respeta una gracia: el trabajador sube los bytes y despues confirma la
    fila, asi que un objeto recien subido todavia no tiene quien lo apunte.
    """
    corte = datetime.now(UTC) - timedelta(hours=settings.orphan_grace_hours)

    # **Las de evidencia tambien.** Sin ellas, el barrido las tomaria por
    # huerfanas y borraria la foto del arreglo de todos los casos cerrados.
    referenciadas: set[str] = set()
    for columna in (
        ReportPhoto.storage_key,
        ReportPhoto.thumbnail_key,
        CasePhoto.storage_key,
        CasePhoto.thumbnail_key,
    ):
        referenciadas.update(k for k in session.execute(select(columna)).scalars().all() if k)

    cliente = storage.client()
    huerfanos: list[str] = []
    token: str | None = None

    while True:
        argumentos = {"Bucket": settings.s3_bucket, "MaxKeys": 1000}
        if token:
            argumentos["ContinuationToken"] = token
        respuesta = cliente.list_objects_v2(**argumentos)

        for objeto in respuesta.get("Contents", []):
            clave = objeto["Key"]
            if clave in referenciadas:
                continue
            if objeto["LastModified"] > corte:
                # Demasiado reciente: puede estar entrando ahora mismo.
                continue
            huerfanos.append(clave)
            if len(huerfanos) >= limite:
                return huerfanos

        if not respuesta.get("IsTruncated"):
            break
        token = respuesta.get("NextContinuationToken")

    return huerfanos


def purge_orphans(session: Session, dry_run: bool = False) -> int:
    claves = orphans(session)
    if dry_run:
        return len(claves)

    for clave in claves:
        storage.delete(clave)
    if claves:
        log.info("retencion huerfanos: %s objetos borrados", len(claves))
    return len(claves)


def main() -> int:
    import sys

    logging_setup.configure()
    seco = "--dry-run" in sys.argv

    from app.db import SessionLocal

    with SessionLocal() as session:
        resultado = run(session, dry_run=seco)
        sueltos = purge_orphans(session, dry_run=seco)

    etiqueta = "se borrarian" if seco else "borradas"
    for nombre, cuantas in resultado.items():
        print(f"  {nombre:12} {cuantas:4} fotos {etiqueta}")
    print(f"  {'huerfanos':12} {sueltos:4} objetos {etiqueta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
