"""Confirmacion de la categoria propuesta.

**El modelo propone, el codigo decide, y la persona confirma.** Aceptar una
categoria sin preguntar manda una cuadrilla de agua a arreglar una luminaria, y
el error solo se descubre cuando la cuadrilla llega.

La respuesta llega por un boton, no por texto libre: interpretar "si, mas o
menos" es exactamente la ambiguedad que este sistema existe para no tener.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Classification, Report
from app.taxonomy import Category, Severity, categorias_reales

# Los valores viajan a Telegram y vuelven. Telegram limita callback_data a 64
# bytes, asi que el prefijo es de una letra y el resto es el uuid.
PREFIJO_SI = "s:"
PREFIJO_NO = "n:"
PREFIJO_CATEGORIA = "c:"

ETIQUETAS: dict[str, str] = {
    Category.VIALIDAD: "Calle o acera",
    Category.ALUMBRADO: "Alumbrado",
    Category.AGUA: "Agua o drenaje",
    Category.DESECHOS: "Basura",
    Category.RIESGO_ESTRUCTURAL: "Riesgo de derrumbe",
    Category.ESPACIO_PUBLICO: "Parque o espacio público",
    Category.NO_ES_REPORTE: "No es un reporte",
}

ETIQUETA_SEVERIDAD: dict[str, str] = {
    Severity.ALTA: "urgente",
    Severity.MEDIA: "atención",
    Severity.BAJA: "sin urgencia",
}

SEVERIDAD_SIN_PROPUESTA = Severity.MEDIA

YA_CONFIRMADO = "Ese reporte ya estaba confirmado."
NO_ENCONTRADO = "No encuentro ese reporte."


def pregunta(clasificacion: Classification) -> tuple[str, list[tuple[str, str]]]:
    """El texto y los botones para confirmar una propuesta."""
    etiqueta = ETIQUETAS.get(clasificacion.proposed_category, clasificacion.proposed_category)
    severidad = ETIQUETA_SEVERIDAD.get(clasificacion.proposed_severity, "")

    # Sin Markdown a proposito: `proposed_reason` lo escribe el modelo y un
    # guion bajo suelto haria que Telegram rechace el mensaje entero con 400.
    texto = (
        f"Revisé tu reporte y creo que es:\n\n"
        f"{etiqueta} ({severidad})\n"
        f"{clasificacion.proposed_reason}\n\n"
        f"¿Es correcto?"
    )
    opciones = [
        ("Sí, es correcto", f"{PREFIJO_SI}{clasificacion.id}"),
        ("No, es otra cosa", f"{PREFIJO_NO}{clasificacion.id}"),
    ]
    return texto, opciones


def opciones_de_categoria(clasificacion: Classification) -> tuple[str, list[tuple[str, str]]]:
    """La lista de categorias, para cuando la persona corrige."""
    texto = "¿Qué es entonces?"
    # Se numera por posicion y no por nombre: el uuid ya ocupa 36 de los 64
    # bytes que Telegram permite en callback_data.
    opciones = [
        (ETIQUETAS[c], f"{PREFIJO_CATEGORIA}{clasificacion.id}:{i}")
        for i, c in enumerate(categorias_reales())
    ]
    opciones.append((ETIQUETAS[Category.NO_ES_REPORTE], f"{PREFIJO_CATEGORIA}{clasificacion.id}:x"))
    return texto, opciones


def pedir_categoria(clasificacion: Classification) -> tuple[str, list[tuple[str, str]]]:
    """Cuando no hubo propuesta, la persona elige desde el principio.

    Los mismos botones que al corregir: la respuesta entra por el camino que ya
    existe y no hay un segundo flujo que mantener. El texto no habla de modelos
    ni de errores; para quien reporta, solo hace falta un dato mas.
    """
    _, opciones = opciones_de_categoria(clasificacion)
    return "No pude revisar la foto automáticamente. ¿Qué tipo de problema es?", opciones


def _resumen(clasificacion: Classification, encabezado: str, categoria: str) -> str:
    """Como queda el mensaje despues de responder.

    Repite la categoria porque este texto **reemplaza** a la propuesta: si solo
    dijera "gracias", el chat perderia lo unico que la persona confirmo, y
    quien lo relea dentro de una semana no sabria que dijo que si.
    """
    etiqueta = ETIQUETAS.get(categoria, categoria)
    severidad = ETIQUETA_SEVERIDAD.get(clasificacion.final_severity, "")
    return f"{encabezado}\n\n{etiqueta} ({severidad})\n\nTe aviso por aquí cuando se atienda."


def _buscar(session: Session, cid: str, external_user_id: str) -> Classification | None:
    """Busca la clasificacion **comprobando que sea de quien responde**.

    El callback_data lo manda el cliente y se puede falsear: sin esta
    comprobacion, cualquiera que adivine un uuid confirmaria el reporte de otro.
    """
    try:
        import uuid as _uuid

        _uuid.UUID(cid)
    except (ValueError, AttributeError):
        return None

    return session.execute(
        select(Classification)
        .join(Report, Report.id == Classification.report_id)
        .where(Classification.id == cid, Report.external_user_id == external_user_id)
    ).scalar_one_or_none()


def handle_choice(session: Session, external_user_id: str, valor: str) -> tuple[str, list, bool]:
    """Aplica la eleccion.

    Devuelve el texto, los botones nuevos, y **si ese texto reemplaza al
    mensaje**. Lo tercero no es un detalle de presentacion: reescribir con
    "no encuentro ese reporte" borraria del chat la propuesta que la persona
    todavia tiene que contestar. Los avisos salen como aviso; solo lo que
    cierra la pregunta la reemplaza.
    """
    if valor.startswith(PREFIJO_SI):
        clasificacion = _buscar(session, valor[len(PREFIJO_SI) :], external_user_id)
        if clasificacion is None:
            return NO_ENCONTRADO, [], False
        if clasificacion.confirmed_at is not None:
            return YA_CONFIRMADO, [], False

        clasificacion.final_category = clasificacion.proposed_category
        clasificacion.final_severity = clasificacion.proposed_severity
        clasificacion.status = "confirmed"
        clasificacion.confirmed_at = datetime.now(UTC)
        _agrupar(session, clasificacion)
        return (
            _resumen(clasificacion, "Confirmado, gracias.", clasificacion.final_category),
            [],
            True,
        )

    if valor.startswith(PREFIJO_NO):
        clasificacion = _buscar(session, valor[len(PREFIJO_NO) :], external_user_id)
        if clasificacion is None:
            return NO_ENCONTRADO, [], False
        texto, opciones = opciones_de_categoria(clasificacion)
        return texto, opciones, True

    if valor.startswith(PREFIJO_CATEGORIA):
        resto = valor[len(PREFIJO_CATEGORIA) :]
        cid, _, indice = resto.rpartition(":")
        clasificacion = _buscar(session, cid, external_user_id)
        if clasificacion is None:
            return NO_ENCONTRADO, [], False

        if indice == "x":
            categoria = Category.NO_ES_REPORTE
        else:
            reales = categorias_reales()
            if not indice.isdigit() or int(indice) >= len(reales):
                return NO_ENCONTRADO, [], False
            categoria = reales[int(indice)]

        sin_propuesta = clasificacion.proposed_category is None
        clasificacion.final_category = categoria.value
        # La severidad propuesta se conserva: la persona corrigio la categoria,
        # no dijo nada de la urgencia, e inventarle una seria ponerle palabras.
        # Sin propuesta (el modelo fallo) va la intermedia: el caso necesita
        # una para ordenarse en la cola, y la media ni lo entierra ni lo vuelve
        # urgente sin que nadie lo haya visto. Quien despacha la ajusta.
        clasificacion.final_severity = clasificacion.proposed_severity or (
            SEVERIDAD_SIN_PROPUESTA.value
        )
        # Sin propuesta no hubo correccion: la persona eligio desde cero. Si
        # quedara "corrected", el tablero diria que corrigio al modelo.
        clasificacion.status = "chosen" if sin_propuesta else "corrected"
        clasificacion.confirmed_at = datetime.now(UTC)
        _agrupar(session, clasificacion)
        encabezado = (
            "Anotado, gracias."
            if sin_propuesta
            else "Corregido, gracias. Eso ayuda a que el sistema mejore."
        )
        return (
            _resumen(clasificacion, encabezado, clasificacion.final_category),
            [],
            True,
        )

    return NO_ENCONTRADO, [], False


def _agrupar(session: Session, clasificacion: Classification) -> None:
    """Agrupa el reporte ahora que su categoria la confirmo una persona.

    Aqui y no antes: agrupar por la categoria que **propuso** el modelo seria
    dejar que el modelo decida agrupaciones por la puerta de atras, y la
    agrupacion es justo lo que PLAN.md reserva para el codigo.

    Si falla, la confirmacion no se pierde: el reporte queda en `pending` de
    agrupacion y lo recoge la siguiente pasada. Perder una confirmacion humana
    por un fallo de agrupacion seria cambiar lo caro por lo barato.
    """
    from app import grouping

    reporte = session.get(Report, clasificacion.report_id)
    if reporte is None:
        return
    try:
        session.flush()
        grouping.group_report(session, reporte)
    except Exception:
        import logging

        logging.getLogger("smart_report.confirm").exception(
            "no se pudo agrupar el reporte %s", reporte.id
        )
        reporte.grouping_status = "pending"
