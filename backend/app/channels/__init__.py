"""Registro de canales.

La busqueda es por codigo porque ese codigo es el mismo que la fila de
`channels` en la base: si no coinciden, la clave foranea lo dice al insertar.
"""

from app.channels.base import InboundChannel, InboundMessage, InboundPhoto
from app.channels.telegram import TelegramChannel

_REGISTRY: dict[str, InboundChannel] = {
    TelegramChannel.code: TelegramChannel(),
}


def get_channel(code: str) -> InboundChannel:
    try:
        return _REGISTRY[code]
    except KeyError:
        raise LookupError(f"canal desconocido: {code}") from None


__all__ = [
    "InboundChannel",
    "InboundMessage",
    "InboundPhoto",
    "TelegramChannel",
    "get_channel",
]
