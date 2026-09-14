"""add dispatch to cases

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # RESTRICT: borrar una cuadrilla no puede dejar casos apuntando al vacio ni
    # llevarselos por delante. Si tiene casos, primero se reasignan.
    op.add_column(
        "cases",
        sa.Column("crew_id", sa.UUID(as_uuid=True), sa.ForeignKey("crews.id", ondelete="RESTRICT")),
    )
    op.add_column("cases", sa.Column("assigned_at", sa.DateTime(timezone=True)))
    # Fecha de cierre propia y no `updated_at`: la retencion de las fotos cuelga
    # de cuando se cerro, y `updated_at` se mueve con cualquier cambio.
    op.add_column("cases", sa.Column("closed_at", sa.DateTime(timezone=True)))
    op.add_column("cases", sa.Column("closing_note", sa.Text()))
    op.create_index("ix_cases_crew", "cases", ["crew_id"])
    op.create_index(
        "ix_cases_closed",
        "cases",
        ["closed_at"],
        postgresql_where=sa.text("closed_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_cases_closed", table_name="cases")
    op.drop_index("ix_cases_crew", table_name="cases")
    for columna in ("closing_note", "closed_at", "assigned_at", "crew_id"):
        op.drop_column("cases", columna)
