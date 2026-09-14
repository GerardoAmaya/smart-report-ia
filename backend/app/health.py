"""Chequeo de salud real.

Comprueba las tres cosas sin las cuales el servicio no puede trabajar:
PostGIS instalado, esquema al dia y conexion con el modelo. Un chequeo que
solo mira si hay conexion no comprueba nada util.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app import storage
from app.config import settings

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

Check = dict[str, Any]


def safe_detail(exc: Exception) -> str:
    """Detalle de error apto para devolver al cliente.

    En dev sirve el mensaje entero. En produccion no: un OperationalError
    de psycopg nombra host, puerto y usuario de la base, y /health se
    consulta sin autenticar. Queda el tipo, que basta para saber que fallo.
    """
    if settings.is_production:
        return type(exc).__name__
    return f"{type(exc).__name__}: {exc}"


# Cache del sondeo al modelo: (momento, resultado).
_model_probe_cache: tuple[float, Check] | None = None


def head_revision() -> str | None:
    """Ultima migracion que existe en el repositorio.

    `script_location` en el ini es relativo al directorio de trabajo, que bajo
    uvicorn no es el mismo que al correr alembic a mano. Se fija absoluto.
    """
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


def check_database(engine: Engine) -> dict[str, Check]:
    """PostGIS y revision de esquema en una sola conexion."""
    head = head_revision()
    try:
        with engine.connect() as conn:
            version = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")
            ).scalar()
            applied = MigrationContext.configure(conn).get_current_revision()
    except Exception as exc:
        detail = safe_detail(exc)
        return {
            "postgis": {"ok": False, "detail": detail},
            "schema": {"ok": False, "detail": detail, "expected_revision": head},
        }

    return {
        "postgis": {
            "ok": version is not None,
            "version": version,
            "detail": None if version else "extension postgis no instalada",
        },
        "schema": {
            # Desfase en cualquier direccion es desfase: una base adelantada
            # respecto al codigo desplegado rompe igual que una atrasada.
            "ok": applied == head,
            "applied_revision": applied,
            "expected_revision": head,
            "detail": None if applied == head else f"esquema en {applied}, se esperaba {head}",
        },
    }


def _probe_model() -> Check:
    """Llamada minima a la API. No genera tokens: solo lista modelos."""
    if not settings.anthropic_api_key.get_secret_value():
        return {"ok": False, "detail": "ANTHROPIC_API_KEY sin definir"}
    try:
        from anthropic import Anthropic

        client = Anthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
            timeout=settings.model_probe_timeout_seconds,
            max_retries=0,
        )
        client.models.list(limit=1)
    except Exception as exc:
        return {"ok": False, "detail": safe_detail(exc)}
    return {"ok": True, "detail": None}


def check_model(now: float | None = None) -> Check:
    global _model_probe_cache
    now = time.monotonic() if now is None else now

    if _model_probe_cache is not None:
        probed_at, cached = _model_probe_cache
        if now - probed_at < settings.model_probe_ttl_seconds:
            return {**cached, "cached": True}

    result = _probe_model()
    _model_probe_cache = (now, result)
    return {**result, "cached": False}


def reset_model_cache() -> None:
    """Usado por las pruebas para no arrastrar estado entre casos."""
    global _model_probe_cache
    _model_probe_cache = None


def build_health(engine: Engine) -> dict[str, Any]:
    checks: dict[str, Check] = dict(check_database(engine))
    checks["model"] = check_model()
    # Desde la fase 2 el almacenamiento es una de las cosas sin las cuales el
    # servicio no puede trabajar: sin bucket, las fotos se quedan en la cola.
    checks["storage"] = storage.check()

    issues = [
        f"{name}: {check.get('detail') or 'fallo sin detalle'}"
        for name, check in checks.items()
        if not check["ok"]
    ]

    return {
        "status": "degraded" if issues else "ok",
        "environment": settings.environment,
        "schema_revision": checks["schema"].get("applied_revision"),
        "checks": checks,
        "issues": issues,
    }
