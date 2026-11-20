"""Despacho y cierre.

Lo que define esta fase: **avisarle de vuelta a todos los que reportaron, no
solo al primero.** Es la parte que casi nadie construye y sin la cual nadie
reporta dos veces; y es lo que le da sentido al agrupamiento mas alla de
ahorrar trabajo, porque permite responderle a cuatro personas con un solo
arreglo.
"""

import io
import uuid
from datetime import UTC, datetime

import pytest
from PIL import Image
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
    # Estas pruebas despachan como invitado, como en desarrollo y en las E2E.
    monkeypatch.setattr(settings, "demo_can_dispatch", True)


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


def en_curso(sesion, caso_id, cuadrilla) -> None:
    """Asignar y empezar: lo que ahora hace falta antes de la foto del arreglo."""
    assert sesion.post(f"/board/cases/{caso_id}/assign?crew_id={cuadrilla.id}").status_code == 200
    assert sesion.post(f"/board/cases/{caso_id}/start").status_code == 200


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

    en_curso(sesion, caso.id, cuadrilla)
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

    en_curso(sesion, caso.id, cuadrilla)
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
    en_curso(sesion, caso.id, cuadrilla)
    subir_evidencia(sesion, caso.id)
    sesion.post(f"/board/cases/{caso.id}/close")

    sesion.post(f"/board/cases/{caso.id}/reopen")
    sesion.post(f"/board/cases/{caso.id}/start")
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


def test_el_aviso_dice_cual_reporte_es(session):
    """La categoria sola no distingue dos reportes de la misma persona.

    Quien reporto dos fugas en la misma semana recibia dos veces "tu reporte
    sobre el agua o drenaje" y no podia saber cual se movio.
    """
    from datetime import UTC, datetime

    caso = Case(category="agua", status="assigned")
    session.add(caso)
    session.flush()
    reporte = Report(
        channel="telegram",
        external_user_id="777",
        status="received",
        case_id=caso.id,
        created_at=datetime(2026, 9, 14, 23, 18, tzinfo=UTC),
        location="SRID=4326;POINT(-89.238082 13.685892)",
    )
    session.add(reporte)
    session.commit()

    texto = dispatch.mensaje(caso, "assigned", None, reporte, session)

    # Cuando: en hora de El Salvador, que son seis menos que UTC.
    assert "lunes 14 de septiembre" in texto
    assert "5:18 p. m." in texto
    # Donde: el punto exacto que recibio la cuadrilla.
    assert "13.685892,-89.238082" in texto
    # El enlace termina el mensaje: un punto detras se lo traga Telegram
    # dentro del enlace y el mapa abre en un sitio que no existe.
    assert not texto.rstrip().endswith(".")
    # Sigue sin hablar del caso.
    assert "caso" not in texto.lower()


def test_cada_quien_recibe_las_señas_de_su_propio_reporte(session):
    """Dos personas en el mismo caso reportaron desde sitios distintos."""
    from datetime import UTC, datetime

    caso = Case(category="agua", status="assigned")
    session.add(caso)
    session.flush()
    for usuario, dia, lon in (("801", 10, -89.20), ("802", 12, -89.21)):
        session.add(
            Report(
                channel="telegram",
                external_user_id=usuario,
                status="received",
                case_id=caso.id,
                created_at=datetime(2026, 9, dia, 18, 0, tzinfo=UTC),
                location=f"SRID=4326;POINT({lon} 13.70)",
            )
        )
    session.commit()

    dispatch.enqueue(session, caso, "assigned")
    session.commit()

    cuerpos = {
        n.external_user_id: n.body
        for n in session.execute(select(Notification).where(Notification.case_id == caso.id))
        .scalars()
        .all()
    }
    assert "-89.200000" in cuerpos["801"]
    assert "-89.210000" in cuerpos["802"]
    assert "10 de septiembre" in cuerpos["801"]
    assert "12 de septiembre" in cuerpos["802"]


# --- Cerrar exige evidencia ---


def test_no_se_cierra_sin_foto_del_arreglo(sesion, session, cuadrilla):
    """Cerrar sin evidencia convierte el cierre en una afirmacion que nadie
    puede comprobar."""
    caso = caso_con_reportes(session, ["401"])
    en_curso(sesion, caso.id, cuadrilla)

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


