"""El tablero se actualiza sin recargar.

Server-Sent Events y no WebSocket: esto solo va del servidor al navegador —el
tablero escucha, no habla— y SSE viaja sobre HTTP normal, atraviesa proxies sin
configurar nada, y el navegador reconecta solo cuando se corta. Un WebSocket
seria maquinaria para una conversacion que no existe.

El aviso sale de `LISTEN/NOTIFY` de Postgres, que es el mismo sitio donde vive
la cola. No hay Redis ni bus de mensajes: cuando el trabajador guarda una foto
en su proceso y la API la tiene que enseñar en otro, Postgres ya esta en medio
de los dos.

**Se manda solo "algo cambio aqui", nunca la fila.** El cliente pide lo que
necesite. Mandar el dato por el flujo obligaria a mantener dos formas de leer lo
mismo, y la segunda se queda vieja.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.auth import current_user
from app.config import settings
from app.models import User
from app.permissions import Permission

log = logging.getLogger("smart_report.stream")

router = APIRouter(prefix="/board", tags=["board"])

CANAL = "smart_report_cambios"

# Cada cuanto se manda un latido si no pasa nada. Sin el, un proxy que corta
# conexiones inactivas tira el flujo a los dos minutos y el tablero se queda
# quieto sin que nadie se entere.
LATIDO_SEGUNDOS = 20


def _url_directa() -> str:
    """URL sin el dialecto de SQLAlchemy: psycopg la quiere cruda."""
    return settings.database_url.replace("postgresql+psycopg://", "postgresql://")


async def _eventos(request: Request) -> AsyncIterator[str]:
    """Escucha a Postgres y reenvia lo que llegue, con latidos entremedio."""
    # Conexion propia y no del pool: LISTEN ocupa la conexion entera mientras
    # escucha, y devolverla al pool con una escucha abierta contamina a quien la
    # tome despues.
    conn = await psycopg.AsyncConnection.connect(_url_directa(), autocommit=True)
    try:
        await conn.execute(f"LISTEN {CANAL}")
        # Uno al abrir: el cliente sabe que el flujo esta vivo sin esperar a que
        # cambie algo, y puede distinguir "conectado y en silencio" de "colgado".
        yield "event: abierto\ndata: {}\n\n"

        while True:
            if await request.is_disconnected():
                break

            # El plazo lo pone psycopg, no `asyncio.wait_for`. Con `wait_for`
            # el vencimiento **cancela** al generador de avisos, que se cierra:
            # la siguiente lectura levantaba `StopAsyncIteration` y el flujo se
            # moria en el primer latido. El navegador reconectaba solo, asi que
            # parecia funcionar; lo que se perdia eran los cambios ocurridos en
            # el hueco entre la muerte y la reconexion.
            oyo_algo = False
            async for aviso in conn.notifies(timeout=LATIDO_SEGUNDOS):
                oyo_algo = True
                try:
                    datos = json.loads(aviso.payload)
                except json.JSONDecodeError:
                    continue
                yield f"event: cambio\ndata: {json.dumps(datos)}\n\n"

            if not oyo_algo:
                # Comentario SSE: mantiene viva la conexion sin generar un
                # evento que el cliente tenga que interpretar.
                yield ": latido\n\n"
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("el flujo de cambios se corto")
    finally:
        await conn.close()


@router.get("/stream")
async def stream(
    request: Request,
    usuario: Annotated[User, Depends(current_user)],
) -> StreamingResponse:
    """Flujo de cambios para el tablero.

    Pide sesion como todo lo demas: quien no puede ver el tablero tampoco puede
    enterarse de lo que cambia en el.
    """
    from app.permissions import puede

    if not puede(usuario.role, Permission.VER):
        from fastapi import HTTPException, status

        raise HTTPException(status.HTTP_403_FORBIDDEN, "tu cuenta no puede ver")

    return StreamingResponse(
        _eventos(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Sin esto, un proxy que acumula respuesta no entrega nada hasta el
            # final, y el flujo deja de ser un flujo.
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
