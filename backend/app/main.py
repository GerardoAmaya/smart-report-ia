"""Punto de entrada de la API."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import engine
from app.health import build_health
from app.security import BodySizeLimitMiddleware, SecurityHeadersMiddleware, body_was_truncated
from app.webhook import router as webhook_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="Smart Report API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)

# Se agrega al final para que quede el mas externo: cortar un cuerpo enorme
# tiene que pasar antes de que nada mas lo toque.
app.add_middleware(BodySizeLimitMiddleware)

app.include_router(webhook_router)


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
