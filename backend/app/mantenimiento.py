"""Lo que hay que correr todos los dias, corriendo dentro del despliegue.

**No es un cron del servidor.** Es el mismo motivo por el que las migraciones
van en `start.sh` y no en un hook del proveedor: lo que hay que acordarse de
configurar aparte es lo que un dia no esta, y falla en silencio. Aqui es un
servicio mas —sale en `docker compose ps`, sus registros estan con los demas—
y si se cae, se ve.

La politica de retencion existia desde la fase 2 y se corria a mano. Una
politica escrita y sin aplicar es peor que no tenerla: promete un borrado que
no ocurre.
"""

from __future__ import annotations

import logging
import time

from app import logging_setup, retention
from app.db import SessionLocal

log = logging.getLogger("smart_report.mantenimiento")

CADA_SEGUNDOS = 24 * 60 * 60


def una_pasada() -> None:
    """Retencion y respaldo, cada uno con su propio fallo.

    Separados a proposito: que el respaldo falle no puede impedir que la
    retencion borre lo que ya deberia estar borrado, ni al reves.
    """
    try:
        with SessionLocal() as session:
            borradas = retention.run(session)
            sueltos = retention.purge_orphans(session)
        log.info("retencion aplicada: %s, %s huerfanos", borradas, sueltos)
    except Exception:
        log.exception("fallo la retencion")

    try:
        # Se importa aqui y no arriba: si `pg_dump` no esta en la imagen, el
        # servicio tiene que seguir aplicando la retencion igual.
        from app import backup

        backup.respaldar()
    except Exception:
        log.exception("fallo el respaldo")


def main() -> int:
    logging_setup.configure()
    log.info("mantenimiento arriba, una pasada cada %s horas", CADA_SEGUNDOS // 3600)

    while True:
        # Una al arrancar: si el respaldo esta roto, se sabe al desplegar y no
        # veinticuatro horas despues.
        una_pasada()
        time.sleep(CADA_SEGUNDOS)


if __name__ == "__main__":
    raise SystemExit(main())
