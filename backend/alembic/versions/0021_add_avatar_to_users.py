"""add avatar to users

Revision ID: 0021
Revises: 0020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # La de Google se guarda al entrar; la propia, al subirla. Quitar la propia
    # vuelve a la de Google, por eso no comparten columna.
    op.add_column("users", sa.Column("google_picture_url", sa.String(500), nullable=True))
    op.add_column("users", sa.Column("avatar_key", sa.String(300), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_key")
    op.drop_column("users", "google_picture_url")
