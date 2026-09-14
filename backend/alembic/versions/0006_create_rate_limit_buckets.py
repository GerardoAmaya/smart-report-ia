"""create rate_limit_buckets

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_buckets",
        sa.Column("scope", sa.String(16), primary_key=True),
        # Nunca la IP en claro: es dato personal y el limitador solo necesita
        # saber si dos peticiones vienen del mismo lado, no de donde. Se guarda
        # un HMAC con el secreto del webhook.
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
    )
    # Para el barrido que borra ventanas viejas.
    op.create_index("ix_rate_limit_window", "rate_limit_buckets", ["window_start"])


def downgrade() -> None:
    op.drop_index("ix_rate_limit_window", table_name="rate_limit_buckets")
    op.drop_table("rate_limit_buckets")
