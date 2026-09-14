"""create classifications

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ESTADOS = ("pending", "processing", "proposed", "confirmed", "corrected", "failed")


def upgrade() -> None:
    # Tabla aparte y no columnas en reports: una clasificacion es un intento
    # con su modelo, su costo y su momento, y va a haber mas de uno por reporte
    # —reintentos, modelos distintos, reclasificar cuando mejore el prompt—.
    # Aplastarla contra el reporte perderia con que se clasifico cada cosa, que
    # es justo lo que la fase 3 tiene que medir.
    op.create_table(
        "classifications",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        # Lo que propone el modelo. Nunca es la categoria final: eso lo decide
        # una persona confirmando, y por eso son columnas distintas.
        sa.Column("proposed_category", sa.String(32)),
        sa.Column("proposed_severity", sa.String(16)),
        sa.Column("proposed_reason", sa.Text()),
        # Lo que quedo tras la confirmacion. Distinto de lo propuesto cuando la
        # persona corrige, y esa diferencia es la medida de acierto en uso real.
        sa.Column("final_category", sa.String(32)),
        sa.Column("final_severity", sa.String(16)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        # Con que se clasifico. Sin esto no se puede comparar un modelo con otro
        # ni saber que produjo una etiqueta vieja.
        sa.Column("model", sa.String(64)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("cost_usd", sa.Numeric(12, 8)),
        sa.Column("latency_ms", sa.Integer()),
        # Que se le mando: la foto entera o la miniatura. Cambia el costo y
        # puede cambiar el acierto, asi que se anota para poder compararlo.
        sa.Column("image_variant", sa.String(16)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("failure_reason", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(f"status IN {ESTADOS}", name="ck_classifications_status"),
    )
    op.create_index("ix_classifications_report", "classifications", ["report_id"])
    op.create_index(
        "ix_classifications_pending",
        "classifications",
        ["next_attempt_at", "created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_classifications_processing",
        "classifications",
        ["locked_at"],
        postgresql_where=sa.text("status = 'processing'"),
    )


def downgrade() -> None:
    op.drop_index("ix_classifications_processing", table_name="classifications")
    op.drop_index("ix_classifications_pending", table_name="classifications")
    op.drop_index("ix_classifications_report", table_name="classifications")
    op.drop_table("classifications")
