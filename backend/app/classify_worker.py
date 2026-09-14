"""Cola de clasificacion.

Mismo patron que la de fotos y en el mismo proceso: `FOR UPDATE SKIP LOCKED`,
reintentos con espera creciente, reclamo de filas huerfanas. Dos colas en un
trabajador y no dos contenedores, porque el volumen no lo justifica y un
proceso mas es algo mas que desplegar y vigilar.

Se encola sola cuando un reporte queda completo y tiene su foto guardada. No
antes: clasificar sin la foto en almacenamiento propio significaria bajarla de
Telegram otra vez.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session

from app import classify, storage
from app.config import settings
from app.models import Classification, Report, ReportPhoto

log = logging.getLogger("smart_report.classify")


class FalloPermanente(Exception):
    """No mejora reintentando."""


def enqueue_pending(session: Session, limite: int = 50) -> int:
    """Encola los reportes completos que todavia no se clasificaron."""
    ya_tiene = exists().where(Classification.report_id == Report.id)
    tiene_foto = (
        exists()
        .where(ReportPhoto.report_id == Report.id)
        .where(ReportPhoto.status == "stored")
        .where(ReportPhoto.kind == "report")
    )

    reportes = (
        session.execute(
            select(Report.id)
            .where(Report.status == "received", tiene_foto, ~ya_tiene)
            .limit(limite)
        )
        .scalars()
        .all()
    )

    for report_id in reportes:
        session.add(Classification(report_id=report_id, status="pending"))
    if reportes:
        session.commit()
    return len(reportes)


def reclaim_stale(session: Session) -> int:
    corte = datetime.now(UTC) - timedelta(seconds=settings.worker_stale_lock_seconds)
    resultado = session.execute(
        update(Classification)
        .where(Classification.status == "processing", Classification.locked_at < corte)
        .values(status="pending", locked_at=None)
    )
    return resultado.rowcount or 0


def claim(session: Session, limite: int) -> list[Classification]:
    ahora = datetime.now(UTC)
    filas = (
        session.execute(
            select(Classification)
            .where(
                Classification.status == "pending",
                (Classification.next_attempt_at.is_(None))
                | (Classification.next_attempt_at <= ahora),
            )
            .order_by(Classification.next_attempt_at.nulls_first(), Classification.created_at)
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


def _imagen_para(session: Session, clasificacion: Classification) -> tuple[bytes, str, str]:
    foto = session.execute(
        select(ReportPhoto)
        .where(
            ReportPhoto.report_id == clasificacion.report_id,
            ReportPhoto.status == "stored",
            ReportPhoto.kind == "report",
        )
        .order_by(ReportPhoto.created_at)
        .limit(1)
    ).scalar_one_or_none()

    if foto is None:
        raise FalloPermanente("el reporte no tiene foto guardada")

    variante = settings.classify_image_variant
    clave = foto.thumbnail_key if variante == "thumbnail" else foto.storage_key
    if not clave:
        raise FalloPermanente(f"la foto no tiene clave para la variante {variante}")

    # La miniatura siempre es JPEG aunque el original no lo sea.
    mime = "image/jpeg" if variante == "thumbnail" else (foto.mime_type or "image/jpeg")
    return storage.get(clave), mime, variante


def process_one(session: Session, clasificacion: Classification) -> None:
    reporte = session.get(Report, clasificacion.report_id)
    if reporte is None:
        raise FalloPermanente("el reporte ya no existe")

    imagen, mime, variante = _imagen_para(session, clasificacion)
    resultado = classify.classify(imagen, mime, caption=reporte.caption, image_variant=variante)

    # proposed_*, nunca final_*: lo final lo escribe una persona al confirmar.
    clasificacion.proposed_category = resultado.propuesta.category.value
    clasificacion.proposed_severity = resultado.propuesta.severity.value
    clasificacion.proposed_reason = resultado.propuesta.reason
    clasificacion.model = resultado.model
    clasificacion.input_tokens = resultado.input_tokens
    clasificacion.output_tokens = resultado.output_tokens
    clasificacion.cost_usd = resultado.cost_usd
    clasificacion.latency_ms = resultado.latency_ms
    clasificacion.image_variant = resultado.image_variant
    clasificacion.status = "proposed"
    clasificacion.locked_at = None
    clasificacion.failure_reason = None


def mark_failure(
    session: Session, clasificacion: Classification, motivo: str, permanente: bool
) -> None:
    clasificacion.attempts = (clasificacion.attempts or 0) + 1
    clasificacion.failure_reason = motivo[:500]
    clasificacion.locked_at = None

    if permanente or clasificacion.attempts >= settings.classify_max_attempts:
        clasificacion.status = "failed"
        clasificacion.next_attempt_at = None
        log.warning(
            "clasificacion %s en failed tras %s intentos: %s",
            clasificacion.id,
            clasificacion.attempts,
            motivo,
        )
        return

    espera = min(300, 5 * 2**clasificacion.attempts)
    clasificacion.status = "pending"
    clasificacion.next_attempt_at = datetime.now(UTC) + timedelta(seconds=espera)
    log.info("clasificacion %s reintenta en %ss: %s", clasificacion.id, espera, motivo)


def run_once(session: Session) -> int:
    """Una pasada: encolar, reclamar huerfanas, clasificar una tanda."""
    enqueue_pending(session)

    reclamadas = reclaim_stale(session)
    if reclamadas:
        log.info("%s clasificaciones reclamadas", reclamadas)
        session.commit()

    filas = claim(session, settings.worker_batch_size)
    if not filas:
        return 0

    for fila in filas:
        try:
            process_one(session, fila)
            session.commit()
            log.info(
                "reporte %s propuesto como %s/%s (USD %s)",
                fila.report_id,
                fila.proposed_category,
                fila.proposed_severity,
                fila.cost_usd,
            )
            _preguntar(session, fila)
        except FalloPermanente as exc:
            session.rollback()
            session.refresh(fila)
            mark_failure(session, fila, str(exc), permanente=True)
            session.commit()
        except Exception as exc:
            session.rollback()
            session.refresh(fila)
            mark_failure(session, fila, f"{type(exc).__name__}: {exc}", permanente=False)
            session.commit()

    return len(filas)


def _preguntar(session: Session, clasificacion: Classification) -> None:
    """Le manda la propuesta a quien reporto, para que confirme.

    Si esto falla, la clasificacion sigue siendo valida y queda en `proposed`:
    no se puede confirmar, pero tampoco se pierde. Un fallo al avisar no tiene
    por que deshacer el trabajo del modelo, que ya se pago.
    """
    import asyncio

    from app import confirm
    from app.channels import get_channel

    reporte = session.get(Report, clasificacion.report_id)
    if reporte is None:
        return

    texto, opciones = confirm.pregunta(clasificacion)
    canal = get_channel(reporte.channel)
    try:
        asyncio.run(canal.ask_out_of_band(reporte.external_user_id, texto, opciones))
    except Exception:
        log.exception("no se pudo preguntar por la clasificacion %s", clasificacion.id)
