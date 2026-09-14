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
    Category.ESPACIO_PUBLICO: "Parque o espacio publico",
    Category.NO_ES_REPORTE: "No es un reporte",
}

ETIQUETA_SEVERIDAD: dict[str, str] = {
    Severity.ALTA: "urgente",
    Severity.MEDIA: "atencion",
    Severity.BAJA: "sin urgencia",
}

GRACIAS = "Gracias, quedo confirmado."
CORREGIDO = "Corregido, gracias. Eso ayuda a que el sistema mejore."
YA_CONFIRMADO = "Ese reporte ya estaba confirmado."
NO_ENCONTRADO = "No encuentro ese reporte."


def pregunta(clasificacion: Classification) -> tuple[str, list[tuple[str, str]]]:
    """El texto y los botones para confirmar una propuesta."""
    etiqueta = ETIQUETAS.get(clasificacion.proposed_category, clasificacion.proposed_category)
    severidad = ETIQUETA_SEVERIDAD.get(clasificacion.proposed_severity, "")

    texto = (
        f"Revise tu reporte y creo que es:\n\n"
        f"**{etiqueta}** ({severidad})\n"
        f"{clasificacion.proposed_reason}\n\n"
        f"¿Es correcto?"
    )
    opciones = [
        ("Si, es correcto", f"{PREFIJO_SI}{clasificacion.id}"),
        ("No, es otra cosa", f"{PREFIJO_NO}{clasificacion.id}"),
    ]
    return texto, opciones


def opciones_de_categoria(clasificacion: Classification) -> tuple[str, list[tuple[str, str]]]:
    """La lista de categorias, para cuando la persona corrige."""
    texto = "¿Que es entonces?"
    # Se numera por posicion y no por nombre: el uuid ya ocupa 36 de los 64
    # bytes que Telegram permite en callback_data.
    opciones = [
        (ETIQUETAS[c], f"{PREFIJO_CATEGORIA}{clasificacion.id}:{i}")
        for i, c in enumerate(categorias_reales())
    ]
    opciones.append((ETIQUETAS[Category.NO_ES_REPORTE], f"{PREFIJO_CATEGORIA}{clasificacion.id}:x"))
    return texto, opciones


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


def handle_choice(session: Session, external_user_id: str, valor: str) -> tuple[str, list]:
    """Aplica la eleccion. Devuelve el texto de respuesta y botones nuevos."""
    if valor.startswith(PREFIJO_SI):
        clasificacion = _buscar(session, valor[len(PREFIJO_SI) :], external_user_id)
        if clasificacion is None:
            return NO_ENCONTRADO, []
        if clasificacion.confirmed_at is not None:
            return YA_CONFIRMADO, []

        clasificacion.final_category = clasificacion.proposed_category
        clasificacion.final_severity = clasificacion.proposed_severity
        clasificacion.status = "confirmed"
        clasificacion.confirmed_at = datetime.now(UTC)
        _agrupar(session, clasificacion)
        return GRACIAS, []

    if valor.startswith(PREFIJO_NO):
        clasificacion = _buscar(session, valor[len(PREFIJO_NO) :], external_user_id)
        if clasificacion is None:
            return NO_ENCONTRADO, []
        texto, opciones = opciones_de_categoria(clasificacion)
        return texto, opciones

    if valor.startswith(PREFIJO_CATEGORIA):
        resto = valor[len(PREFIJO_CATEGORIA) :]
        cid, _, indice = resto.rpartition(":")
        clasificacion = _buscar(session, cid, external_user_id)
        if clasificacion is None:
            return NO_ENCONTRADO, []

        if indice == "x":
            categoria = Category.NO_ES_REPORTE
        else:
            reales = categorias_reales()
            if not indice.isdigit() or int(indice) >= len(reales):
                return NO_ENCONTRADO, []
            categoria = reales[int(indice)]

        clasificacion.final_category = categoria.value
        # La severidad propuesta se conserva: la persona corrigio la categoria,
        # no dijo nada de la urgencia, e inventarle una seria ponerle palabras.
        clasificacion.final_severity = clasificacion.proposed_severity
        clasificacion.status = "corrected"
        clasificacion.confirmed_at = datetime.now(UTC)
        _agrupar(session, clasificacion)
        return CORREGIDO, []

    return NO_ENCONTRADO, []


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
