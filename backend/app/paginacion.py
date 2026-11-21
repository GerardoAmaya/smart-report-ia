"""Paginacion por cursor de la cola.

Por cursor y no por desplazamiento (`OFFSET`): la cola cambia en vivo —entra un
caso, otro se reagrupa y sube de puesto— y con desplazamiento la pagina
siguiente se corre una fila: un caso sale repetido o, peor, no sale nunca. El
cursor dice "despues de esta fila" con los valores por los que se ordena, y eso
no se mueve aunque cambie lo de arriba.

El cursor es opaco para el cliente: base64url de los valores de la ultima fila.
Se valida al leerlo; uno mal formado es un 400, no un 500 ni una pagina vacia
que parezca el final.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import literal, tuple_
from sqlalchemy.sql.elements import ColumnElement


class CursorInvalido(HTTPException):
    def __init__(self) -> None:
        super().__init__(status.HTTP_400_BAD_REQUEST, "el cursor de la cola no es valido")


def codificar(rango: int, menos_reportes: int, creado: datetime, caso_id: UUID) -> str:
    crudo = json.dumps([rango, menos_reportes, creado.isoformat(), str(caso_id)])
    return base64.urlsafe_b64encode(crudo.encode()).decode().rstrip("=")


def decodificar(cursor: str) -> tuple[int, int, datetime, UUID]:
    try:
        relleno = "=" * (-len(cursor) % 4)
        valores = json.loads(base64.urlsafe_b64decode(cursor + relleno))
        rango, menos_reportes, creado, caso_id = valores
        # bool es int en Python: un cursor fabricado con true no debe colar.
        if not all(type(v) is int for v in (rango, menos_reportes)):
            raise ValueError
        fecha = datetime.fromisoformat(creado)
        # Sin zona, la comparacion con timestamptz dependeria de la del servidor.
        if fecha.tzinfo is None:
            raise ValueError
        return rango, menos_reportes, fecha, UUID(caso_id)
    except (ValueError, TypeError, json.JSONDecodeError):
        raise CursorInvalido() from None


def despues_de(columnas: list[ColumnElement], cursor: str) -> ColumnElement:
    """La condicion "esta fila va despues de la del cursor", en el orden dado.

    Una comparacion de filas de Postgres, que es lexicografica: compara la
    primera columna, y solo si empata pasa a la siguiente. Todas en orden
    ascendente; lo que se ordena de mayor a menor entra negado.
    """
    valores = decodificar(cursor)
    return tuple_(*columnas) > tuple_(
        *(literal(v, type_=c.type) for v, c in zip(valores, columnas, strict=True))
    )
