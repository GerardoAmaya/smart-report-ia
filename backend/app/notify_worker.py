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

from app.channels import get_channel
from app.config import settings
from app.models import Notification

log = logging.getLogger("smart_report.notify")


class FalloPermanente(Exception):
    """No mejora reintentando."""


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


def process_one(aviso: Notification) -> None:
    canal = get_channel(aviso.channel)
    try:
        asyncio.run(canal.notify(aviso.external_user_id, aviso.body))
    except Exception as exc:
        # Quien bloqueo al bot o borro la conversacion no va a recibirlo nunca:
        # reintentar eso es gastar cuota para llegar a la misma conclusion.
        texto = str(exc).lower()
        if "blocked" in texto or "chat not found" in texto or "deactivated" in texto:
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
            process_one(aviso)
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
