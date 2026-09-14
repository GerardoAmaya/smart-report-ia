"""Adaptador de Telegram.

Aca adentro se puede hablar de `Update`, `PhotoSize` y `chat_id`. Afuera no:
lo que sale es `InboundMessage` y nada mas.

PTB se usa como biblioteca y no como framework —sus tipos y su cliente, no su
`Application` ni su despachador—, porque el enrutado ya lo hace FastAPI y dos
maquinas de despacho en el mismo proceso son una de mas.
"""

from __future__ import annotations

from datetime import UTC, datetime

from telegram import Update

from app.channels.base import InboundMessage, InboundPhoto
from app.config import settings


class TelegramChannel:
    code = "telegram"

    # --- Entrada ---

    def update_id(self, payload: dict) -> str | None:
        valor = payload.get("update_id")
        return str(valor) if isinstance(valor, int) else None

    def parse(self, payload: dict) -> InboundMessage | None:
        try:
            update = Update.de_json(payload)
        except Exception:
            # Un payload que PTB no entiende no es una excepcion del servicio:
            # es basura o una version nueva de la API. Se guarda crudo igual y
            # se responde 200, porque un error haria que Telegram reintente
            # eternamente algo que nunca vamos a poder parsear.
            return None

        message = update.effective_message
        user = update.effective_user
        if message is None or user is None:
            return None

        comun = {
            "channel": self.code,
            "external_update_id": str(update.update_id),
            "external_user_id": str(user.id),
            "received_at": message.date or datetime.now(UTC),
        }

        if message.photo:
            # Telegram manda la misma foto en varios tamanos, de menor a mayor.
            # El ultimo es el grande; los otros son miniaturas que el propio
            # Telegram genero y no sirven como evidencia.
            grande = message.photo[-1]
            return InboundMessage(
                **comun,
                kind="photo",
                caption=message.caption,
                photo=InboundPhoto(
                    external_file_id=grande.file_id,
                    external_file_unique_id=grande.file_unique_id,
                    declared_bytes=grande.file_size,
                    width=grande.width,
                    height=grande.height,
                ),
            )

        if message.location:
            return InboundMessage(
                **comun,
                kind="location",
                lat=message.location.latitude,
                lon=message.location.longitude,
            )

        texto = (message.text or "").strip()
        if texto.startswith("/start"):
            return InboundMessage(**comun, kind="start")
        if texto:
            return InboundMessage(**comun, kind="text", caption=texto)

        # Sticker, audio, documento: llego algo que no sabemos usar. Se nombra
        # para poder contestarle a la persona en vez de ignorarla.
        return InboundMessage(**comun, kind="unsupported")

    # --- Salida ---

    def ack(self, external_user_id: str, text: str, ask_location: bool = False) -> dict:
        """Llamada a la API de Telegram metida en la respuesta al webhook."""
        cuerpo: dict = {
            "method": "sendMessage",
            "chat_id": external_user_id,
            "text": text,
        }
        if ask_location:
            # El boton nativo. La ubicacion nunca sale de los EXIF de la foto:
            # Telegram comprime las imagenes y les quita los metadatos.
            cuerpo["reply_markup"] = {
                "keyboard": [[{"text": "Enviar mi ubicacion", "request_location": True}]],
                "resize_keyboard": True,
                "one_time_keyboard": True,
            }
        else:
            cuerpo["reply_markup"] = {"remove_keyboard": True}
        return cuerpo

    # --- Red: fase 2 en adelante ---

    def _bot(self):
        from telegram import Bot

        token = settings.telegram_bot_token.get_secret_value()
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN sin definir")
        return Bot(token)

    async def fetch_media(self, external_file_id: str) -> bytes:
        """Descarga un archivo. Lo usa el trabajador de la fase 2."""
        bot = self._bot()
        async with bot:
            archivo = await bot.get_file(external_file_id)
            return bytes(await archivo.download_as_bytearray())

    async def notify(self, external_user_id: str, text: str) -> None:
        """Aviso fuera de banda. Nunca desde el webhook: esto es una llamada de red."""
        bot = self._bot()
        async with bot:
            await bot.send_message(chat_id=external_user_id, text=text)
