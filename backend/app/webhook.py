"""Webhook del canal.

Tiene un segundo para responder. Si tarda, Telegram reenvia el update, y un
reenvio es un reporte duplicado si la idempotencia no aguanta.

Por eso aca no hay ni una llamada de red saliente: la respuesta a quien reporta
viaja en el cuerpo de esta misma respuesta HTTP. Bajar la foto es de la fase 2
y va por la cola, no por aca.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request, Response
from sqlalchemy.orm import Session

from app import ingest
from app.channels import get_channel
from app.config import settings
from app.db import get_session
from app.rate_limit import hit
from app.security import body_was_truncated, client_ip, rate_limit_key, verify_webhook_secret

log = logging.getLogger("smart_report.webhook")

router = APIRouter()

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


@router.post("/webhooks/telegram")
def telegram_webhook(
    request: Request,
    response: Response,
    payload: Annotated[dict, Body()],
    session: Annotated[Session, Depends(get_session)],
) -> dict:
    """Recibe un update de Telegram.

    Devuelve 200 en casi todo, y no por descuido: un codigo de error hace que
    Telegram reintente. Solo se responde error cuando el reintento es lo que
    queremos (fallo transitorio) o cuando la peticion no es de Telegram.
    """
    if body_was_truncated(request):
        response.status_code = 413
        return {"detail": "cuerpo demasiado grande"}

    # Autenticidad primero: sin esto, cualquiera que descubra la URL inyecta
    # reportes falsos, y no hay forma de distinguirlos despues.
    if not verify_webhook_secret(request.headers.get(SECRET_HEADER)):
        log.warning("webhook rechazado: secreto invalido desde %s", client_ip(request))
        response.status_code = 403
        return {"detail": "prohibido"}

    canal = get_channel("telegram")

    # Limite por IP: protege el servicio. Va antes de parsear nada.
    por_ip = hit(
        session,
        scope="ip",
        key=rate_limit_key(client_ip(request)),
        limit=settings.rate_limit_ip_per_minute,
        window_seconds=60,
    )
    if not por_ip.allowed:
        session.commit()
        response.status_code = 429
        response.headers["Retry-After"] = str(por_ip.retry_after_seconds)
        return {"detail": "demasiadas peticiones"}

    update_id = canal.update_id(payload)
    if update_id is None:
        # Ni el identificador se pudo leer. No hay nada que guardar sin
        # arriesgar duplicados, y reintentarlo no lo va a mejorar.
        log.warning("update sin update_id, descartado")
        session.commit()
        return {}

    inbound_id = ingest.record_raw(session, canal.code, update_id, payload)
    if inbound_id is None:
        # Ya lo teniamos: es un reintento de Telegram porque una respuesta
        # anterior tardo. Confirmar y no volver a aplicarlo.
        session.commit()
        log.info("update %s repetido, ignorado", update_id)
        return {}

    # Confirmar el crudo aqui y no al final: si lo que viene falla, hay que
    # poder revertir lo aplicado sin perder el payload original, que es lo
    # unico que permite reprocesar. Son dos escrituras locales diminutas y el
    # presupuesto del segundo ni se entera.
    session.commit()

    mensaje = canal.parse(payload)
    if mensaje is None:
        # Guardado crudo queda, que es lo que importa. No sabemos contestarlo.
        session.commit()
        return {}

    # Limite por usuario: protege el almacenamiento y la cuota del modelo. Es
    # otro problema que el limite por IP y por eso es otro limite: una oficina
    # entera sale por una sola IP, y un usuario puede cambiar de red.
    por_usuario = hit(
        session,
        scope="tg_user",
        key=rate_limit_key(mensaje.external_user_id),
        limit=settings.rate_limit_user_per_hour,
        window_seconds=3600,
    )
    if not por_usuario.allowed:
        session.commit()
        return canal.ack(mensaje.external_user_id, ingest.DEMASIADOS)

    try:
        respuesta = ingest.handle(session, mensaje, inbound_id)
    except Exception as exc:
        # El crudo ya esta confirmado, asi que revertir solo deshace lo que se
        # aplico mal. Se anota el fallo y se responde 200: reprocesar es un
        # trabajo aparte que lee inbound_updates, no un reintento del canal.
        session.rollback()
        ingest.record_failure(session, inbound_id, type(exc).__name__)
        session.commit()
        log.exception("fallo procesando el update %s", update_id)
        return {}

    ingest.mark_processed(session, inbound_id)
    session.commit()
    log.info("update %s procesado: %s", update_id, mensaje.kind)

    return canal.ack(mensaje.external_user_id, respuesta.text, respuesta.ask_location)
