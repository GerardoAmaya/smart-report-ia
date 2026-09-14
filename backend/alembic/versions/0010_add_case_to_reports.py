"""add case to reports

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AGRUPACION = ("pending", "grouped", "alone", "doubtful")


def upgrade() -> None:
    # SET NULL y no CASCADE: borrar un caso no puede borrar los reportes que lo
    # formaban. Deshacer una agrupacion tiene que devolver los reportes, no
    # perderlos.
    op.add_column(
        "reports",
        sa.Column("case_id", sa.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="SET NULL")),
    )
    # "doubtful" es el estado que PLAN.md pide: lo que queda en el limite no se
    # agrupa ni se descarta, se marca con el motivo esperando decision humana.
    op.add_column(
        "reports",
        sa.Column("grouping_status", sa.String(16), nullable=False, server_default="pending"),
    )
    op.create_check_constraint(
        "ck_reports_grouping_status", "reports", f"grouping_status IN {AGRUPACION}"
    )
    op.create_index("ix_reports_case", "reports", ["case_id"])
    op.create_index(
        "ix_reports_grouping_pending",
        "reports",
        ["created_at"],
        postgresql_where=sa.text("grouping_status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_reports_grouping_pending", table_name="reports")
    op.drop_index("ix_reports_case", table_name="reports")
    op.drop_constraint("ck_reports_grouping_status", "reports", type_="check")
    op.drop_column("reports", "grouping_status")
    op.drop_column("reports", "case_id")
