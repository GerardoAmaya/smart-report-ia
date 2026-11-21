"""add chosen classification status

Revision ID: 0022
Revises: 0021
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEJOS = ("pending", "processing", "proposed", "confirmed", "corrected", "failed")
# "chosen": la persona eligio la categoria porque el modelo no propuso nada.
# Quedaba como "corrected" y el tablero decia que corrigio al modelo, cuando
# no habia nada que corregir.
NUEVOS = ("pending", "processing", "proposed", "confirmed", "corrected", "chosen", "failed")


def upgrade() -> None:
    op.drop_constraint("ck_classifications_status", "classifications", type_="check")
    op.create_check_constraint(
        "ck_classifications_status", "classifications", f"status IN {NUEVOS}"
    )
    # Las que ya estaban mal anotadas: sin propuesta y "corregidas".
    op.execute(
        "UPDATE classifications SET status = 'chosen' "
        "WHERE status = 'corrected' AND proposed_category IS NULL"
    )


def downgrade() -> None:
    # Vuelven a lo que eran antes de existir el estado, sin perder la fila: la
    # categoria que eligio la persona sigue valiendo.
    op.execute("UPDATE classifications SET status = 'corrected' WHERE status = 'chosen'")
    op.drop_constraint("ck_classifications_status", "classifications", type_="check")
    op.create_check_constraint(
        "ck_classifications_status", "classifications", f"status IN {VIEJOS}"
    )
