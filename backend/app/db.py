"""Motor y sesiones de base de datos."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app import db_guard
from app.config import settings

# pool_pre_ping evita servir con conexiones muertas tras un reinicio de la base.
engine: Engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=5)

# Se engancha aqui y no en cada sitio que borra: un guardia que hay que
# acordarse de llamar protege solo al que ya iba con cuidado. Asi cubre
# tambien a un script suelto, que es como se perdio un reporte real.
db_guard.install(engine)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Sesion por peticion. Revierte si el handler lanza.

    Sin el rollback explicito, una excepcion deja la conexion con una
    transaccion abierta que vuelve al pool y hace fallar a la siguiente
    peticion con un error que no tiene nada que ver.
    """
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Alias para las rutas. `Annotated` y no `= Depends(...)`: es la forma moderna
# de FastAPI y evita llamadas en los valores por defecto.
SesionBD = Annotated[Session, Depends(get_session)]
