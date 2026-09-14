"""enable postgis

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")


def downgrade() -> None:
    """Quita PostGIS **solo si esta migracion fue quien lo puso**.

    Reversible a proposito: CI comprueba ida y vuelta en cada commit, y una
    migracion que no baja se descubre el dia que hay que revertir en produccion.

    Pero la imagen oficial de PostGIS instala ademas `postgis_topology` y
    `postgis_tiger_geocoder`, que dependen de `postgis`. Ahi el DROP falla, y
    forzarlo con CASCADE destruiria dos extensiones que esta migracion nunca
    creo — revertir un cambio no puede llevarse por delante lo que ya estaba.

    Asi que se intenta bajar y, si hay dependientes, se deja puesto y se dice.
    En una base limpia baja de verdad; en la imagen de PostGIS no habia nada que
    bajar.

    Esto fallaba solo en CI: la base de desarrollo la crea la imagen con las
    cinco extensiones, y la de pruebas la crea `CREATE DATABASE` con la unica
    que instala esta migracion. La ida y vuelta se estaba comprobando contra la
    base que no se parece a produccion.
    """
    op.execute(
        """
        DO $$
        BEGIN
            DROP EXTENSION IF EXISTS postgis;
        EXCEPTION WHEN dependent_objects_still_exist THEN
            RAISE NOTICE 'postgis se deja puesto: otras extensiones dependen de el';
        END $$;
        """
    )
