"""Rutas de entrada y salida del tablero."""

from __future__ import annotations

import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app import auth
from app.config import settings
from app.db import SesionBD
from app.models import User
from app.permissions import PERMISOS, Role

log = logging.getLogger("smart_report.auth")

router = APIRouter(prefix="/auth", tags=["auth"])

ESTADO_OAUTH = "oauth_state"


def _oauth():
    """Cliente de Google, construido al vuelo.

    Al vuelo y no al importar: sin credenciales configuradas el modulo tiene que
    poder importarse igual, o las pruebas y el arranque en local fallarian por
    una funcionalidad que no estan usando.
    """
    from authlib.integrations.starlette_client import OAuth

    if not settings.google_client_id or not settings.google_client_secret.get_secret_value():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "la entrada con Google no esta configurada",
        )

    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret.get_secret_value(),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth.google


@router.get("/google/start")
async def google_start(request: Request):
    """Manda al navegador a Google."""
    cliente = _oauth()
    # `state` contra CSRF: Google lo devuelve tal cual y se compara. Sin esto,
    # alguien puede hacer que una victima complete un intercambio ajeno y quede
    # con la sesion de otra cuenta.
    estado = secrets.token_urlsafe(32)
    request.session[ESTADO_OAUTH] = estado
    return await cliente.authorize_redirect(request, settings.oauth_redirect_url, state=estado)


@router.get("/google/callback")
async def google_callback(request: Request, session: SesionBD):
    """Vuelta de Google. **Aqui se decide si entra o no.**"""
    esperado = request.session.pop(ESTADO_OAUTH, None)
    recibido = request.query_params.get("state")
    if not esperado or esperado != recibido:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "el intercambio no coincide")

    cliente = _oauth()
    try:
        token = await cliente.authorize_access_token(request)
    except Exception as exc:
        log.warning("Google rechazo el intercambio: %s", type(exc).__name__)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no se pudo verificar con Google") from exc

    info = token.get("userinfo") or {}
    correo = (info.get("email") or "").strip().lower()

    # Un correo sin verificar no prueba nada: cualquiera puede poner el correo
    # ajeno en un perfil.
    if not correo or not info.get("email_verified"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google no devolvio un correo verificado")

    usuario = auth.autorizado(session, correo)
    if usuario is None:
        # Google dice quien es; entrar lo decide la tabla.
        log.warning("intento de entrada de %s, que no esta permitido", correo)
        return RedirectResponse(f"{settings.frontend_url}/entrar?error=sin_acceso")

    if info.get("name") and not usuario.display_name:
        usuario.display_name = info["name"][:128]

    auth.abrir_sesion(request, session, usuario)
    return RedirectResponse(settings.frontend_url)


@router.post("/demo")
def entrar_de_prueba(
    request: Request,
    password: Annotated[str, Body(embed=True)],
    session: SesionBD,
) -> dict:
    """Entrada del usuario de prueba, con contraseña.

    Existe porque el tablero es la mitad del proyecto y uno que nadie puede ver
    no se puede mostrar. Ese usuario **no puede borrar**: va a entrar gente a
    tocar todo, que para eso esta.
    """
    if not auth.password_de_prueba_valida(password):
        # El mismo mensaje y el mismo codigo pase lo que pase: distinguir
        # "usuario no existe" de "contraseña mala" le dice a quien prueba cual
        # de las dos mitades acerto.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "contraseña incorrecta")

    usuario = auth.asegurar_usuario_de_prueba(session)
    if usuario is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "el usuario de prueba no esta configurado"
        )

    auth.abrir_sesion(request, session, usuario)
    return _perfil(usuario)


@router.post("/salir")
def salir(request: Request) -> dict:
    auth.cerrar_sesion(request)
    return {"ok": True}


@router.get("/yo")
def yo(usuario: Annotated[User, Depends(auth.current_user)]) -> dict:
    """Quien soy y que puedo. Lo usa el tablero para esconder lo que no puede.

    Esconder no es impedir: el permiso se comprueba igual en cada endpoint. Esto
    es para que la interfaz no ofrezca botones que van a fallar.
    """
    return _perfil(usuario)


def _perfil(usuario: User) -> dict:
    permisos = PERMISOS.get(Role(usuario.role), frozenset())
    return {
        "email": usuario.email,
        "role": usuario.role,
        "display_name": usuario.display_name,
        "permissions": sorted(p.value for p in permisos),
    }
