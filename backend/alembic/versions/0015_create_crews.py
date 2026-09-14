"""create crews

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Tabla y no una cadena en `cases`: una cuadrilla mal escrita crearia una
    # cuadrilla fantasma a la que se le asignan casos que nadie ve.
    op.create_table(
        "crews",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("notes", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_crews_name", "crews", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_crews_name", table_name="crews")
    op.drop_table("crews")
