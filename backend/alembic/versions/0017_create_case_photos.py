"""create case photos

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Tabla propia y **no** `report_photos.kind = 'evidence'`, que es lo que la
    # fase 2 habia anticipado. La anticipacion estaba mal: una foto de evidencia
    # no se parece a una de reporte —la sube un operador y no un ciudadano, no
    # se clasifica, no se le saca huella, y no puede entrar nunca en la
    # agrupacion—. Compartiendo tabla, cada consulta de agrupacion necesitaria
    # `WHERE kind='report'`, y olvidarlo una sola vez mete la foto del arreglo
    # como si fuera un reporte mas del problema.
    op.create_table(
        "case_photos",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "case_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Quien la subio. Una evidencia sin autor no se puede cuestionar.
        sa.Column("uploaded_by", sa.String(320), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("thumbnail_key", sa.Text()),
        sa.Column("content_sha256", sa.String(64)),
        sa.Column("bytes", sa.Integer()),
        sa.Column("thumbnail_bytes", sa.Integer()),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("mime_type", sa.String(64)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_case_photos_case", "case_photos", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_case_photos_case", table_name="case_photos")
    op.drop_table("case_photos")
