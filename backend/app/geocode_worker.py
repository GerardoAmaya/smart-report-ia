"""Cola de direcciones.

La tercera cola del mismo trabajador, con la misma forma que las otras dos:
`FOR UPDATE SKIP LOCKED`, tope de intentos y espera creciente. La cola **es la
propia fila del reporte** —`geocoded_at` nulo con ubicacion puesta— igual que la
de fotos es la tabla de fotos: el trabajo es la fila, y una tabla de trabajos
aparte seria infraestructura para lo que ya cabe en un indice parcial.

Va aqui y no en el webhook por la razon de siempre: es red. Y no va en el aviso
porque un aviso que espera a un tercero es un aviso que se puede perder por algo
que ya se sabia.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from geoalchemy2 import Geometry
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from app import geocode
from app.config import settings
from app.models import Report

log = logging.getLogger("smart_report.geocode")


def claim(session: Session, limite: int) -> list[tuple[Report, float, float]]:
    """Toma reportes sin direccion, con sus coordenadas."""
    filas = session.execute(
        select(
            Report,
            func.ST_Y(cast(Report.location, Geometry)),
            func.ST_X(cast(Report.location, Geometry)),
        )
        .where(
            Report.geocoded_at.is_(None),
            Report.location.is_not(None),
            Report.geocode_attempts < settings.geocode_max_attempts,
        )
        .order_by(Report.created_at)
        .limit(limite)
        .with_for_update(skip_locked=True, of=Report)
    ).all()
    return [(r, lat, lon) for r, lat, lon in filas]


def run_once(session: Session) -> int:
    """Resuelve un lote. Devuelve cuantos se intentaron."""
    if not settings.geocode_enabled:
        return 0

    pendientes = claim(session, settings.geocode_batch_size)
    if not pendientes:
        return 0

    hechos = 0
    for indice, (reporte, lat, lon) in enumerate(pendientes):
        if indice:
            # El tope de una por segundo se respeta desde el codigo y no de
            # palabra: pasarse hace que el servicio bloquee la IP entera, y
            # eso se descubre tarde y afecta a todos los reportes.
            time.sleep(settings.geocode_min_interval_seconds)

        reporte.geocode_attempts += 1
        try:
            direccion = geocode.reverse(lat, lon)
        except geocode.FalloTransitorio as exc:
            # No se marca `geocoded_at`: sigue en la cola. Al llegar al tope de
            # intentos deja de tomarse, y el reporte se queda con su enlace al
            # punto, que nunca dejo de ser correcto.
            log.warning("reporte %s sin direccion todavia: %s", reporte.id, exc)
            session.commit()
            continue

        reporte.address_text = direccion
        # Se marca aunque no haya direccion: "se intento y el sitio no tiene
        # nombre" es una respuesta, y reintentarla llega a la misma.
        reporte.geocoded_at = datetime.now(UTC)
        hechos += 1
        session.commit()

    if hechos:
        log.info("%s reportes con direccion resuelta", hechos)
    return hechos
