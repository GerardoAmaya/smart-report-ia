"""Entorno de Alembic.

La URL sale siempre de la configuracion, nunca del ini. Si el ini gana, las
migraciones corren contra una base distinta a la que usa la aplicacion y el
sintoma aparece lejos de la causa.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Sin modelos todavia: la fase 0 solo instala la extension.
target_metadata = None

# PostGIS crea sus propias tablas e indices. Sin este filtro, el autogenerate
# propone borrarlos en la siguiente migracion.
POSTGIS_OWNED = {"spatial_ref_sys", "geography_columns", "geometry_columns", "raster_columns"}


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    if type_ == "table" and name in POSTGIS_OWNED:
        return False
    return not (type_ == "index" and name and name.startswith("idx_"))


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
