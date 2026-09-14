"""create notifications

Revision ID: 0018
Revises: 0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ESTADOS = ("pending", "processing", "sent", "failed")
TIPOS = ("assigned", "in_progress", "closed")


def upgrade() -> None:
    # **A todos los que reportaron, no solo al primero.** Es la parte que casi
    # nadie construye y sin la cual nadie reporta dos veces; tambien es lo que
    # le da sentido al agrupamiento mas alla de ahorrar trabajo, porque permite
    # responderle a cuatro personas con un solo arreglo.
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "case_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(32), sa.ForeignKey("channels.code"), nullable=False),
        sa.Column("external_user_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("failure_reason", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(f"status IN {ESTADOS}", name="ck_notifications_status"),
        sa.CheckConstraint(f"kind IN {TIPOS}", name="ck_notifications_kind"),
        # Una persona recibe **un** aviso por caso y tipo, aunque haya reportado
        # el mismo problema tres veces. Sin esto, quien mas reporta mas molesta
        # el sistema, que es exactamente al reves de lo que se quiere.
        sa.UniqueConstraint(
            "case_id", "channel", "external_user_id", "kind", name="uq_notifications_destinatario"
        ),
    )
    op.create_index(
        "ix_notifications_pending",
        "notifications",
        ["next_attempt_at", "created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_notifications_processing",
        "notifications",
        ["locked_at"],
        postgresql_where=sa.text("status = 'processing'"),
    )
    op.create_index("ix_notifications_case", "notifications", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_notifications_case", table_name="notifications")
    op.drop_index("ix_notifications_processing", table_name="notifications")
    op.drop_index("ix_notifications_pending", table_name="notifications")
    op.drop_table("notifications")
