"""add phash to photos

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Huella perceptual: 64 bits que sobreviven al reescalado y al recorte
    # suave. Detecta la misma foto reenviada, que es el caso barato y comun.
    # NO detecta dos fotos distintas del mismo bache; eso es otra cosa y hay que
    # medir si hace falta antes de pagarla.
    op.add_column("report_photos", sa.Column("phash", sa.BigInteger()))
    op.create_index(
        "ix_report_photos_phash",
        "report_photos",
        ["phash"],
        postgresql_where=sa.text("phash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_report_photos_phash", table_name="report_photos")
    op.drop_column("report_photos", "phash")
