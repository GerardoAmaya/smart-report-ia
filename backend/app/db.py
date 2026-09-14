"""Motor de base de datos compartido."""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.config import settings

# pool_pre_ping evita servir con conexiones muertas tras un reinicio de la base.
engine: Engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=5)
