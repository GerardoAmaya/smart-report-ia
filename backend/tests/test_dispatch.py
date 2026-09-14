"""Despacho y cierre.

Lo que define esta fase: **avisarle de vuelta a todos los que reportaron, no
solo al primero.** Es la parte que casi nadie construye y sin la cual nadie
reporta dos veces; y es lo que le da sentido al agrupamiento mas alla de
ahorrar trabajo, porque permite responderle a cuatro personas con un solo
arreglo.
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from app import dispatch, notify_worker
from app.channels.telegram import TelegramChannel
from app.config import settings
from app.models import Case, CasePhoto, Classification, Crew, Notification, Report
from tests.imagenes import foto_sintetica

PASSWORD = "clave-del-despacho"


@pytest.fixture(autouse=True)
def demo(monkeypatch):
    monkeypatch.setattr(settings, "demo_password", SecretStr(PASSWORD))


@pytest.fixture
def sesion(client):
    assert client.post("/auth/demo", json={"password": PASSWORD}).status_code == 200
    return client


@pytest.fixture
def cuadrilla(session):
    c = Crew(name=f"Cuadrilla {uuid.uuid4().hex[:6]}", is_active=True)
    session.add(c)
    session.commit()
    return c


def caso_con_reportes(session, usuarios: list[str], categoria: str = "vialidad") -> Case:
    """Un caso con varios reportes, como el que el sistema agrupa."""
    caso = Case(category=categoria, severity="alta", status="open", report_count=len(usuarios))
    session.add(caso)
    session.flush()

    for u in usuarios:
        r = Report(
            channel="telegram",
            external_user_id=u,
            status="received",
            case_id=caso.id,
            grouping_status="grouped",
            location=func.ST_SetSRID(func.ST_MakePoint(-89.2182, 13.6929), 4326),
        )
        session.add(r)
        session.flush()
        session.add(
            Classification(
                report_id=r.id,
                status="confirmed",
                proposed_category=categoria,
                final_category=categoria,
                final_severity="alta",
                confirmed_at=datetime.now(UTC),
            )
        )
    session.commit()
    return caso


def subir_evidencia(sesion, caso_id) -> None:
    datos = foto_sintetica(semilla=91)
    r = sesion.post(
        f"/board/cases/{caso_id}/evidence",
        files={"archivo": ("arreglo.jpg", datos, "image/jpeg")},
    )
    assert r.status_code == 200, r.text


# --- LO QUE DEFINE LA FASE ---


def test_se_avisa_a_todos_los_que_reportaron(sesion, session, cuadrilla):
    """Cuatro personas reportaron el mismo hueco. Las cuatro se enteran.

    Un solo arreglo, cuatro respuestas. Eso es lo que hace que la gente vuelva a
    reportar.
    """
    caso = caso_con_reportes(session, ["101", "102", "103", "104"])

    sesion.post(f"/board/cases/{caso.id}/assign?crew_id={cuadrilla.id}")
    subir_evidencia(sesion, caso.id)
    r = sesion.post(f"/board/cases/{caso.id}/close?nota=Se+bacheo+el+tramo")

    assert r.status_code == 200
    assert r.json()["avisados"] == 4

    destinatarios = set(
        session.execute(
            select(Notification.external_user_id).where(
                Notification.case_id == caso.id, Notification.kind == "closed"
            )
        )
        .scalars()
        .all()
    )
    assert destinatarios == {"101", "102", "103", "104"}


def test_quien_reporto_tres_veces_recibe_un_aviso(sesion, session, cuadrilla):
    """Quien mas reporta no puede acabar mas molestado por el sistema."""
    caso = caso_con_reportes(session, ["201", "201", "201", "202"])

    sesion.post(f"/board/cases/{caso.id}/assign?crew_id={cuadrilla.id}")
    subir_evidencia(sesion, caso.id)
    sesion.post(f"/board/cases/{caso.id}/close")

    cuantos = session.execute(
        select(func.count(Notification.id)).where(
            Notification.case_id == caso.id,
            Notification.kind == "closed",
            Notification.external_user_id == "201",
        )
    ).scalar_one()
    assert cuantos == 1


def test_cerrar_dos_veces_no_reenvia_el_aviso(sesion, session, cuadrilla):
    """Un sistema que avisa dos veces de lo mismo se aprende a ignorar."""
    caso = caso_con_reportes(session, ["301"])
    sesion.post(f"/board/cases/{caso.id}/assign?crew_id={cuadrilla.id}")
    subir_evidencia(sesion, caso.id)
    sesion.post(f"/board/cases/{caso.id}/close")

    sesion.post(f"/board/cases/{caso.id}/reopen")
    r = sesion.post(f"/board/cases/{caso.id}/close")

    assert r.json()["avisados"] == 0
    cuantos = session.execute(
        select(func.count(Notification.id)).where(
            Notification.case_id == caso.id, Notification.kind == "closed"
        )
    ).scalar_one()
    assert cuantos == 1


def test_el_aviso_habla_del_reporte_y_no_del_caso(session):
    """Quien reporto un hueco no sabe que existe un "caso 4f2a".

    El agrupamiento es un detalle del sistema, no de su problema.
    """
    caso = Case(category="vialidad", status="closed", closing_note="Se bacheo el tramo.")
    texto = dispatch.mensaje(caso, "closed")

    assert "reportaste" in texto
    assert "la calle o acera" in texto
    assert str(caso.id) not in texto
    assert "caso" not in texto.lower()
    # La nota del operador llega tal cual.
    assert "Se bacheo el tramo." in texto


# --- Cerrar exige evidencia ---


def test_no_se_cierra_sin_foto_del_arreglo(sesion, session, cuadrilla):
    """Cerrar sin evidencia convierte el cierre en una afirmacion que nadie
    puede comprobar."""
    caso = caso_con_reportes(session, ["401"])
    sesion.post(f"/board/cases/{caso.id}/assign?crew_id={cuadrilla.id}")

    r = sesion.post(f"/board/cases/{caso.id}/close")

    assert r.status_code == 409
    assert "foto" in r.json()["detail"]
    session.refresh(caso)
    assert caso.status != "closed"
    # Nadie recibio un aviso de cierre de algo que no se cerro. El de asignacion
    # si esta, y debe estar: esa parte si ocurrio.
    cierres = session.execute(
        select(func.count(Notification.id)).where(Notification.kind == "closed")
    ).scalar_one()
    assert cierres == 0


def test_la_evidencia_se_valida_abriendola(sesion, session):
    """Un archivo con cabecera JPEG y basura detras revienta despues."""
    caso = caso_con_reportes(session, ["501"])
    falso = b"\\xff\\xd8\\xff\\xe0" + b"basura" * 200

    r = sesion.post(
        f"/board/cases/{caso.id}/evidence",
        files={"archivo": ("falsa.jpg", falso, "image/jpeg")},
    )

    assert r.status_code == 400
    assert session.execute(select(func.count(CasePhoto.id))).scalar_one() == 0


def test_la_evidencia_guarda_quien_la_subio(sesion, session):
    """Una evidencia sin autor no se puede cuestionar."""
    caso = caso_con_reportes(session, ["601"])
    subir_evidencia(sesion, caso.id)

    foto = session.execute(select(CasePhoto)).scalar_one()
    assert foto.uploaded_by == settings.demo_email
    assert foto.storage_key and foto.thumbnail_key
    assert foto.content_sha256


def test_la_evidencia_no_entra_en_la_agrupacion(sesion, session):
    """Va en tabla propia justo para que no pueda.

    Compartiendo tabla con las de reporte, olvidar un `WHERE kind='report'` una
    sola vez meteria la foto del arreglo como si fuera otro reporte del problema.
    """
    from app.models import ReportPhoto

    caso = caso_con_reportes(session, ["701"])
    subir_evidencia(sesion, caso.id)

    assert session.execute(select(func.count(CasePhoto.id))).scalar_one() == 1
    assert session.execute(select(func.count(ReportPhoto.id))).scalar_one() == 0


# --- Asignar ---


def test_asignar_avisa_y_cambia_el_estado(sesion, session, cuadrilla):
    caso = caso_con_reportes(session, ["801", "802"])

    r = sesion.post(f"/board/cases/{caso.id}/assign?crew_id={cuadrilla.id}")

    assert r.status_code == 200
    assert r.json()["avisados"] == 2
    session.refresh(caso)
    assert caso.status == "assigned"
    assert caso.crew_id == cuadrilla.id
    assert caso.assigned_at is not None


def test_no_se_asigna_a_una_cuadrilla_dada_de_baja(sesion, session, cuadrilla):
    cuadrilla.is_active = False
    session.commit()
    caso = caso_con_reportes(session, ["901"])

    r = sesion.post(f"/board/cases/{caso.id}/assign?crew_id={cuadrilla.id}")

    assert r.status_code == 409
    assert "baja" in r.json()["detail"]


def test_no_se_pone_en_curso_sin_cuadrilla(sesion, session):
    caso = caso_con_reportes(session, ["1001"])
    r = sesion.post(f"/board/cases/{caso.id}/start")
    assert r.status_code == 409
    assert "cuadrilla" in r.json()["detail"]


def test_reabrir_limpia_la_fecha_de_cierre(sesion, session, cuadrilla):
    """De closed_at cuelga la retencion de las fotos.

    Un caso reabierto no puede seguir contando los noventa dias del cierre
    anterior.
    """
    caso = caso_con_reportes(session, ["1101"])
    sesion.post(f"/board/cases/{caso.id}/assign?crew_id={cuadrilla.id}")
    subir_evidencia(sesion, caso.id)
    sesion.post(f"/board/cases/{caso.id}/close")
    session.refresh(caso)
    assert caso.closed_at is not None

    sesion.post(f"/board/cases/{caso.id}/reopen")
    session.refresh(caso)

    assert caso.status == "assigned"
    assert caso.closed_at is None


# --- El aviso sale de verdad ---


def test_el_trabajador_manda_el_aviso(sesion, session, cuadrilla, monkeypatch):
    enviados: list[tuple[str, str]] = []

    async def falso(self, external_user_id, text):
        enviados.append((external_user_id, text))

    monkeypatch.setattr(TelegramChannel, "notify", falso)

    caso = caso_con_reportes(session, ["1201", "1202"])
    sesion.post(f"/board/cases/{caso.id}/assign?crew_id={cuadrilla.id}")
    subir_evidencia(sesion, caso.id)
    sesion.post(f"/board/cases/{caso.id}/close?nota=Listo")

    # Dos de asignacion y dos de cierre.
    assert notify_worker.run_once(session) == 4

    assert {u for u, _ in enviados} == {"1201", "1202"}
    assert any("resuelto" in t for _, t in enviados)

    pendientes = session.execute(
        select(func.count(Notification.id)).where(Notification.status != "sent")
    ).scalar_one()
    assert pendientes == 0


def test_a_quien_bloqueo_el_bot_no_se_le_reintenta(sesion, session, cuadrilla, monkeypatch):
    """Reintentar eso es gastar cuota para llegar a la misma conclusion."""

    async def bloqueado(self, external_user_id, text):
        raise RuntimeError("Forbidden: bot was blocked by the user")

    monkeypatch.setattr(TelegramChannel, "notify", bloqueado)

    caso = caso_con_reportes(session, ["1301"])
    sesion.post(f"/board/cases/{caso.id}/assign?crew_id={cuadrilla.id}")
    notify_worker.run_once(session)

    aviso = session.execute(select(Notification)).scalars().first()
    session.refresh(aviso)
    assert aviso.status == "failed"
    assert aviso.attempts == 1
    assert aviso.next_attempt_at is None


def test_un_fallo_de_red_si_se_reintenta(sesion, session, cuadrilla, monkeypatch):
    async def se_cae(self, external_user_id, text):
        raise ConnectionError("la red")

    monkeypatch.setattr(TelegramChannel, "notify", se_cae)

    caso = caso_con_reportes(session, ["1401"])
    sesion.post(f"/board/cases/{caso.id}/assign?crew_id={cuadrilla.id}")
    notify_worker.run_once(session)

    aviso = session.execute(select(Notification)).scalars().first()
    session.refresh(aviso)
    assert aviso.status == "pending"
    assert aviso.next_attempt_at is not None


def test_el_cierre_no_depende_de_que_el_aviso_salga(sesion, session, cuadrilla, monkeypatch):
    """El cierre es un hecho; avisarlo es un intento.

    Si mandar los mensajes viviera dentro de la peticion que cierra, un fallo en
    el cuarto dejaria el caso sin cerrar.
    """

    async def siempre_falla(self, external_user_id, text):
        raise ConnectionError("la red")

    monkeypatch.setattr(TelegramChannel, "notify", siempre_falla)

    caso = caso_con_reportes(session, ["1501"])
    sesion.post(f"/board/cases/{caso.id}/assign?crew_id={cuadrilla.id}")
    subir_evidencia(sesion, caso.id)
    r = sesion.post(f"/board/cases/{caso.id}/close")

    assert r.status_code == 200
    session.refresh(caso)
    assert caso.status == "closed"
