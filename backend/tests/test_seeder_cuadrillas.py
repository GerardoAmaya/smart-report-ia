"""Las cuadrillas sembradas: por especialidad, y sin «ejemplo» a la vista.

Existe por un fallo real: con el sistema en produccion, el aviso a quien
reporto decia «ya fue asignado a Cuadrilla de ejemplo A».
"""

from sqlalchemy import func, select

from app.models import Crew
from seeders.runner import SEEDERS_DIR, _load

semilla = _load(SEEDERS_DIR / "0003_crews.py")


def _activas(session) -> set[str]:
    return set(session.execute(select(Crew.name).where(Crew.is_active.is_(True))).scalars())


def test_siembra_una_por_especialidad_y_retira_las_de_ejemplo(session):
    # Como quedo la base de quien sembro con la version anterior.
    for nombre in ("Cuadrilla de ejemplo A", "Cuadrilla de ejemplo B"):
        session.add(Crew(name=nombre, notes="vieja", is_active=True))
    session.commit()

    semilla.seed(session)
    session.commit()

    activas = _activas(session)
    assert {n for n, _ in semilla.CUADRILLAS} <= activas
    assert not any("ejemplo" in n for n in activas)
    # De baja, no borradas: los casos que se les asignaron las siguen nombrando.
    retiradas = (
        session.execute(select(Crew.name).where(Crew.name.like("Cuadrilla de ejemplo%")))
        .scalars()
        .all()
    )
    assert len(retiradas) == 2


def test_correrlo_dos_veces_no_duplica(session):
    semilla.seed(session)
    session.commit()
    semilla.seed(session)
    session.commit()

    repetidas = (
        session.execute(select(Crew.name).group_by(Crew.name).having(func.count() > 1))
        .scalars()
        .all()
    )
    assert repetidas == []


def test_no_reactiva_una_que_alguien_apago(session):
    semilla.seed(session)
    session.commit()
    bacheo = session.execute(select(Crew).where(Crew.name == "Cuadrilla de bacheo")).scalar_one()
    bacheo.is_active = False
    session.commit()

    semilla.seed(session)
    session.commit()

    session.refresh(bacheo)
    assert bacheo.is_active is False
