"""create cases

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ESTADOS = ("open", "assigned", "in_progress", "closed", "discarded")


def upgrade() -> None:
    # Un caso es un problema real. Varios reportes pueden apuntar al mismo, y
    # eso es justo lo que el sistema existe para descubrir: cuarenta y siete
    # reportes en un dia son dieciocho problemas.
    op.create_table(
        "cases",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("category", sa.String(32)),
        sa.Column("severity", sa.String(16)),
        # Centro de los reportes que lo forman. Se recalcula al entrar uno
        # nuevo: comparar contra el centro es mas estable que contra el primer
        # reporte, que por ser el primero no tiene por que ser el mas exacto.
        sa.Column("centroid", Geography(geometry_type="POINT", srid=4326, spatial_index=False)),
        sa.Column("report_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(f"status IN {ESTADOS}", name="ck_cases_status"),
    )
    op.create_index("ix_cases_centroid_gist", "cases", ["centroid"], postgresql_using="gist")
    op.create_index("ix_cases_category_status", "cases", ["category", "status"])


def downgrade() -> None:
    op.drop_index("ix_cases_category_status", table_name="cases")
    op.drop_index("ix_cases_centroid_gist", table_name="cases")
    op.drop_table("cases")
