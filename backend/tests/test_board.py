"""La API del tablero.

La verificacion de la fase dice que un operador que no vio el sistema antes
entienda **por que cuatro reportes estan juntos** sin que nadie se lo explique.
Eso depende de que el detalle traiga la evidencia escrita, no un puntaje.
"""

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from app import grouping
from app.config import settings
from app.models import Case, Classification, Report, ReportPhoto
from app.taxonomy import Category

PASSWORD = "clave-del-tablero"
LAT0, LON0 = 13.6929, -89.2182


@pytest.fixture(autouse=True)
def demo(monkeypatch):
    monkeypatch.setattr(settings, "demo_password", SecretStr(PASSWORD))


@pytest.fixture
def sesion_iniciada(client):
    assert client.post("/auth/demo", json={"password": PASSWORD}).status_code == 200
    return client


def desplazar(metros: float) -> tuple[float, float]:
    return LAT0 + metros / 111_320, LON0


def crear_reporte(session, *, metros=0.0, usuario="1", caption=None, categoria=None):
    lat, lon = desplazar(metros)
    r = Report(
        channel="telegram",
        external_user_id=usuario,
        status="received",
        caption=caption,
        location=func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326),
    )
    session.add(r)
    session.flush()
    session.add(
        ReportPhoto(
            report_id=r.id,
            channel="telegram",
            external_file_id=f"f{usuario}{metros}",
            status="stored",
            storage_key=f"2026/01/01/{r.id}/orig.jpg",
            thumbnail_key=f"2026/01/01/{r.id}/thumb.jpg",
        )
    )
    session.add(
        Classification(
            report_id=r.id,
            status="confirmed",
            proposed_category=categoria or Category.VIALIDAD.value,
            proposed_severity="alta",
            proposed_reason="Se ve un bache profundo en el carril derecho.",
            final_category=categoria or Category.VIALIDAD.value,
            final_severity="alta",
            confirmed_at=datetime.now(UTC),
        )
    )
    session.commit()
    session.refresh(r)
    grouping.group_report(session, r)
    session.commit()
    return r


def test_la_cola_trae_los_casos(sesion_iniciada, session):
    crear_reporte(session)
    crear_reporte(session, metros=10, usuario="2")

    cuerpo = sesion_iniciada.get("/board/cases").json()

    assert len(cuerpo["cases"]) == 1
    caso = cuerpo["cases"][0]
    assert caso["report_count"] == 2
    assert caso["category"] == Category.VIALIDAD.value
    assert caso["severity"] == "alta"


def test_lo_grave_va_primero(sesion_iniciada, session):
    """Quien despacha necesita ver primero lo mas grave, no lo mas reciente."""
    crear_reporte(session, categoria=Category.DESECHOS.value)
    session.execute(
        Case.__table__.update().values(severity="baja").where(Case.category == "desechos")
    )
    session.commit()
    crear_reporte(session, metros=500, usuario="9", categoria=Category.AGUA.value)

    casos = sesion_iniciada.get("/board/cases").json()["cases"]
    assert casos[0]["severity"] == "alta"


def test_el_detalle_explica_por_que_estan_juntos(sesion_iniciada, session):
    """El corazon de la verificacion de esta fase."""
    crear_reporte(session, caption="hueco grande")
    crear_reporte(session, metros=12, usuario="2", caption="hueco en la esquina")

    caso_id = sesion_iniciada.get("/board/cases").json()["cases"][0]["id"]
    detalle = sesion_iniciada.get(f"/board/cases/{caso_id}").json()

    assert len(detalle["reports"]) == 2

    segundo = detalle["reports"][1]
    evidencia = [e for e in segundo["evidence"] if e["decision"] == "grouped"]
    assert evidencia, "el reporte agrupado tiene que traer su evidencia"

    ev = evidencia[0]
    # La distancia en metros, no un puntaje: "a 12 m" se puede discutir.
    assert 10 <= ev["distance_m"] <= 14
    assert "m" in ev["reason"]
    # Y con que umbrales se decidio, o no se puede interpretar despues.
    assert ev["thresholds"]["group_max_distance_m"] == settings.group_max_distance_m


def test_el_detalle_trae_la_clasificacion_y_si_la_corrigieron(sesion_iniciada, session):
    crear_reporte(session)
    caso_id = sesion_iniciada.get("/board/cases").json()["cases"][0]["id"]

    reporte = sesion_iniciada.get(f"/board/cases/{caso_id}").json()["reports"][0]
    clasificacion = reporte["classification"]

    assert clasificacion["final_category"] == Category.VIALIDAD.value
    assert clasificacion["confirmed"] is True
    assert "bache" in clasificacion["reason"]
    # Saber si la persona corrigio al modelo es lo que deja ver donde falla.
    assert clasificacion["corrected"] is False


def test_el_mapa_dice_cuantos_reportan_cada_punto(sesion_iniciada, session):
    """El tamaño del pin es cuantos reportan lo mismo.

    Un mapa de puntos iguales tira a la basura la informacion de donde se
    concentra el reclamo.
    """
    crear_reporte(session)
    crear_reporte(session, metros=10, usuario="2")
    crear_reporte(session, metros=400, usuario="3")

    puntos = sesion_iniciada.get("/board/cases/map").json()["points"]

    assert len(puntos) == 2
    cuentas = sorted(p["report_count"] for p in puntos)
    assert cuentas == [1, 2]
    for p in puntos:
        assert p["lat"] is not None and p["lon"] is not None


def test_la_cola_marca_los_dudosos(sesion_iniciada, session):
    """Lo que quedo en el limite tiene que verse desde la cola."""
    crear_reporte(session)
    crear_reporte(session, metros=55, usuario="2")

    casos = sesion_iniciada.get("/board/cases").json()["cases"]
    assert sum(c["doubtful_count"] for c in casos) == 1


def test_separar_desde_el_tablero(sesion_iniciada, session):
    crear_reporte(session)
    segundo = crear_reporte(session, metros=10, usuario="2")

    r = sesion_iniciada.post(f"/board/reports/{segundo.id}/ungroup")
    assert r.status_code == 200

    session.refresh(segundo)
    assert segundo.grouping_status == "alone"
    # Y queda constancia de quien lo separo.
    from app.models import GroupingEvidence

    motivos = (
        session.execute(
            select(GroupingEvidence.reason).where(GroupingEvidence.report_id == segundo.id)
        )
        .scalars()
        .all()
    )
    assert any("separado por" in m for m in motivos)


def test_separar_un_reporte_suelto_avisa(sesion_iniciada, session):
    r = Report(channel="telegram", external_user_id="9", status="received")
    session.add(r)
    session.commit()

    assert sesion_iniciada.post(f"/board/reports/{r.id}/ungroup").status_code == 409


def test_un_caso_que_no_existe_da_404(sesion_iniciada):
    import uuid

    assert sesion_iniciada.get(f"/board/cases/{uuid.uuid4()}").status_code == 404


def test_no_se_puede_descartar_cambiando_el_estado(sesion_iniciada, session):
    """`discarded` no esta entre los estados que despachar puede poner.

    Descartar es borrar, y borrar es otro permiso.
    """
    crear_reporte(session)
    caso_id = sesion_iniciada.get("/board/cases").json()["cases"][0]["id"]

    r = sesion_iniciada.post(f"/board/cases/{caso_id}/status?nuevo=discarded")
    assert r.status_code == 422
