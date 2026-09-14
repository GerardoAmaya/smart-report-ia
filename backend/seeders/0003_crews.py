"""Cuadrillas de ejemplo.

Existen para que el despacho se pueda usar desde el primer arranque: sin
ninguna cuadrilla, el boton de asignar no tiene a quien asignar y la funcion
parece rota.

Son de ejemplo y lo dicen en el nombre. Una institucion de verdad las crea las
suyas y da de baja estas; por eso el seeder **no reactiva** una cuadrilla que
alguien apago, ni pisa el nombre de una que ya existe.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Crew

EJEMPLOS = [
    ("Cuadrilla de ejemplo A", "Creada por el seeder. Dar de baja al usar esto de verdad."),
    ("Cuadrilla de ejemplo B", "Creada por el seeder. Dar de baja al usar esto de verdad."),
]


def seed(session: Session) -> None:
    for nombre, notas in EJEMPLOS:
        existe = session.execute(select(Crew.id).where(Crew.name == nombre)).first()
        if existe is None:
            session.add(Crew(name=nombre, notes=notas, is_active=True))