def test_la_evidencia_se_valida_abriendola(sesion, session, cuadrilla):
    """Un archivo con cabecera JPEG y basura detras revienta despues."""
    caso = caso_con_reportes(session, ["501"])
    en_curso(sesion, caso.id, cuadrilla)
    falso = b"\\xff\\xd8\\xff\\xe0" + b"basura" * 200

    r = sesion.post(
        f"/board/cases/{caso.id}/evidence",
        files={"archivo": ("falsa.jpg", falso, "image/jpeg")},
    )

    assert r.status_code == 400
    assert session.execute(select(func.count(CasePhoto.id))).scalar_one() == 0


def test_la_evidencia_guarda_quien_la_subio(sesion, session, cuadrilla):
    """Una evidencia sin autor no se puede cuestionar."""
    caso = caso_con_reportes(session, ["601"])
    en_curso(sesion, caso.id, cuadrilla)
    subir_evidencia(sesion, caso.id)

    foto = session.execute(select(CasePhoto)).scalar_one()
    assert foto.uploaded_by == settings.demo_email
    assert foto.storage_key and foto.thumbnail_key
    assert foto.content_sha256


def test_la_evidencia_no_entra_en_la_agrupacion(sesion, session, cuadrilla):
    """Va en tabla propia justo para que no pueda.

    Compartiendo tabla con las de reporte, olvidar un `WHERE kind='report'` una
    sola vez meteria la foto del arreglo como si fuera otro reporte del problema.
    """
    from app.models import ReportPhoto

    caso = caso_con_reportes(session, ["701"])
    en_curso(sesion, caso.id, cuadrilla)
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
    en_curso(sesion, caso.id, cuadrilla)
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
    en_curso(sesion, caso.id, cuadrilla)
    subir_evidencia(sesion, caso.id)
    sesion.post(f"/board/cases/{caso.id}/close?nota=Listo")

    # Dos de asignacion, dos de "en curso" y dos de cierre. En varias pasadas:
    # el trabajador toma tandas de `worker_batch_size`, que son menos que seis.
    total = 0
    while (n := notify_worker.run_once(session)) > 0:
        total += n
    assert total == 6

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
    en_curso(sesion, caso.id, cuadrilla)
    subir_evidencia(sesion, caso.id)
    r = sesion.post(f"/board/cases/{caso.id}/close")

    assert r.status_code == 200
    session.refresh(caso)
    assert caso.status == "closed"


# --- El aviso de cierre lleva la foto del arreglo ---
#
# Quien reporto es quien mejor sabe si de verdad se arreglo: la foto es lo que
# le deja comprobarlo. Y la foto acompaña al aviso; nunca es la razon de que no
# llegue.


def _cerrar_con_foto(sesion, session, cuadrilla, usuario: str) -> Case:
    caso = caso_con_reportes(session, [usuario])
    en_curso(sesion, caso.id, cuadrilla)
    subir_evidencia(sesion, caso.id)
    assert sesion.post(f"/board/cases/{caso.id}/close?nota=Listo").status_code == 200
    return caso


def _vaciar_cola(session) -> None:
    while notify_worker.run_once(session) > 0:
        pass


def _aviso_de_cierre(session) -> Notification:
    aviso = session.execute(select(Notification).where(Notification.kind == "closed")).scalar_one()
    session.refresh(aviso)
    return aviso


def test_el_aviso_de_cierre_lleva_la_foto_del_arreglo(sesion, session, cuadrilla, monkeypatch):
    textos: list[str] = []
    fotos: list[tuple[bytes, str]] = []

    async def texto(self, external_user_id, text):
        textos.append(text)

    async def con_foto(self, external_user_id, photo, caption):
        fotos.append((photo, caption))

    monkeypatch.setattr(TelegramChannel, "notify", texto)
    monkeypatch.setattr(TelegramChannel, "notify_photo", con_foto)

    _cerrar_con_foto(sesion, session, cuadrilla, "1601")
    _vaciar_cola(session)

    # Asignado y en curso van como texto; el cierre, con su foto. Se compara
    # con el texto exacto: «resuelto» lo dice tambien el de asignacion.
    cierre = _aviso_de_cierre(session).body
    assert len(textos) == 2
    assert cierre not in textos
    assert len(fotos) == 1
    foto, pie = fotos[0]
    assert pie == cierre
    with Image.open(io.BytesIO(foto)) as img:
        assert img.format == "JPEG"
        assert max(img.size) <= settings.notify_photo_width


