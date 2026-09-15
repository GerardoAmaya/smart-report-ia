"""add address to reports

Revision ID: 0020
Revises: 0019
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # La direccion se guarda y no se pide cada vez: el servicio libre permite
    # una consulta por segundo, y un aviso que espera a la red es un aviso que
    # se puede perder por algo que ya se sabia.
    op.add_column("reports", sa.Column("address_text", sa.String(200), nullable=True))
    # Las dos columnas hacen falta y no una: sin la fecha no se distingue «no
    # se ha intentado» de «se intento y el sitio no tiene nombre», y el
    # trabajador reintentaria para siempre lo segundo.
    op.add_column("reports", sa.Column("geocoded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "reports", sa.Column("geocode_attempts", sa.Integer(), nullable=False, server_default="0")
    )

    # El indice es la cola: solo las filas que faltan por resolver, que son
    # pocas y se vacian. Un indice sobre la tabla entera crece con el historico
    # para responder siempre lo mismo.
    op.create_index(
        "ix_reports_geocode_pending",
        "reports",
        ["created_at"],
        postgresql_where=sa.text("geocoded_at IS NULL AND location IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_reports_geocode_pending", table_name="reports")
    op.drop_column("reports", "geocode_attempts")
    op.drop_column("reports", "geocoded_at")
    op.drop_column("reports", "address_text")
