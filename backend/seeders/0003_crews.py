"""Cuadrillas, una por especialidad.

Existen para que el despacho se pueda usar desde el primer arranque: sin
ninguna cuadrilla, el boton de asignar no tiene a quien asignar y la funcion
parece rota.

**El nombre le llega a quien reporto**: «Tu reporte ya fue asignado a
Cuadrilla de bacheo». Por eso va por especialidad, alineada con las categorias,
y no por letra: «Cuadrilla A» no le dice a nadie quien va. Las primeras se
llamaban «Cuadrilla de ejemplo A/B», y con el sistema en produccion ese
«ejemplo» le llegaba a gente de verdad.

Idempotente, porque el corredor lo ejecuta en cada despliegue: no duplica, **no
reactiva** una cuadrilla que alguien apago, ni pisa el nombre de una que ya
existe. Las de ejemplo se dan de baja y no se borran: los casos que se les
asignaron las siguen nombrando en su historial.
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Crew

CUADRILLAS = [
    ("Cuadrilla de bacheo", "Calles y aceras: baches, hundimientos, aceras rotas."),
    ("Cuadrilla de alumbrado", "Luminarias apagadas, intermitentes o dañadas."),
    ("Cuadrilla de agua y drenaje", "Fugas, tuberías rotas, tragantes y alcantarillas."),
    ("Cuadrilla de limpieza", "Basura acumulada y desechos en la vía pública."),
    ("Cuadrilla de obras y estructuras", "Riesgo de derrumbe: muros, taludes, puentes."),
    ("Cuadrilla de parques y espacios públicos", "Parques, mobiliario urbano y señales."),
]

RETIRADAS = ("Cuadrilla de ejemplo A", "Cuadrilla de ejemplo B")


def seed(session: Session) -> None:
    for nombre, notas in CUADRILLAS:
        existe = session.execute(select(Crew.id).where(Crew.name == nombre)).first()
        if existe is None:
            session.add(Crew(name=nombre, notes=notas, is_active=True))

    # De baja y no borradas: una cuadrilla con casos en su historial no se borra.
    session.execute(
        update(Crew)
        .where(Crew.name.in_(RETIRADAS), Crew.is_active.is_(True))
        .values(is_active=False)
    )
