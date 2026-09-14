"""create reports

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = ("incomplete", "received", "rejected")


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "channel",
            sa.String(32),
            sa.ForeignKey("channels.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_user_id", sa.String(64), nullable=False),
        sa.Column(
            "inbound_update_id",
            sa.BigInteger(),
            sa.ForeignKey("inbound_updates.id", ondelete="SET NULL"),
        ),
        # spatial_index=False: el indice se crea abajo con nombre propio. El
        # que crea GeoAlchemy2 solo se llama idx_* y env.py filtra ese prefijo,
        # asi que un autogenerate futuro propondria borrarlo.
        sa.Column("location", Geography(geometry_type="POINT", srid=4326, spatial_index=False)),
        sa.Column("caption", sa.Text()),
        sa.Column("status", sa.String(24), nullable=False, server_default="incomplete"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(f"status IN {STATUSES}", name="ck_reports_status"),
    )
    # Sin GIST, cada agrupacion de la fase 4 es un recorrido completo.
    op.create_index("ix_reports_location_gist", "reports", ["location"], postgresql_using="gist")
    # Sirve al limite por usuario: contar reportes de alguien en una ventana.
    op.create_index("ix_reports_user_created", "reports", ["external_user_id", "created_at"])
    op.create_index("ix_reports_status_created", "reports", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_reports_status_created", table_name="reports")
    op.drop_index("ix_reports_user_created", table_name="reports")
    op.drop_index("ix_reports_location_gist", table_name="reports")
    op.drop_table("reports")
