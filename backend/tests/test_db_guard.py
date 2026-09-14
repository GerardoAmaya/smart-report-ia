"""El guardia contra borrados masivos.

Existe por un error real y repetido. La primera vez fue la suite de pruebas
apuntando a la base de desarrollo; la segunda, un script de depuracion con un
TRUNCATE. Las dos veces se perdio un reporte que habia entrado desde un
telefono.

La leccion esta en el diseño: **la defensa no vive en el que llama.** Un guardia
que hay que acordarse de invocar protege solo al que ya iba con cuidado.
"""

import pytest
from sqlalchemy import text

from app import db_guard

DESARROLLO = "postgresql+psycopg://u:p@h:5432/smart_report"
PRUEBAS = "postgresql+psycopg://u:p@h:5432/smart_report_test"


# --- Lo que tiene que parar ---


@pytest.mark.parametrize(
    "sql",
    [
        "TRUNCATE reports",
        "truncate table reports cascade",
        "  TRUNCATE  reports, cases  ",
        "DROP TABLE reports",
        "drop schema public cascade",
        "DELETE FROM reports",
        "delete from reports;",
        "UPDATE reports SET status = 'x'",
    ],
)
def test_bloquea_lo_destructivo(sql):
    assert db_guard.motivo_para_bloquear(DESARROLLO, sql) is not None


def test_el_guardia_esta_enganchado_al_motor_de_verdad(monkeypatch):
    """Que la funcion exista no sirve si nadie la llama.

    Se finge que la base no es de pruebas y se lanza un TRUNCATE real contra el
    motor de la aplicacion: si el enganche falta, el TRUNCATE pasa.
    """
    from app.db import engine

    monkeypatch.setattr(db_guard, "es_base_de_pruebas", lambda url: False)

    with pytest.raises(db_guard.BorradoMasivoBloqueado), engine.connect() as conn:
        conn.execute(text("TRUNCATE reports"))


def test_el_mensaje_dice_que_hacer():
    mensaje = db_guard.mensaje_de_bloqueo("smart_report", "TRUNCATE", "TRUNCATE reports")

    assert "smart_report" in mensaje
    assert "TRUNCATE" in mensaje
    # Dice como seguir, no solo que esta prohibido.
    assert db_guard.VARIABLE_DE_ESCAPE in mensaje


def test_los_comentarios_no_lo_esconden():
    """Un TRUNCATE detras de un comentario sigue siendo un TRUNCATE."""
    assert db_guard.motivo_para_bloquear(DESARROLLO, "-- limpieza\nTRUNCATE reports")
    assert db_guard.motivo_para_bloquear(DESARROLLO, "/* limpieza */ TRUNCATE reports")


# --- Lo que tiene que dejar pasar ---


def test_la_base_de_pruebas_puede_vaciarse():
    """Sin esto la suite no podria limpiar entre casos."""
    assert db_guard.motivo_para_bloquear(PRUEBAS, "TRUNCATE reports") is None


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM reports",
        "DELETE FROM reports WHERE id = 1",
        "UPDATE reports SET status = 'x' WHERE id = 1",
        "INSERT INTO reports (id) VALUES (1)",
        "DROP INDEX ix_algo",
    ],
)
def test_deja_pasar_lo_normal(sql):
    assert db_guard.motivo_para_bloquear(DESARROLLO, sql) is None


def test_hay_escotilla_pero_hay_que_escribirla_fuera(monkeypatch):
    """Variable de entorno y no parametro: obliga a que se vea."""
    assert db_guard.motivo_para_bloquear(DESARROLLO, "TRUNCATE reports") is not None
    monkeypatch.setenv(db_guard.VARIABLE_DE_ESCAPE, "1")
    assert db_guard.motivo_para_bloquear(DESARROLLO, "TRUNCATE reports") is None


def test_reconoce_la_base_de_pruebas_por_el_nombre():
    assert db_guard.es_base_de_pruebas("postgresql://u:p@h:5432/smart_report_test")
    assert not db_guard.es_base_de_pruebas("postgresql://u:p@h:5432/smart_report")
    # Un sufijo parecido no cuenta.
    assert not db_guard.es_base_de_pruebas("postgresql://u:p@h:5432/testing")
