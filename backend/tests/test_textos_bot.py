"""Lo que le llega a quien reporta va en español correcto, con tildes.

Existe por un fallo real: el bot mandaba «Mandame una foto del problema y
despues tu ubicacion» y un boton «Enviar mi ubicacion», mientras el tablero ya
iba con tildes. Recorre todos los textos que salen por Telegram y falla si
aparece alguna de las faltas que ya hubo, de una lista explicita: una
heuristica acabaria marcando palabras bien escritas.
"""

import re
import uuid
from datetime import UTC, datetime

from app import confirm, dispatch, ingest
from app.channels.telegram import TelegramChannel
from app.models import Case, Classification, Crew, Report

# Sin tilde → con tilde. Solo palabras que en estos textos siempre la llevan.
FALTAS = {
    "despues": "después",
    "ubicacion": "ubicación",
    "boton": "botón",
    "aqui": "aquí",
    "todavia": "todavía",
    "recibi": "recibí",
    "revise": "revisé",
    "validas": "válidas",
    "publico": "público",
    "atencion": "atención",
    "quedo": "quedó",
    "categoria": "categoría",
    "automaticamente": "automáticamente",
    "mas tarde": "más tarde",
    "si, es": "sí, es",
    "que es entonces": "qué es entonces",
}


def _textos_del_bot() -> list[str]:
    textos = [v for k, v in vars(ingest).items() if k.isupper() and isinstance(v, str)]
    textos += [confirm.YA_CONFIRMADO, confirm.NO_ENCONTRADO]
    textos += list(confirm.ETIQUETAS.values()) + list(confirm.ETIQUETA_SEVERIDAD.values())
    textos += list(dispatch.ETIQUETA_CATEGORIA.values())

    # Los mensajes armados, con una clasificacion y un caso de mentira.
    clasificacion = Classification(
        id=uuid.uuid4(),
        proposed_category="vialidad",
        proposed_severity="media",
        proposed_reason="Se ve un bache.",
        final_severity="media",
    )
    texto, opciones = confirm.pregunta(clasificacion)
    textos += [texto] + [etiqueta for etiqueta, _ in opciones]
    texto, opciones = confirm.opciones_de_categoria(clasificacion)
    textos += [texto] + [etiqueta for etiqueta, _ in opciones]
    textos.append(confirm.pedir_categoria(clasificacion)[0])
    textos.append(confirm._resumen(clasificacion, "Confirmado, gracias.", "vialidad"))

    caso = Case(category="espacio_publico", closing_note="Listo")
    reporte = Report(created_at=datetime(2026, 9, 14, tzinfo=UTC), address_text="Calle Real")
    for kind in ("assigned", "in_progress", "closed", "otro"):
        textos.append(dispatch.mensaje(caso, kind, Crew(name="Cuadrilla de bacheo"), reporte))

    # El boton nativo de ubicacion.
    cuerpo = TelegramChannel().ack("1", ingest.PEDIR_UBICACION, ask_location=True)
    textos += [b["text"] for fila in cuerpo["reply_markup"]["keyboard"] for b in fila]
    return textos


def test_los_textos_del_bot_llevan_sus_tildes():
    textos = _textos_del_bot()
    assert len(textos) > 30, "no se juntaron los textos: la prueba no estaria mirando nada"

    faltas = []
    for texto in textos:
        for mal, bien in FALTAS.items():
            if re.search(rf"\b{re.escape(mal)}\b", texto, flags=re.IGNORECASE):
                faltas.append(f"{mal!r} (va {bien!r}) en: {texto!r}")
    assert not faltas, "\n".join(faltas)
