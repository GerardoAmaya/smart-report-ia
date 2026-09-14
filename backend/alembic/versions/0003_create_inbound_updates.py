"""create inbound_updates

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inbound_updates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "channel",
            sa.String(32),
            sa.ForeignKey("channels.code", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_update_id", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("process_error", sa.Text()),
        # Idempotencia del canal: Telegram reenvia el update si el webhook
        # tarda, y sin este unico cada reintento seria un reporte duplicado.
        sa.UniqueConstraint(
            "channel", "external_update_id", name="uq_inbound_updates_channel_extid"
        ),
    )


def downgrade() -> None:
    op.drop_table("inbound_updates")
