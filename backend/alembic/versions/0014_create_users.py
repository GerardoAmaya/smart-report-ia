"""create users

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = ("admin", "operator", "demo")


def upgrade() -> None:
    # **Google dice quien es, no si puede entrar.** Esta tabla es la lista de
    # quienes pueden, con su rol. Sin ella, cualquiera con una cuenta de Google
    # entraria al tablero de una institucion.
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        # Guardado en minusculas: los proveedores no coinciden en el uso de
        # mayusculas y comparar sin normalizar deja entrar a un correo dos veces
        # o a ninguna.
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("display_name", sa.String(128)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(f"role IN {ROLES}", name="ck_users_role"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
