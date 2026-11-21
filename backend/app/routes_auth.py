"""Rutas de entrada y salida del tablero."""

from __future__ import annotations

import logging
import re
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import RedirectResponse

from app import auth, images, storage
from app.config import settings
from app.db import SesionBD
from app.models import User
from app.permissions import Role, permisos_de

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
    # La foto de Google se refresca en cada entrada: si la persona la cambia
    # alla, aqui se ve la nueva. Solo https: es una URL que pinta el navegador.
    foto = info.get("picture")
    if isinstance(foto, str) and foto.startswith("https://") and len(foto) <= 500:
        usuario.google_picture_url = foto

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


def avatar_url(usuario: User) -> str | None:
    """La foto que se enseña: la subida manda, luego la de Google, luego nada.

    La subida va firmada y caduca como las demas del bucket: el bucket no es
    publico y un avatar no es motivo para abrirlo.
    """
    if usuario.avatar_key:
        return storage.presigned_url(usuario.avatar_key)
    return usuario.google_picture_url


def _perfil(usuario: User) -> dict:
    permisos = permisos_de(usuario.role)
    return {
        "email": usuario.email,
        "role": usuario.role,
        "display_name": usuario.display_name,
        "permissions": sorted(p.value for p in permisos),
        "avatar_url": avatar_url(usuario),
        # Para ofrecer "Quitar" solo si hay algo propio que quitar: la de
        # Google no vive aqui.
        "avatar_propio": bool(usuario.avatar_key),
        "last_login_at": usuario.last_login_at.isoformat() if usuario.last_login_at else None,
    }


# --- Mi perfil ---

# Sin < ni >: el nombre se pinta en el tablero de otros, y aunque React escapa,
# un nombre con etiquetas no es un nombre.
NOMBRE_VALIDO = re.compile(r"^[^<>]{1,64}$")


def _editable(usuario: User, session) -> User:
    """El usuario de esta sesion, cargado en la sesion de base de la peticion.

    **El invitado no edita nada de su perfil**: es una cuenta que comparte
    todo el publico, y un nombre o una foto suyos serian grafiti que ve el
    siguiente que entra.
    """
    if usuario.role == Role.DEMO.value:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "La cuenta de prueba es compartida: su nombre y su foto no se cambian.",
        )
    propio = session.get(User, usuario.id)
    if propio is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "esta cuenta ya no tiene acceso")
    return propio


@router.patch("/yo")
def cambiar_perfil(
    usuario: Annotated[User, Depends(auth.current_user)],
    session: SesionBD,
    display_name: Annotated[str, Body(embed=True)],
) -> dict:
    propio = _editable(usuario, session)
    nombre = " ".join(display_name.split())
    if not NOMBRE_VALIDO.match(nombre):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "El nombre tiene que tener entre 1 y 64 caracteres, sin < ni >.",
        )
    propio.display_name = nombre
    session.commit()
    return _perfil(propio)


@router.post("/yo/foto")
async def subir_foto(
    usuario: Annotated[User, Depends(auth.current_user)],
    session: SesionBD,
    archivo: Annotated[UploadFile, File()],
) -> dict:
    propio = _editable(usuario, session)
    datos = await archivo.read()
    if len(datos) > settings.max_photo_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "La foto es demasiado grande."
        )
    try:
        # Abriendola, como las demas: una cabecera JPEG con basura detras pasa
        # cualquier numero magico y revienta despues.
        images.validate(datos)
        recortada = images.avatar(datos)
    except images.ImagenInvalida as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Eso no es una imagen válida.") from exc

    # Clave propia y nueva en cada subida: con la misma clave, el navegador
    # seguiria enseñando la foto vieja que tiene en cache.
    clave = f"avatares/{propio.id}/{uuid.uuid4()}.jpg"
    storage.put(clave, recortada, "image/jpeg")
    vieja = propio.avatar_key
    propio.avatar_key = clave
    session.commit()
    if vieja:
        storage.delete(vieja)
    return _perfil(propio)


@router.delete("/yo/foto")
def quitar_foto(
    usuario: Annotated[User, Depends(auth.current_user)],
    session: SesionBD,
) -> dict:
    propio = _editable(usuario, session)
    vieja = propio.avatar_key
    propio.avatar_key = None
    session.commit()
    # Se borra de verdad: una foto de perfil quitada que sigue en el bucket es
    # una foto que la persona creyo haber retirado.
    if vieja:
        storage.delete(vieja)
    return _perfil(propio)
