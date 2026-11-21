"""La cola por paginas, con cursor.

Existe por un fallo real: la cola devolvia solo los 50 primeros en su orden
(gravedad, reportes, antiguedad), asi que un caso nuevo, leve y de un reporte
caia al final y con mas de 50 no se veia nunca en «Todo».
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr

from app.config import settings
from app.models import Case, Report

PASSWORD = "clave-de-la-cola"
T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def sesion(client, monkeypatch):
    monkeypatch.setattr(settings, "demo_password", SecretStr(PASSWORD))
    assert client.post("/auth/demo", json={"password": PASSWORD}).status_code == 200
    return client


def crear_caso(session, *, severidad="baja", reportes=1, creado=T0, estado="open") -> Case:
    caso = Case(status=estado, category="vialidad", severity=severidad, created_at=creado)
    session.add(caso)
    session.flush()
    for i in range(reportes):
        session.add(
            Report(
                channel="telegram",
                external_user_id=f"{caso.id}-{i}",
                status="received",
                case_id=caso.id,
            )
        )
    return caso


def recorrer(cliente, filtro: str = "", limite: int = 7) -> tuple[list[str], int]:
    """Pide pagina tras pagina hasta el final. Devuelve los ids y cuantas fueron."""
    ids, cursor, paginas = [], None, 0
    while True:
        q = f"?limite={limite}{filtro}" + (f"&cursor={cursor}" if cursor else "")
        r = cliente.get(f"/board/cases{q}")
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        ids += [c["id"] for c in cuerpo["cases"]]
        paginas += 1
        cursor = cuerpo["next_cursor"]
        if cursor is None:
            return ids, paginas
        assert paginas < 100, "el cursor no avanza"


def test_con_mas_de_cincuenta_se_llega_al_ultimo(sesion, session):
    """El fallo: con 60 casos, el leve y nuevo quedaba fuera de la cola."""
    for i in range(59):
        crear_caso(session, severidad="alta", reportes=2, creado=T0 + timedelta(minutes=i))
    ultimo = crear_caso(session, severidad="baja", reportes=1, creado=T0 + timedelta(days=1))
    session.commit()

    ids, _ = recorrer(sesion, limite=50)

    assert str(ultimo.id) in ids
    assert ids[-1] == str(ultimo.id)


def test_cada_caso_sale_una_vez_y_en_el_mismo_orden_que_sin_paginar(sesion, session):
    # Empates a proposito: misma gravedad, mismos reportes y hasta la misma
    # fecha. Ahi solo el id ordena, y es donde un cursor mal hecho salta filas.
    for sev in ("alta", "media", "baja", None):
        for n in (3, 1):
            for _ in range(4):
                crear_caso(session, severidad=sev, reportes=n, creado=T0)
    for i in range(5):
        crear_caso(session, severidad="media", reportes=2, creado=T0 + timedelta(hours=i))
    session.commit()

    de_una_vez = [c["id"] for c in sesion.get("/board/cases?limite=200").json()["cases"]]
    paginado, paginas = recorrer(sesion, limite=4)

    assert len(de_una_vez) == 37
    assert paginado == de_una_vez
    assert len(set(paginado)) == len(paginado)
    assert paginas == 10


def test_el_orden_es_gravedad_luego_reportes_luego_antiguedad(sesion, session):
    leve_viejo = crear_caso(session, severidad="baja", reportes=5, creado=T0)
    urgente_un_reporte = crear_caso(session, severidad="alta", reportes=1, creado=T0)
    urgente_muchos = crear_caso(session, severidad="alta", reportes=4, creado=T0)
    medio_nuevo = crear_caso(session, severidad="media", reportes=1, creado=T0 + timedelta(days=2))
    medio_viejo = crear_caso(session, severidad="media", reportes=1, creado=T0)
    session.commit()

    ids, _ = recorrer(sesion, limite=2)

    assert ids == [
        str(c.id)
        for c in (urgente_muchos, urgente_un_reporte, medio_viejo, medio_nuevo, leve_viejo)
    ]


def test_total_y_fin_con_filtros(sesion, session):
    for _ in range(5):
        crear_caso(session, estado="open")
    for _ in range(3):
        crear_caso(session, estado="closed")
    session.commit()

    r = sesion.get("/board/cases?status=closed&limite=2").json()
    assert r["total"] == 3
    assert len(r["cases"]) == 2
    assert r["next_cursor"] is not None

    r2 = sesion.get(f"/board/cases?status=closed&limite=2&cursor={r['next_cursor']}").json()
    assert len(r2["cases"]) == 1
    assert r2["next_cursor"] is None
    assert r2["total"] == 3

    todos = sesion.get("/board/cases").json()
    assert todos["total"] == 8
    assert todos["next_cursor"] is None


@pytest.mark.parametrize(
    "cursor",
    [
        "nada",
        "W10",  # base64 de "[]"
        "WzEsMiwzXQ",  # [1,2,3]: faltan valores
        # [0,-1,"2026-11-01T12:00:00","..."]: fecha sin zona
        "WzAsLTEsIjIwMjYtMTEtMDFUMTI6MDA6MDAiLCIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDAiXQ",
        # [true,-1,...]: un booleano no es un rango
        "W3RydWUsLTEsIjIwMjYtMTEtMDFUMTI6MDA6MDArMDA6MDAiLCIwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDAiXQ",
    ],
)
def test_un_cursor_mal_formado_es_400(sesion, cursor):
    r = sesion.get(f"/board/cases?cursor={cursor}")
    assert r.status_code == 400


def test_un_caso_que_entra_mientras_se_pagina_no_corre_las_paginas(sesion, session):
    """Con desplazamiento, un caso nuevo arriba repetiria uno de la pagina 1."""
    for i in range(6):
        crear_caso(session, severidad="baja", creado=T0 + timedelta(minutes=i))
    session.commit()

    p1 = sesion.get("/board/cases?limite=3").json()
    crear_caso(session, severidad="alta", reportes=9, creado=T0)
    session.commit()
    p2 = sesion.get(f"/board/cases?limite=3&cursor={p1['next_cursor']}").json()

    vistos = [c["id"] for c in p1["cases"] + p2["cases"]]
    assert len(vistos) == len(set(vistos)) == 6
