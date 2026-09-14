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
    # Reversible a proposito: CI comprueba ida y vuelta en cada commit, y una
    # migracion que no baja se descubre el dia que hay que revertir en produccion.
    op.execute("DROP EXTENSION IF EXISTS postgis")
