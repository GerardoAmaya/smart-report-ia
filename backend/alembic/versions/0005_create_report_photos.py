"""create report_photos

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = ("pending", "stored", "failed", "rejected")
KINDS = ("report", "evidence")


def upgrade() -> None:
    op.create_table(
        "report_photos",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False, server_default="report"),
        sa.Column(
            "channel",
            sa.String(32),
            sa.ForeignKey("channels.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        # Comprobante de origen, no almacenamiento: el file_path que se pide
        # con esto caduca en una hora.
        sa.Column("external_file_id", sa.Text(), nullable=False),
        sa.Column("external_file_unique_id", sa.String(128)),
        # Lo que declara el update. Se compara con el tope antes de descargar:
        # bajar 20 MB para despues decidir que sobraban es pagar el abuso.
        sa.Column("declared_bytes", sa.Integer()),
        # Lo rellena el trabajador de la fase 2. Nulo aqui no es error: es
        # "todavia no subida", y por eso el estado va aparte.
        sa.Column("storage_key", sa.Text()),
        sa.Column("content_sha256", sa.String(64)),
        sa.Column("bytes", sa.Integer()),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("mime_type", sa.String(64)),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("failure_reason", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("stored_at", sa.DateTime(timezone=True)),
        # La retencion de la fase 2 borra de verdad; esto marca lo que ya no
        # esta en el bucket, para no servir una clave muerta.
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(f"status IN {STATUSES}", name="ck_report_photos_status"),
        sa.CheckConstraint(f"kind IN {KINDS}", name="ck_report_photos_kind"),
    )
    op.create_index("ix_report_photos_report", "report_photos", ["report_id"])
    # No unico: la misma foto reenviada por dos personas son dos reportes. La
    # deduplicacion real la decide content_sha256 en la fase 2.
    op.create_index(
        "ix_report_photos_unique_file", "report_photos", ["channel", "external_file_unique_id"]
    )
    # Parcial: la cola de la fase 2 solo mira pendientes, y el indice no tiene
    # por que crecer con cada foto ya subida.
    op.create_index(
        "ix_report_photos_pending",
        "report_photos",
        ["created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_report_photos_pending", table_name="report_photos")
    op.drop_index("ix_report_photos_unique_file", table_name="report_photos")
    op.drop_index("ix_report_photos_report", table_name="report_photos")
    op.drop_table("report_photos")
