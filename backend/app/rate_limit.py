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
from datetime import UTC, datetime, timedelta, tzinfo

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

# Cada ambito barre **solo lo suyo**. Sin el filtro, una peticion del webhook
# (ventana de un minuto) borraba los contadores diarios del asistente, que
# empiezan a medianoche, y el tope diario se reiniciaba al azar.
_SWEEP = text("DELETE FROM rate_limit_buckets WHERE scope = :scope AND window_start < :corte")

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


def ahora() -> datetime:
    """Momento actual, en una funcion propia para poder fijarlo al probar.

    La ventana es fija y arranca en el reloj de pared, asi que una prueba
    que cruce el borde veria el contador reiniciarse a mitad. Es raro, pero
    una prueba de seguridad que falla una vez cada tanto enseña a ignorar el
    rojo, que es peor que la prueba misma.
    """
    return datetime.now(UTC)


def window_start(now: datetime, window_seconds: int, zona: tzinfo | None = None) -> datetime:
    """Inicio de la ventana fija que contiene a `now`.

    Sin zona, las ventanas se alinean al reloj UTC: para las de un minuto o una
    hora da igual. Con zona, se alinean al reloj de alli: un tope "por dia" que
    empezaba a medianoche UTC se reiniciaba a las seis de la tarde en El
    Salvador, a mitad de la jornada de quien despacha.
    """
    if zona is None:
        epoch = int(now.timestamp())
        return datetime.fromtimestamp(epoch - (epoch % window_seconds), tz=UTC)
    # Se corre el reloj al de la zona, se redondea alli y se vuelve a UTC.
    desfase = now.astimezone(zona).utcoffset() or timedelta(0)
    local = int((now + desfase).timestamp())
    return datetime.fromtimestamp(local - (local % window_seconds), tz=UTC) - desfase


def hit(
    session: Session,
    *,
    scope: str,
    key: str,
    limit: int,
    window_seconds: int,
    now: datetime | None = None,
    zona: tzinfo | None = None,
) -> RateLimitResult:
    """Cuenta una peticion y dice si pasa.

    Cuenta siempre, incluso cuando ya se paso: asi el que insiste sigue viendo
    la puerta cerrada durante toda la ventana en vez de colar una por ciclo.
    `zona` alinea la ventana al reloj local (ver `window_start`).
    """
    now = now or ahora()
    inicio = window_start(now, window_seconds, zona)

    count = session.execute(_HIT, {"scope": scope, "key": key, "window_start": inicio}).scalar_one()

    if random.random() < _SWEEP_PROBABILITY:
        session.execute(
            _SWEEP, {"scope": scope, "corte": inicio - timedelta(seconds=window_seconds)}
        )

    restante = int((inicio + timedelta(seconds=window_seconds) - now).total_seconds())
    return RateLimitResult(
        allowed=count <= limit,
        count=count,
        limit=limit,
        retry_after_seconds=max(1, restante),
    )
