"""Punto de entrada de la API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import engine
from app.health import build_health

app = FastAPI(title="Smart Report API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """Devuelve 200 incluso degradado.

    Un 503 aca hace que el orquestador reinicie el contenedor en bucle por un
    problema de datos que reiniciar no arregla. El estado va en el cuerpo.
    """
    return build_health(engine)
