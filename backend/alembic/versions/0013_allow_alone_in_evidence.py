"""allow alone in evidence

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEJAS = ("grouped", "rejected", "doubtful")
# "alone" faltaba: un reporte sin nada cerca tambien deja evidencia, y "mire y
# no habia ningun caso de la misma categoria en ochenta metros" es justo lo que
# un operador necesita leer para confiar en que no se agrupo por descuido.
NUEVAS = ("grouped", "rejected", "doubtful", "alone")


def upgrade() -> None:
    op.drop_constraint("ck_grouping_evidence_decision", "grouping_evidence", type_="check")
    op.create_check_constraint(
        "ck_grouping_evidence_decision", "grouping_evidence", f"decision IN {NUEVAS}"
    )


def downgrade() -> None:
    op.execute("DELETE FROM grouping_evidence WHERE decision = 'alone'")
    op.drop_constraint("ck_grouping_evidence_decision", "grouping_evidence", type_="check")
    op.create_check_constraint(
        "ck_grouping_evidence_decision", "grouping_evidence", f"decision IN {VIEJAS}"
    )