def test_si_telegram_rechaza_la_foto_el_aviso_sale_como_texto(
    sesion, session, cuadrilla, monkeypatch
):
    textos: list[str] = []

    async def texto(self, external_user_id, text):
        textos.append(text)

    async def rechaza(self, external_user_id, photo, caption):
        raise RuntimeError("Bad Request: PHOTO_INVALID_DIMENSIONS")

    monkeypatch.setattr(TelegramChannel, "notify", texto)
    monkeypatch.setattr(TelegramChannel, "notify_photo", rechaza)

    _cerrar_con_foto(sesion, session, cuadrilla, "1602")
    _vaciar_cola(session)

    aviso = _aviso_de_cierre(session)
    assert aviso.body in textos
    assert aviso.status == "sent"


def test_un_corte_de_red_con_foto_se_reintenta_con_foto(sesion, session, cuadrilla, monkeypatch):
    """Caer al texto por un corte de red perderia la foto sin motivo."""
    textos: list[str] = []

    async def texto(self, external_user_id, text):
        textos.append(text)

    async def se_cae(self, external_user_id, photo, caption):
        raise ConnectionError("la red")

    monkeypatch.setattr(TelegramChannel, "notify", texto)
    monkeypatch.setattr(TelegramChannel, "notify_photo", se_cae)

    _cerrar_con_foto(sesion, session, cuadrilla, "1603")
    _vaciar_cola(session)

    aviso = _aviso_de_cierre(session)
    assert aviso.status == "pending"
    assert aviso.next_attempt_at is not None
    assert aviso.body not in textos


def test_a_quien_bloqueo_el_bot_tampoco_se_le_reintenta_la_foto(
    sesion, session, cuadrilla, monkeypatch
):
    async def texto(self, external_user_id, text):
        pass

    async def bloqueado(self, external_user_id, photo, caption):
        raise RuntimeError("Forbidden: bot was blocked by the user")

    monkeypatch.setattr(TelegramChannel, "notify", texto)
    monkeypatch.setattr(TelegramChannel, "notify_photo", bloqueado)

    _cerrar_con_foto(sesion, session, cuadrilla, "1604")
    _vaciar_cola(session)

    aviso = _aviso_de_cierre(session)
    assert aviso.status == "failed"
    assert aviso.attempts == 1


# --- La foto del arreglo y el cierre, solo en curso ---
#
# Antes se podia ir de abierto a cerrado subiendo una foto, sin asignar a nadie:
# quien reporto recibia «resuelto» sin haber sabido nunca que alguien iba.


def _cuantas_evidencias(session) -> int:
    return session.execute(select(func.count(CasePhoto.id))).scalar_one()


def test_no_se_sube_la_foto_con_el_caso_abierto(sesion, session):
    caso = caso_con_reportes(session, ["1601"])

    r = sesion.post(
        f"/board/cases/{caso.id}/evidence",
        files={"archivo": ("arreglo.jpg", foto_sintetica(semilla=92), "image/jpeg")},
    )

    assert r.status_code == 409
    assert "trabajando" in r.json()["detail"]
    assert _cuantas_evidencias(session) == 0


def test_no_se_sube_la_foto_con_el_caso_solo_asignado(sesion, session, cuadrilla):
    caso = caso_con_reportes(session, ["1701"])
    sesion.post(f"/board/cases/{caso.id}/assign?crew_id={cuadrilla.id}")

    r = sesion.post(
        f"/board/cases/{caso.id}/evidence",
        files={"archivo": ("arreglo.jpg", foto_sintetica(semilla=93), "image/jpeg")},
    )

    assert r.status_code == 409
    assert "trabajando" in r.json()["detail"]
    assert _cuantas_evidencias(session) == 0


