"""add photo processing state

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEJOS = ("pending", "stored", "failed", "rejected")
NUEVOS = ("pending", "processing", "stored", "failed", "rejected")


def upgrade() -> None:
    # La miniatura va aparte del original: el original es evidencia y se guarda
    # tal cual llego, sin reencodear.
    op.add_column("report_photos", sa.Column("thumbnail_key", sa.Text()))
    op.add_column("report_photos", sa.Column("thumbnail_bytes", sa.Integer()))

    # Reintentos con espera creciente. Una foto que falla por un corte de red
    # tiene que volver a intentarse; una que falla porque el archivo ya no esta,
    # no. La diferencia la decide el trabajador, pero sin estas columnas no
    # puede decidir nada.
    op.add_column(
        "report_photos",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("report_photos", sa.Column("next_attempt_at", sa.DateTime(timezone=True)))

    # Marca de cuando un trabajador tomo la fila. Si el proceso muere a mitad de
    # una descarga, la fila queda en processing para siempre; con esto se puede
    # reclamar lo que lleva demasiado tomado.
    op.add_column("report_photos", sa.Column("locked_at", sa.DateTime(timezone=True)))

    op.drop_constraint("ck_report_photos_status", "report_photos", type_="check")
    op.create_check_constraint("ck_report_photos_status", "report_photos", f"status IN {NUEVOS}")

    # El indice parcial de pendientes ahora tiene que ver tambien las que
    # esperan reintento, y ordenar por cuando toca.
    op.drop_index("ix_report_photos_pending", table_name="report_photos")
    op.create_index(
        "ix_report_photos_pending",
        "report_photos",
        ["next_attempt_at", "created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    # Para reclamar las que quedaron tomadas por un trabajador muerto.
    op.create_index(
        "ix_report_photos_processing",
        "report_photos",
        ["locked_at"],
        postgresql_where=sa.text("status = 'processing'"),
    )


def downgrade() -> None:
    op.drop_index("ix_report_photos_processing", table_name="report_photos")
    op.drop_index("ix_report_photos_pending", table_name="report_photos")
    op.create_index(
        "ix_report_photos_pending",
        "report_photos",
        ["created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # Bajar el CHECK exige que no quede ninguna fila en el estado que se quita.
    op.execute("UPDATE report_photos SET status = 'pending' WHERE status = 'processing'")
    op.drop_constraint("ck_report_photos_status", "report_photos", type_="check")
    op.create_check_constraint("ck_report_photos_status", "report_photos", f"status IN {VIEJOS}")

    for columna in ("locked_at", "next_attempt_at", "attempts", "thumbnail_bytes", "thumbnail_key"):
        op.drop_column("report_photos", columna)
