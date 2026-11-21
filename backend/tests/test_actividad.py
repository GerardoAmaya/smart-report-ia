"""El feed de actividad: lo que acaba de pasar, armado con los datos que hay.

Se prueba que cada hecho sale con su texto, en orden, con su tope, y que nada
de lo que sale identifica a quien reporto: el feed lo mira el invitado publico.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import update

from app import dispatch
from app.config import settings
from app.models import Case, Crew, Notification, Report
from tests.test_board import crear_reporte

PASSWORD = "clave-del-feed"


@pytest.fixture(autouse=True)
def invitado(monkeypatch):
    monkeypatch.setattr(settings, "demo_password", SecretStr(PASSWORD))


@pytest.fixture
def sesion(client):
    assert client.post("/auth/demo", json={"password": PASSWORD}).status_code == 200
    return client


def _eventos(sesion, **params) -> list[dict]:
    r = sesion.get("/board/actividad", params=params)
    assert r.status_code == 200, r.text
    return r.json()["eventos"]


def _de_tipo(eventos, tipo) -> list[dict]:
    return [e for e in eventos if e["tipo"] == tipo]


def test_sin_sesion_no_se_ve(client):
    assert client.get("/board/actividad").status_code == 401


def test_un_reporte_nuevo_sale_con_su_categoria(sesion, session):
    r = crear_reporte(session)
    session.execute(
        update(Report).where(Report.id == r.id).values(address_text="Colonia Escalón, San Salvador")
    )
    session.commit()

    (evento,) = _de_tipo(_eventos(sesion), "reporte")

    assert evento["texto"] == "Nuevo reporte · Calle o acera · Colonia Escalón, San Salvador"
    assert evento["caso_id"] == str(r.case_id)


def test_juntarse_con_otro_dice_cuantos_son(sesion, session):
    crear_reporte(session)
    crear_reporte(session, metros=10, usuario="2")
    crear_reporte(session, metros=12, usuario="3")

    juntados = _de_tipo(_eventos(sesion), "agrupado")

    assert [e["texto"] for e in juntados] == [
        "Se juntó con otros 2 reportes · ahora son 3",
        "Se juntó con otro reporte · ahora son 2",
    ]
    assert all(e["detalle"] == "Calle o acera" for e in juntados)


def test_un_dudoso_sale_como_pendiente(sesion, session):
    crear_reporte(session)
    # Entre 30 y 80 m: ni tan cerca para juntarlo solo ni tan lejos para ignorarlo.
    crear_reporte(session, metros=50, usuario="2")

    (evento,) = _de_tipo(_eventos(sesion), "dudoso")

    assert evento["texto"] == "Quedó en duda · espera que alguien decida"


def test_el_ciclo_del_caso_sale_entero(sesion, session):
    crear_reporte(session, usuario="7")
    crear_reporte(session, metros=10, usuario="8")
    caso = session.query(Case).one()
    cuadrilla = Crew(name="Cuadrilla de bacheo", is_active=True)
    session.add(cuadrilla)
    session.flush()

    dispatch.assign(session, caso, cuadrilla)
    dispatch.start(session, caso)
    dispatch.close(session, caso, "Listo", exigir_evidencia=False)
    # Los avisos los manda el trabajador; aca se dan por enviados.
    session.execute(update(Notification).values(status="sent", sent_at=datetime.now(UTC)))
    session.commit()

    eventos = _eventos(sesion)

    (asignado,) = _de_tipo(eventos, "asignado")
    assert asignado["texto"] == "Asignado a Cuadrilla de bacheo"
    (en_curso,) = _de_tipo(eventos, "en_curso")
    assert en_curso["texto"] == "Ya están trabajando"
    (cerrado,) = _de_tipo(eventos, "cerrado")
    # Dos personas, dos avisos de cierre: dos, no cuatro mensajes contados.
    assert cerrado["texto"] == "Resuelto · se avisó a 2 personas"
    avisos = {e["texto"] for e in _de_tipo(eventos, "aviso")}
    assert avisos == {
        "Se avisó a 2 personas que se asignó",
        "Se avisó a 2 personas que ya están trabajando",
    }


def test_va_del_mas_nuevo_al_mas_viejo_y_respeta_el_tope(sesion, session):
    for i in range(5):
        r = crear_reporte(session, metros=i * 5000, usuario=str(i))
        # Fechas separadas a proposito: en la misma transaccion saldrian iguales.
        session.execute(
            update(Report)
            .where(Report.id == r.id)
            .values(created_at=datetime.now(UTC) - timedelta(minutes=10 - i))
        )
    session.commit()

    eventos = _eventos(sesion, limite=3)

    assert len(eventos) == 3
    fechas = [e["cuando"] for e in eventos]
    assert fechas == sorted(fechas, reverse=True)


def test_no_sale_nada_de_quien_reporto(sesion, session):
    crear_reporte(session, usuario="555123987", caption="Soy Juana, vivo en la casa 14")
    crear_reporte(session, metros=10, usuario="555000111", caption="Mi telefono es 7777-7777")

    crudo = sesion.get("/board/actividad").text

    for secreto in ("555123987", "555000111", "Juana", "casa 14", "7777-7777"):
        assert secreto not in crudo