def test_no_se_cierra_asignado_aunque_haya_foto(sesion, session, cuadrilla):
    """La foto no basta: el caso tiene que estar en curso al cerrar."""
    caso = caso_con_reportes(session, ["1801"])
    en_curso(sesion, caso.id, cuadrilla)
    subir_evidencia(sesion, caso.id)
    # Vuelve a asignado con la foto ya puesta.
    assert sesion.post(f"/board/cases/{caso.id}/status?nuevo=assigned").status_code == 200

    r = sesion.post(f"/board/cases/{caso.id}/close")

    assert r.status_code == 409
    assert "trabajando" in r.json()["detail"]
    session.refresh(caso)
    assert caso.status == "assigned"
    cierres = session.execute(
        select(func.count(Notification.id)).where(Notification.kind == "closed")
    ).scalar_one()
    assert cierres == 0


def test_no_se_cierra_por_el_cambio_de_estado(sesion, session):
    """La puerta lateral: cerraba sin foto, sin `closed_at` y sin avisar."""
    caso = caso_con_reportes(session, ["1901"])

    r = sesion.post(f"/board/cases/{caso.id}/status?nuevo=closed")

    assert r.status_code == 409
    session.refresh(caso)
    assert caso.status == "open"
    assert caso.closed_at is None


def test_el_camino_completo_avisa_en_orden(sesion, session, cuadrilla):
    """Abierto, asignado, en curso, foto, cerrado: los tres avisos, en orden."""
    caso = caso_con_reportes(session, ["2001"])

    en_curso(sesion, caso.id, cuadrilla)
    subir_evidencia(sesion, caso.id)
    r = sesion.post(f"/board/cases/{caso.id}/close?nota=Listo")

    assert r.status_code == 200
    session.refresh(caso)
    assert caso.status == "closed"
    assert caso.closed_at is not None
    tipos = (
        session.execute(
            select(Notification.kind)
            .where(Notification.external_user_id == "2001")
            .order_by(Notification.created_at)
        )
        .scalars()
        .all()
    )
    assert tipos == ["assigned", "in_progress", "closed"]


# --- El contador del panel cuenta personas, no mensajes ---
#
# Con un solo reporte de una sola persona, tras asignar y marcar en curso, el
# panel decia «se aviso a 2 personas»: eran sus dos avisos.


def _marcar_avisos(session, caso_id, estado: str = "sent") -> None:
    for n in session.execute(select(Notification).where(Notification.case_id == caso_id)).scalars():
        n.status = estado
    session.commit()


def _contador(sesion, caso_id) -> dict:
    r = sesion.get(f"/board/cases/{caso_id}")
    assert r.status_code == 200, r.text
    return r.json()["notifications"]


def test_una_persona_con_dos_avisos_cuenta_una_vez(sesion, session, cuadrilla):
    caso = caso_con_reportes(session, ["2101"])
    en_curso(sesion, caso.id, cuadrilla)
    _marcar_avisos(session, caso.id)

    assert _contador(sesion, caso.id) == {"sent": 1, "pending": 0, "failed": 0}


def test_dos_personas_son_dos(sesion, session, cuadrilla):
    caso = caso_con_reportes(session, ["2201", "2202"])
    en_curso(sesion, caso.id, cuadrilla)
    _marcar_avisos(session, caso.id)

    assert _contador(sesion, caso.id) == {"sent": 2, "pending": 0, "failed": 0}


def test_cada_persona_cae_en_su_peor_estado(sesion, session, cuadrilla):
    """Los tres numeros suman exactamente las personas."""
    caso = caso_con_reportes(session, ["2301", "2302"])
    en_curso(sesion, caso.id, cuadrilla)
    _marcar_avisos(session, caso.id)
    uno = (
        session.execute(
            select(Notification).where(
                Notification.case_id == caso.id, Notification.external_user_id == "2302"
            )
        )
        .scalars()
        .first()
    )
    uno.status = "failed"
    session.commit()

    assert _contador(sesion, caso.id) == {"sent": 1, "pending": 0, "failed": 1}
