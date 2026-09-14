"""create grouping evidence

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DECISIONES = ("grouped", "rejected", "doubtful")


def upgrade() -> None:
    # **Cada agrupacion muestra su evidencia.** Un numero de confianza que cada
    # quien interpreta distinto no sirve; una lista de reportes cercanos con la
    # distancia escrita, si. Esta tabla es esa lista, incluidos los que se
    # decidio NO agrupar: saber que se descarto es tan util como saber que se
    # junto.
    op.create_table(
        "grouping_evidence",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("case_id", sa.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE")),
        sa.Column("decision", sa.String(16), nullable=False),
        # Las senales, cada una por separado y en su unidad. Un solo puntaje
        # combinado no se puede discutir; "a 12 metros y misma categoria" si.
        sa.Column("distance_m", sa.Float()),
        sa.Column("category_match", sa.Boolean()),
        sa.Column("hours_apart", sa.Float()),
        sa.Column("text_similarity", sa.Float()),
        sa.Column("visual_distance", sa.Integer()),
        # En español y legible: esto se muestra en el tablero tal cual.
        sa.Column("reason", sa.Text(), nullable=False),
        # Con que umbrales se decidio. Sin esto, una agrupacion vieja no se
        # puede interpretar despues de recalibrar.
        sa.Column("thresholds", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(f"decision IN {DECISIONES}", name="ck_grouping_evidence_decision"),
    )
    op.create_index("ix_grouping_evidence_report", "grouping_evidence", ["report_id"])
    op.create_index("ix_grouping_evidence_case", "grouping_evidence", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_grouping_evidence_case", table_name="grouping_evidence")
    op.drop_index("ix_grouping_evidence_report", table_name="grouping_evidence")
    op.drop_table("grouping_evidence")
