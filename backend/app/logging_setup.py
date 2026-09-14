"""Configuracion de registro comun.

Existe por un fallo concreto: python-telegram-bot habla por httpx, y httpx
registra en INFO la URL completa de cada peticion. La URL de la API de Telegram
**lleva el token dentro de la ruta**, asi que el registro por defecto escupe la
credencial del bot en cada llamada, a los logs del contenedor y a donde sea que
se recojan.

Un secreto en un log es peor que un secreto en el codigo: nadie lo revisa, se
copia a sistemas de agregacion y sobrevive a la rotacion.
"""

from __future__ import annotations

import logging
import re

# Cualquier cosa con forma de token de bot dentro de una URL de Telegram.
_TOKEN = re.compile(r"/bot\d{6,12}:[A-Za-z0-9_-]{20,}")


class RedactaSecretos(logging.Filter):
    """Tapa credenciales en cualquier registro que pase por aca.

    Filtro y no solo silenciar httpx: silenciar tapa el caso conocido, pero el
    dia que otra biblioteca registre la misma URL vuelve el problema. Esto
    reescribe el mensaje venga de donde venga.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str) and "/bot" in record.msg:
            record.msg = _TOKEN.sub("/bot<oculto>", record.msg)
        if record.args:
            record.args = tuple(
                _TOKEN.sub("/bot<oculto>", a) if isinstance(a, str) else a for a in record.args
            )
        return True


def configure(nivel: int = logging.INFO) -> None:
    logging.basicConfig(level=nivel, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    filtro = RedactaSecretos()
    for handler in logging.getLogger().handlers:
        handler.addFilter(filtro)

    # httpx registra la URL entera en INFO. Se sube a WARNING ademas del filtro:
    # dos defensas, porque esta es la que ya fallo una vez.
    # httpx2 y no solo httpx: el SDK de Anthropic 1.x usa httpx2, y cada
    # cliente nuevo trae su propio registrador.
    for ruidoso in (
        "httpx",
        "httpx2",
        "httpcore",
        "telegram.ext",
        "botocore",
        "boto3",
        "s3transfer",
        "anthropic",
    ):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
