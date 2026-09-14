"""El contrato del canal de entrada.

Telegram es la primera implementacion, no la unica prevista. La prueba de que
el adaptador existe de verdad es que ningun tipo de python-telegram-bot cruza
esta frontera: si `Update` o `PhotoSize` aparecen fuera de telegram.py, esto
no es un adaptador sino decoracion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

# Que trae el mensaje. El canal no decide que hacer con eso; solo lo nombra.
# "choice" es una respuesta a una pregunta con opciones, no texto libre.
MessageKind = Literal["photo", "location", "text", "start", "choice", "unsupported"]


@dataclass(frozen=True)
class InboundPhoto:
    """Una foto tal como la anuncia el canal, antes de descargar nada."""

    external_file_id: str
    external_file_unique_id: str | None
    declared_bytes: int | None
    width: int | None
    height: int | None


@dataclass(frozen=True)
class InboundMessage:
    """Mensaje normalizado. Es lo unico que el resto del sistema conoce."""

    channel: str
    external_update_id: str
    external_user_id: str
    kind: MessageKind
    received_at: datetime
    photo: InboundPhoto | None = None
    lat: float | None = None
    lon: float | None = None
    caption: str | None = None
    # Valor de la opcion elegida, cuando kind es "choice". Lo mando el
    # canal de vuelta tal cual se lo dimos, asi que es dato del usuario y
    # hay que comprobar que le pertenezca antes de actuar sobre el.
    choice: str | None = None
    # Identificador de la interaccion, para poder acusar recibo.
    choice_id: str | None = None
    # Mensaje donde estaban los botones, para poder reemplazarlo en vez de
    # mandar uno nuevo. Editar cabe en el cuerpo del webhook; mandar otro
    # mensaje seria una llamada de red mas.
    choice_message_id: str | None = None


@runtime_checkable
class InboundChannel(Protocol):
    """Lo que tiene que saber hacer un canal.

    `parse` es sincrono porque es CPU pura sobre un dict. Los otros dos son
    asincronos porque son red. La diferencia esta en la firma a proposito: un
    metodo que parece barato y hace una llamada de red es como se acaba con un
    webhook que tarda tres segundos.
    """

    code: str

    def update_id(self, payload: dict) -> str | None:
        """Identificador del update segun el canal, sin interpretarlo.

        Existe aparte de `parse` para poder guardar el crudo de updates que no
        sabemos leer. Si solo se pudiera guardar lo que se parsea, un update de
        un tipo nuevo se perderia justo cuando hace falta verlo.
        """
        ...

    def parse(self, payload: dict) -> InboundMessage | None:
        """Payload crudo del canal a mensaje normalizado.

        Devuelve None si el update no es algo que sepamos interpretar. None no
        es un error: Telegram manda muchos tipos de update que no nos importan.
        """
        ...

    def ack(self, external_user_id: str, text: str, ask_location: bool = False) -> dict:
        """Respuesta para devolver en el cuerpo del propio webhook.

        Telegram acepta una llamada a su API en la respuesta HTTP al webhook,
        lo que ahorra un viaje de ida y vuelta: es la diferencia entre
        responder en decenas de milisegundos o esperar a api.telegram.org
        dentro del segundo que tenemos. Un canal que no pueda hacerlo devuelve
        un dict vacio y usa `notify`.
        """
        ...

    async def fetch_media(self, external_file_id: str) -> bytes:
        """Bytes de un archivo. Lo usa el trabajador de la fase 2, no el webhook."""
        ...

    async def notify(self, external_user_id: str, text: str) -> None:
        """Aviso fuera de banda. Fases 3 y 6."""
        ...

    async def ask(self, external_user_id: str, text: str, options: list[tuple[str, str]]) -> None:
        """Pregunta con opciones cerradas. `options` son pares (etiqueta, valor).

        Cerradas y no texto libre porque la respuesta va a decidir una categoria:
        interpretar "si, mas o menos" es exactamente el tipo de ambiguedad que
        este sistema existe para no tener.
        """
        ...

    def ack_choice(self, choice_id: str, text: str = "") -> dict:
        """Acuse de recibo de una eleccion, para devolver en el webhook.

        El texto se muestra como aviso emergente, asi que una confirmacion
        corta no necesita mandar ningun mensaje aparte.
        """
        ...

    def edit_with_options(
        self, external_user_id: str, message_id: str, text: str, options: list[tuple[str, str]]
    ) -> dict:
        """Reemplaza el mensaje de los botones por otro, con otras opciones."""
        ...
