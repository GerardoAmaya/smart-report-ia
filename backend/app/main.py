"""Punto de entrada de la API."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app import logging_setup
from app.config import settings
from app.db import engine
from app.health import build_health
from app.routes_auth import router as auth_router
from app.routes_board import router as board_router
from app.security import BodySizeLimitMiddleware, SecurityHeadersMiddleware, body_was_truncated
from app.webhook import router as webhook_router

logging_setup.configure()


def _secreto_de_sesion() -> str:
    """Clave para firmar la cookie.

    En produccion es obligatoria: sin ella, arrancar con una clave generada al
    vuelo cerraria la sesion de todos en cada reinicio, y peor, dos instancias
    firmarian distinto. En local se genera una y se avisa.
    """
    configurado = settings.session_secret.get_secret_value()
    if configurado:
        return configurado
    if settings.is_production:
        raise RuntimeError("SESSION_SECRET es obligatorio en produccion")

    import secrets as _secrets

    generado = _secrets.token_urlsafe(32)
    logging.getLogger("smart_report").warning(
        "SESSION_SECRET sin definir: se genero una al vuelo. Las sesiones se "
        "pierden en cada reinicio. Generar una con: openssl rand -hex 32"
    )
    return generado


app = FastAPI(title="Smart Report API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
    # La sesion viaja en cookie, asi que el navegador tiene que poder mandarla
    # en peticiones a otro origen. Con esto activo, allow_origins NO puede ser
    # "*": el navegador lo rechaza, y con razon.
    allow_credentials=True,
)

# La sesion va en cookie firmada. HttpOnly la deja fuera del alcance de
# cualquier script en la pagina, que es por donde se roban las sesiones.
app.add_middleware(
    SessionMiddleware,
    secret_key=_secreto_de_sesion(),
    max_age=settings.session_max_age_seconds,
    same_site="lax",
    # Solo por HTTPS en produccion. En local seria imposible entrar.
    https_only=settings.is_production,
)
app.add_middleware(SecurityHeadersMiddleware)

# Se agrega al final para que quede el mas externo: cortar un cuerpo enorme
# tiene que pasar antes de que nada mas lo toque.
app.add_middleware(BodySizeLimitMiddleware)

app.include_router(webhook_router)
app.include_router(auth_router)
app.include_router(board_router)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Un cuerpo cortado por el tope llega aca como JSON invalido.

    Sin esto el cliente recibiria un 422 que dice "JSON mal formado", que es
    cierto pero esconde la causa: el cuerpo era demasiado grande.
    """
    if body_was_truncated(request):
        return JSONResponse({"detail": "cuerpo demasiado grande"}, status_code=413)
    return JSONResponse({"detail": "peticion invalida"}, status_code=422)


@app.get("/health")
def health() -> dict:
    """Devuelve 200 incluso degradado.

    Un 503 aca hace que el orquestador reinicie el contenedor en bucle por un
    problema de datos que reiniciar no arregla. El estado va en el cuerpo.
    """
    return build_health(engine)
