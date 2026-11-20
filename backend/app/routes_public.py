"""Lo unico que se ve sin entrar: lo que la pantalla de entrada necesita saber.

Hoy es un dato: si el invitado puede despachar, para que la pantalla diga la
verdad sobre el (en produccion solo mira; en local y en las E2E, despacha).

**Nada de datos del sistema.** Hubo cifras agregadas —reportes, casos,
personas avisadas— para adornar la entrada, y se quitaron: la entrada es una
puerta que quien despacha cruza todos los dias, y un dato que no se muestra
tampoco hace falta publicarlo. Lo que se agregue aqui lo puede pedir cualquiera.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/config")
def configuracion() -> dict:
    return {"demo_can_dispatch": settings.demo_can_dispatch}
