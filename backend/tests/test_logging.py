"""Que no se filtren credenciales por los registros.

Esto existe por un fallo real: python-telegram-bot habla por httpx, httpx
registra la URL completa en INFO, y la URL de la API de Telegram lleva el token
**dentro de la ruta**. El trabajador escupio la credencial del bot en los logs
del contenedor en cada llamada.

Un secreto en un log es peor que uno en el codigo: nadie lo revisa, se copia a
sistemas de agregacion y sobrevive a la rotacion.
"""

import logging

from app.logging_setup import RedactaSecretos, configure

TOKEN_FALSO = "8844248832:AAGvOksIcro1TaPX7lzzuSOcElmouS2adcM"


def _registro(mensaje: str, *args) -> logging.LogRecord:
    return logging.LogRecord("prueba", logging.INFO, __file__, 1, mensaje, args, None)


def test_tapa_el_token_en_el_mensaje():
    r = _registro(f"HTTP Request: POST https://api.telegram.org/bot{TOKEN_FALSO}/getFile")
    RedactaSecretos().filter(r)

    assert TOKEN_FALSO not in r.getMessage()
    assert "/bot<oculto>" in r.getMessage()


def test_tapa_el_token_en_los_argumentos():
    """El caso que se escapa si solo se mira el mensaje con formato."""
    r = _registro("peticion a %s", f"https://api.telegram.org/bot{TOKEN_FALSO}/getMe")
    RedactaSecretos().filter(r)

    assert TOKEN_FALSO not in r.getMessage()


def test_no_toca_lo_que_no_es_secreto():
    r = _registro("foto %s guardada en %s", "abc-123", "2026/09/14/x/y-original.jpg")
    RedactaSecretos().filter(r)
    assert r.getMessage() == "foto abc-123 guardada en 2026/09/14/x/y-original.jpg"


def test_httpx_queda_callado(caplog):
    """Dos defensas: el filtro tapa, y httpx ni siquiera registra en INFO.

    La segunda porque esta es la via que ya fallo una vez, y silenciarla no
    depende de que el filtro reconozca el formato de la URL.
    """
    configure()
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_el_filtro_queda_puesto_en_la_raiz():
    configure()
    raiz = logging.getLogger()
    assert any(isinstance(f, RedactaSecretos) for h in raiz.handlers for f in h.filters)
