"""Impide borrados masivos contra la base de desarrollo.

Existe por un error real y repetido: un script de depuracion con un `TRUNCATE`
corrido contra la base de desarrollo se llevo un reporte que habia entrado desde
un telefono. La primera vez fue la suite de pruebas —y se arreglo apuntandola a
`smart_report_test`—; la segunda fue codigo a mano que no pasaba por ningun
guardia.

De ahi la leccion: **la defensa no puede vivir en el que llama.** Un guardia que
hay que acordarse de invocar protege solo al que ya iba con cuidado. Este se
engancha al motor, asi que cubre cualquier cosa que use `app.db` —incluido un
script escrito con prisa a las once de la noche—.

**Qué para:** `TRUNCATE`, `DROP`, y `DELETE`/`UPDATE` sin `WHERE`.
**Qué deja pasar:** todo lo demas, y todo si la base termina en `_test`.

Las migraciones no pasan por aqui: Alembic construye su propio motor en
`alembic/env.py`. Es deliberado — cambiar el esquema es justamente su trabajo.
"""

from __future__ import annotations

import logging
import os
import re

from sqlalchemy import event
from sqlalchemy.engine import Engine

log = logging.getLogger("smart_report.db_guard")


class BorradoMasivoBloqueado(RuntimeError):
    """Una sentencia destructiva contra una base que no es de pruebas."""


# Se mira el inicio de la sentencia, ya sin comentarios ni espacios.
_TRUNCATE = re.compile(r"^\s*truncate\b", re.IGNORECASE)
_DROP = re.compile(r"^\s*drop\s+(table|schema|database)\b", re.IGNORECASE)
_DELETE_SIN_WHERE = re.compile(r"^\s*delete\s+from\s+[^\s;]+\s*;?\s*$", re.IGNORECASE)
_UPDATE_SIN_WHERE = re.compile(r"^\s*update\s+(?!.*\bwhere\b).*$", re.IGNORECASE | re.DOTALL)

# Escotilla explicita para cuando de verdad haga falta. Que sea una variable de
# entorno y no un parametro es a proposito: obliga a escribirla fuera del
# codigo, donde se ve.
VARIABLE_DE_ESCAPE = "ALLOW_DESTRUCTIVE_SQL"


def _es_destructiva(sql: str) -> str | None:
    """Devuelve como se llama el peligro, o None si no lo hay."""
    limpia = re.sub(r"--[^\n]*", " ", sql)
    limpia = re.sub(r"/\*.*?\*/", " ", limpia, flags=re.DOTALL)

    if _TRUNCATE.match(limpia):
        return "TRUNCATE"
    if _DROP.match(limpia):
        return "DROP"
    if _DELETE_SIN_WHERE.match(limpia):
        return "DELETE sin WHERE"
    if _UPDATE_SIN_WHERE.match(limpia) and " where " not in limpia.lower():
        return "UPDATE sin WHERE"
    return None


def es_base_de_pruebas(url: str) -> bool:
    nombre = url.rsplit("/", 1)[-1].split("?")[0]
    return nombre.endswith("_test")


def motivo_para_bloquear(url: str, sql: str) -> str | None:
    """La decision entera, sin tocar la base.

    Separada del enganche al motor a proposito: probar esto requeriria una
    conexion viva, y la conexion falla antes de que el guardia llegue a opinar.
    Una regla que no se puede probar sin levantar media infraestructura es una
    regla que nadie prueba.
    """
    peligro = _es_destructiva(sql)
    if peligro is None:
        return None
    if es_base_de_pruebas(url):
        return None
    if os.environ.get(VARIABLE_DE_ESCAPE) == "1":
        log.warning("%s permitido por %s", peligro, VARIABLE_DE_ESCAPE)
        return None
    return peligro


def mensaje_de_bloqueo(base: str, peligro: str, sql: str) -> str:
    """El texto del error. Tiene que decir que pasa y como seguir.

    Un error que solo dice "prohibido" manda a leer el codigo; este dice contra
    que base se intento, que se bloqueo, y cual es la escotilla.
    """
    return (
        f"{peligro} bloqueado contra {base!r}, que no es una base de pruebas.\n"
        f"Si de verdad hace falta: {VARIABLE_DE_ESCAPE}=1\n"
        f"Sentencia: {sql.strip()[:120]}"
    )


def install(engine: Engine) -> None:
    """Engancha el guardia a un motor."""

    @event.listens_for(engine, "before_cursor_execute")
    def _revisar(conn, cursor, statement, parameters, context, executemany):
        peligro = motivo_para_bloquear(str(engine.url), statement)
        if peligro is None:
            return

        raise BorradoMasivoBloqueado(
            mensaje_de_bloqueo(str(engine.url.database), peligro, statement)
        )
