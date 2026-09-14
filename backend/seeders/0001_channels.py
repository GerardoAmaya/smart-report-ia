"""Canales de entrada conocidos.

Telegram es el unico de la fase 1. WhatsApp no entra por el tramite de cuenta
verificada de Meta, no por diseno: cuando entre es una fila aca y una clase que
implementa InboundChannel.
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Channel

CHANNELS = [
    {"code": "telegram", "display_name": "Telegram", "is_active": True},
]


def seed(session: Session) -> None:
    for row in CHANNELS:
        # DO UPDATE solo del nombre visible: is_active lo puede haber apagado
        # un operador para cerrar un canal, y el seeder no tiene por que
        # reabrirlo en el siguiente despliegue.
        stmt = (
            insert(Channel)
            .values(**row)
            .on_conflict_do_update(
                index_elements=[Channel.code],
                set_={"display_name": row["display_name"]},
            )
        )
        session.execute(stmt)
