"""Las rutas del asistente: el chat del tablero y la comparacion de dudosos.

Las dos piden solo permiso de **ver**: el asistente lee y sugiere, nunca
despacha. Comparten un tope diario por persona, porque las dos gastan saldo del
modelo y el invitado es publico.
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app import asistente, comparar, rate_limit
from app.auth import requiere
from app.config import settings
from app.db import SesionBD
from app.models import Report, User
from app.permissions import Permission, Role
from app.security import rate_limit_key

log = logging.getLogger("smart_report.asistente")

router = APIRouter(prefix="/board", tags=["asistente"])

Ver = Annotated[User, Depends(requiere(Permission.VER))]

UN_DIA = 24 * 60 * 60


def gastar_consulta(session, usuario: User) -> int:
    """Cuenta una consulta y corta si se paso del tope del dia.

    El dia es el de El Salvador: se reinicia a medianoche de alli. En UTC se
    reiniciaba a las seis de la tarde, a mitad de la jornada. Se cuenta antes
    de llamar al modelo, porque lo caro es la llamada, no la respuesta.
    """
    limite = (
        settings.assistant_daily_limit_demo
        if usuario.role == Role.DEMO.value
        else settings.assistant_daily_limit
    )
    resultado = rate_limit.hit(
        session,
        scope="asistente",
        key=rate_limit_key(f"asistente:{usuario.email}"),
        limit=limite,
        window_seconds=UN_DIA,
        zona=asistente.ZONA,
    )
    session.commit()
    if not resultado.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Llegaste al tope de {limite} consultas al asistente por hoy. "
            "Se renueva a la medianoche.",
            headers={"Retry-After": str(resultado.retry_after_seconds)},
        )
    return limite - resultado.count


# --- Comparar dos fotos de una agrupacion dudosa ---


@router.post("/reports/{report_id}/compare")
def comparar_fotos(report_id: UUID, usuario: Ver, session: SesionBD) -> dict:
    reporte = session.get(Report, report_id)
    if reporte is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No existe ese reporte.")
    if reporte.grouping_status != "doubtful":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Solo se comparan los reportes que quedaron en duda."
        )
    # Antes de gastar: si falta el candidato o una foto, no tiene sentido
    # cobrar la consulta del dia.
    try:
        comparar.candidato(session, reporte)
    except comparar.NoSePuedeComparar as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    restantes = gastar_consulta(session, usuario)
    try:
        resultado = comparar.comparar(session, reporte)
    except comparar.NoSePuedeComparar as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except Exception as exc:
        log.exception("fallo la comparacion del reporte %s", report_id)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "No se pudo comparar ahora. Prueba de nuevo en un rato."
        ) from exc

    log.info(
        "comparacion %s vs %s: %s, %s+%s tokens, USD %s, %s ms",
        report_id,
        resultado.candidato_id,
        resultado.comparacion.sugerencia,
        resultado.input_tokens,
        resultado.output_tokens,
        resultado.cost_usd,
        resultado.latency_ms,
    )
    return {
        **resultado.comparacion.model_dump(),
        "candidate_report_id": resultado.candidato_id,
        "remaining_today": restantes,
    }


# --- El chat ---


class Mensaje(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class Pregunta(BaseModel):
    messages: list[Mensaje] = Field(min_length=1, max_length=30)

    @field_validator("messages")
    @classmethod
    def alterna_y_termina_en_pregunta(cls, mensajes: list[Mensaje]) -> list[Mensaje]:
        # El historial lo manda el navegador: se comprueba que tenga forma de
        # conversacion antes de pagar por ella.
        if mensajes[0].role != "user" or mensajes[-1].role != "user":
            raise ValueError("la conversación empieza y termina con una pregunta")
        for antes, despues in zip(mensajes, mensajes[1:], strict=False):
            if antes.role == despues.role:
                raise ValueError("los mensajes tienen que alternar")
        return mensajes


@router.post("/asistente")
def preguntar(pregunta: Pregunta, usuario: Ver, session: SesionBD) -> dict:
    restantes = gastar_consulta(session, usuario)
    try:
        respuesta = asistente.responder(session, [m.model_dump() for m in pregunta.messages])
    except asistente.SeAcabaronLasVueltas as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "La pregunta necesitó demasiadas consultas. Prueba a hacerla más concreta.",
        ) from exc
    except Exception as exc:
        log.exception("fallo el asistente")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "El asistente no pudo contestar ahora. Prueba de nuevo en un rato.",
        ) from exc
    return {"answer": respuesta.texto, "remaining_today": restantes}
