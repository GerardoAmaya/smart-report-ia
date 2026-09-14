"""notify on changes

Revision ID: 0019
Revises: 0018
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Las tablas cuyos cambios el tablero tiene que ver al momento.
TABLAS = ("cases", "reports", "classifications", "notifications", "case_photos")

CANAL = "smart_report_cambios"


def upgrade() -> None:
    # **Disparador y no llamadas a pg_notify desde el codigo.** La tentacion es
    # avisar a mano en cada sitio que cambia algo, y es exactamente como el
    # tablero se queda viejo: basta olvidar uno. Un disparador no se puede
    # olvidar, y vive en una migracion, que esta versionada y se revisa.
    #
    # El payload va minimo —tabla e identificador— porque pg_notify corta en
    # 8000 bytes y mandar la fila entera reventaria con un reporte largo. El
    # cliente pide lo que necesite; esto solo dice "algo cambio aqui".
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION avisar_cambio() RETURNS trigger AS $$
        DECLARE
            fila RECORD;
        BEGIN
            fila := COALESCE(NEW, OLD);
            PERFORM pg_notify(
                '{CANAL}',
                json_build_object(
                    'tabla', TG_TABLE_NAME,
                    'id', fila.id::text,
                    'accion', lower(TG_OP)
                )::text
            );
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    for tabla in TABLAS:
        # AFTER y FOR EACH ROW: el aviso sale cuando el cambio ya esta hecho.
        # Avisar antes haria que el tablero pidiera y leyera el estado viejo.
        op.execute(
            f"""
            CREATE TRIGGER trg_avisar_{tabla}
            AFTER INSERT OR UPDATE OR DELETE ON {tabla}
            FOR EACH ROW EXECUTE FUNCTION avisar_cambio();
            """
        )


def downgrade() -> None:
    for tabla in TABLAS:
        op.execute(f"DROP TRIGGER IF EXISTS trg_avisar_{tabla} ON {tabla}")
    op.execute("DROP FUNCTION IF EXISTS avisar_cambio()")
