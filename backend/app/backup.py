"""Respaldo de la base al mismo almacenamiento donde viven las fotos.

Sin esto el despliegue gratuito tiene un agujero grande: no hay respaldos
administrados, y todo vive en una maquina. Un disco que se pierde se lleva los
reportes, los casos y la evidencia de cada agrupacion.

Va a R2 y no al disco de al lado porque un respaldo en la misma maquina no es
un respaldo: protege del error humano, no del incendio.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app import storage
from app.config import settings

log = logging.getLogger("smart_report.backup")

PREFIJO = "respaldos/"

# Cuantos dias se guardan. Son unos megabytes cada uno y el nivel gratuito de
# R2 son 10 GB; el limite existe para que no crezca sin fin, no por espacio.
DIAS_QUE_SE_GUARDAN = 14


def _url_para_pg_dump() -> str:
    """`pg_dump` no entiende el dialecto de SQLAlchemy."""
    return settings.database_url.replace("postgresql+psycopg://", "postgresql://")


def volcar() -> bytes:
    """El volcado de la base, comprimido por el propio pg_dump.

    Formato `custom` y no SQL plano: se restaura con `pg_restore`, permite
    sacar una sola tabla, y ya viene comprimido.
    """
    with tempfile.TemporaryDirectory() as carpeta:
        destino = Path(carpeta) / "volcado.dump"
        resultado = subprocess.run(
            ["pg_dump", "--format=custom", "--file", str(destino), _url_para_pg_dump()],
            capture_output=True,
            timeout=600,
        )
        if resultado.returncode != 0:
            # El error va tal cual pero sin la URL, que lleva la contraseña.
            detalle = resultado.stderr.decode("utf-8", "replace")[:500]
            raise RuntimeError(f"pg_dump fallo: {detalle}")
        return destino.read_bytes()


def limpiar_viejos(corte: datetime | None = None) -> int:
    """Borra los respaldos que pasaron de la ventana.

    El corte se puede pasar para poder probar esto: la fecha de un objeto la
    pone el almacenamiento y no se puede falsear desde fuera.
    """
    if corte is None:
        corte = datetime.now(UTC) - timedelta(days=DIAS_QUE_SE_GUARDAN)
    cliente = storage.client()
    borrados = 0

    paginas = cliente.get_paginator("list_objects_v2").paginate(
        Bucket=settings.s3_bucket, Prefix=PREFIJO
    )
    for pagina in paginas:
        for objeto in pagina.get("Contents", []):
            if objeto["LastModified"] < corte:
                cliente.delete_object(Bucket=settings.s3_bucket, Key=objeto["Key"])
                borrados += 1
    return borrados


def respaldar() -> str:
    """Hace el respaldo y lo sube. Devuelve la clave del objeto."""
    datos = volcar()
    # Por dia y no por minuto: dos respaldos del mismo dia se pisan, que es lo
    # que se quiere. Reiniciar el servicio no debe llenar el bucket.
    clave = f"{PREFIJO}{datetime.now(UTC):%Y-%m-%d}.dump"
    storage.put(clave, datos, "application/octet-stream")

    viejos = limpiar_viejos()
    log.info("respaldo %s, %s bytes, %s viejos borrados", clave, len(datos), viejos)
    return clave


def main() -> int:
    from app import logging_setup

    logging_setup.configure()
    respaldar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
