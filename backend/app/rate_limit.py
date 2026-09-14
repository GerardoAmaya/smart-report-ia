"""Limites de uso, con el contador en Postgres.

La cola vive en Postgres y los limites tambien: un segundo almacen es
infraestructura que hay que desplegar, vigilar y explicar.

Ventana fija y no deslizante a proposito. Una ventana deslizante es mas justa
en el borde, pero cuesta guardar cada marca de tiempo y contarlas; la fija es
un UPSERT sobre la clave primaria, que es lo unico que cabe dentro del segundo
que tiene el webhook para responder.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

# Parametros ligados, nunca interpolacion: `scope` y `key` vienen de la
# peticion, y una f-string aca seria inyeccion directa.
_HIT = text(
    """
    INSERT INTO rate_limit_buckets (scope, key, window_start, count)
    VALUES (:scope, :key, :window_start, 1)
    ON CONFLICT (scope, key, window_start)
    DO UPDATE SET count = rate_limit_buckets.count + 1
    RETURNING count
    """
)

_SWEEP = text("DELETE FROM rate_limit_buckets WHERE window_start < :corte")

# Probabilidad de barrer ventanas viejas en una peticion dada. Barrer siempre
# agrega un DELETE a cada request; no barrer nunca hace crecer la tabla sin
# fin. Una de cada cien la mantiene chica sin costo perceptible.
_SWEEP_PROBABILITY = 0.01


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    count: int
    limit: int
    retry_after_seconds: int


def window_start(now: datetime, window_seconds: int) -> datetime:
    """Inicio de la ventana fija que contiene a `now`."""
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % window_seconds), tz=UTC)


def hit(
    session: Session,
    *,
    scope: str,
    key: str,
    limit: int,
    window_seconds: int,
    now: datetime | None = None,
) -> RateLimitResult:
    """Cuenta una peticion y dice si pasa.

    Cuenta siempre, incluso cuando ya se paso: asi el que insiste sigue viendo
    la puerta cerrada durante toda la ventana en vez de colar una por ciclo.
    """
    now = now or datetime.now(UTC)
    inicio = window_start(now, window_seconds)

    count = session.execute(_HIT, {"scope": scope, "key": key, "window_start": inicio}).scalar_one()

    if random.random() < _SWEEP_PROBABILITY:
        session.execute(_SWEEP, {"corte": inicio - timedelta(seconds=window_seconds)})

    restante = int((inicio + timedelta(seconds=window_seconds) - now).total_seconds())
    return RateLimitResult(
        allowed=count <= limit,
        count=count,
        limit=limit,
        retry_after_seconds=max(1, restante),
    )
