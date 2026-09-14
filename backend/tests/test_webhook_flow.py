"""El recorrido del reporte: foto, ubicacion, reporte completo."""

from sqlalchemy import text

from app import ingest
from app.config import settings
from app.webhook import SECRET_HEADER
from tests.conftest import SECRETO_DE_PRUEBA
from tests.factories import (
    update_con_foto,
    update_con_sticker,
    update_con_texto,
    update_con_ubicacion,
)

URL = "/webhooks/telegram"
CAB = {SECRET_HEADER: SECRETO_DE_PRUEBA}


def post(client, payload):
    return client.post(URL, json=payload, headers=CAB)


def test_foto_crea_reporte_incompleto_y_pide_ubicacion(client, session):
    r = post(client, update_con_foto())
    assert r.status_code == 200

    cuerpo = r.json()
    assert cuerpo["method"] == "sendMessage"
    # El boton nativo, que es de donde sale la ubicacion. Nunca de los EXIF:
    # Telegram comprime las fotos y les quita los metadatos.
    assert cuerpo["reply_markup"]["keyboard"][0][0]["request_location"] is True

    fila = session.execute(text("SELECT status, caption, location FROM reports")).one()
    assert fila.status == "incomplete"
    assert fila.caption == "hueco frente a la casa"
    assert fila.location is None


def test_foto_guarda_el_comprobante_y_deja_la_subida_pendiente(client, session):
    post(client, update_con_foto())
    foto = session.execute(
        text(
            "SELECT external_file_id, external_file_unique_id, declared_bytes, "
            "width, storage_key, status FROM report_photos"
        )
    ).one()
    # El tamano grande, no la miniatura que genera Telegram.
    assert foto.external_file_id == "grande"
    assert foto.external_file_unique_id == "u_grande"
    assert foto.width == 1280
    assert foto.declared_bytes == 240_000
    # La subida es de la fase 2: aca solo queda la fila lista.
    assert foto.storage_key is None
    assert foto.status == "pending"


def test_ubicacion_completa_el_reporte(client, session):
    post(client, update_con_foto(update_id=1))
    r = post(client, update_con_ubicacion(update_id=2, lat=13.6929, lon=-89.2182))

    assert r.json()["text"] == ingest.LISTO
    fila = session.execute(
        text(
            "SELECT status, ST_Y(location::geometry) AS lat, "
            "ST_X(location::geometry) AS lon FROM reports"
        )
    ).one()
    assert fila.status == "received"
    assert round(fila.lat, 4) == 13.6929
    assert round(fila.lon, 4) == -89.2182


def test_ubicacion_sin_foto_pide_la_foto(client, session):
    r = post(client, update_con_ubicacion())
    assert r.json()["text"] == ingest.SIN_FOTO
    assert session.execute(text("SELECT count(*) FROM reports")).scalar() == 0


def test_segunda_foto_se_suma_al_mismo_reporte(client, session):
    """Telegram manda los albumes como updates separados del mismo problema.

    Si cada foto abriera un reporte, un album de tres seria tres reportes del
    mismo hueco, que es justo el error que el sistema existe para evitar.
    """
    post(client, update_con_foto(update_id=1))
    post(client, update_con_foto(update_id=2, caption=None))

    assert session.execute(text("SELECT count(*) FROM reports")).scalar() == 1
    assert session.execute(text("SELECT count(*) FROM report_photos")).scalar() == 2


def test_update_repetido_no_duplica(client, session):
    """Telegram reenvia el update si el webhook tarda. Eso no es otro reporte."""
    payload = update_con_foto(update_id=77)
    assert post(client, payload).status_code == 200
    assert post(client, payload).status_code == 200

    assert session.execute(text("SELECT count(*) FROM inbound_updates")).scalar() == 1
    assert session.execute(text("SELECT count(*) FROM reports")).scalar() == 1
    assert session.execute(text("SELECT count(*) FROM report_photos")).scalar() == 1


def test_foto_demasiado_grande_se_rechaza_sin_descargar(client, session, monkeypatch):
    monkeypatch.setattr(settings, "max_photo_bytes", 100_000)
    r = post(client, update_con_foto(file_size=5_000_000))
    assert r.json()["text"] == ingest.FOTO_MUY_GRANDE
    assert session.execute(text("SELECT count(*) FROM report_photos")).scalar() == 0


def test_texto_suelto_pide_foto(client):
    assert post(client, update_con_texto()).json()["text"] == ingest.PEDIR_FOTO


def test_sticker_no_rompe_y_contesta(client, session):
    """Un bot publico recibe cosas que no son reportes desde el primer dia."""
    r = post(client, update_con_sticker())
    assert r.status_code == 200
    assert r.json()["text"] == ingest.NO_ENTIENDO
    # Se guarda crudo igual: sirve para saber que manda la gente de verdad.
    assert session.execute(text("SELECT count(*) FROM inbound_updates")).scalar() == 1
    assert session.execute(text("SELECT count(*) FROM reports")).scalar() == 0


def test_update_desconocido_se_guarda_crudo(client, session):
    """Un tipo de update que no sabemos leer no se pierde ni hace reintentar."""
    r = post(client, {"update_id": 900, "poll": {"id": "1", "question": "?", "options": []}})
    assert r.status_code == 200
    assert session.execute(text("SELECT count(*) FROM inbound_updates")).scalar() == 1


def test_update_sin_id_no_se_guarda(client, session):
    r = post(client, {"mensaje": "esto no es un update"})
    assert r.status_code == 200
    assert session.execute(text("SELECT count(*) FROM inbound_updates")).scalar() == 0


def test_dos_personas_no_comparten_reporte(client, session):
    """El reporte abierto es de quien lo empezo, no del que mande antes."""
    post(client, update_con_foto(update_id=1, user_id=111))
    r = post(client, update_con_ubicacion(update_id=2, user_id=222))

    assert r.json()["text"] == ingest.SIN_FOTO
    fila = session.execute(text("SELECT status FROM reports")).one()
    assert fila.status == "incomplete"


def test_ubicacion_invalida_se_rechaza(client, session):
    post(client, update_con_foto(update_id=1))
    r = post(client, update_con_ubicacion(update_id=2, lat=999.0, lon=-89.2))
    assert r.json()["text"] == ingest.UBICACION_INVALIDA
    fila = session.execute(text("SELECT status FROM reports")).one()
    assert fila.status == "incomplete"


def test_update_marcado_como_procesado(client, session):
    post(client, update_con_foto())
    fila = session.execute(text("SELECT processed_at, process_error FROM inbound_updates")).one()
    assert fila.processed_at is not None
    assert fila.process_error is None


# --- La descripcion: no se pide, pero no se tira ---


def test_texto_despues_de_completar_se_pega_al_reporte(client, session):
    """Lo que alguien escribe por su cuenta es una senal, no ruido.

    La fase 4 agrupa por semejanza visual **y textual**. Descartar el texto
    seria tirar materia prima de la parte dificil del proyecto.
    """
    post(client, update_con_foto(update_id=1))
    post(client, update_con_ubicacion(update_id=2))
    r = post(client, update_con_texto(update_id=3, texto="hueco enorme frente al colegio"))

    assert r.json()["text"] == ingest.DETALLE_GUARDADO
    fila = session.execute(text("SELECT status, caption FROM reports")).one()
    assert fila.status == "received"
    assert "hueco enorme frente al colegio" in fila.caption


def test_texto_con_reporte_incompleto_anota_y_sigue_pidiendo_ubicacion(client, session):
    post(client, update_con_foto(update_id=1, caption=None))
    r = post(client, update_con_texto(update_id=2, texto="se inunda cuando llueve"))

    assert r.json()["text"] == ingest.DETALLE_Y_FALTA_UBICACION
    # El botón sigue ahí: falta lo único sin lo cual no se puede agrupar.
    assert r.json()["reply_markup"]["keyboard"][0][0]["request_location"] is True
    fila = session.execute(text("SELECT status, caption FROM reports")).one()
    assert fila.status == "incomplete"
    assert "se inunda cuando llueve" in fila.caption


def test_texto_se_acumula_no_se_pisa(client, session):
    """Dos frases sueltas son dos frases, no la ultima."""
    post(client, update_con_foto(update_id=1, caption="hueco"))
    post(client, update_con_texto(update_id=2, texto="del lado derecho"))
    post(client, update_con_texto(update_id=3, texto="ya tiene semanas"))

    caption = session.execute(text("SELECT caption FROM reports")).scalar()
    assert "hueco" in caption
    assert "del lado derecho" in caption
    assert "ya tiene semanas" in caption


def test_texto_repetido_no_se_duplica(client, session):
    post(client, update_con_foto(update_id=1, caption=None))
    post(client, update_con_texto(update_id=2, texto="es peligroso"))
    post(client, update_con_texto(update_id=3, texto="es peligroso"))

    caption = session.execute(text("SELECT caption FROM reports")).scalar()
    assert caption.count("es peligroso") == 1


def test_texto_sin_reporte_previo_pide_foto(client, session):
    r = post(client, update_con_texto(texto="hay un hueco"))
    assert r.json()["text"] == ingest.PEDIR_FOTO
    assert session.execute(text("SELECT count(*) FROM reports")).scalar() == 0


def test_texto_no_crece_sin_fin(client, session):
    """Un solo reporte no puede engordar a fuerza de mensajes sueltos."""
    post(client, update_con_foto(update_id=1, caption=None))
    for i in range(2, 12):
        post(client, update_con_texto(update_id=i, texto=f"detalle numero {i} " + "x" * 300))

    caption = session.execute(text("SELECT caption FROM reports")).scalar()
    assert len(caption) <= ingest.CAPTION_MAX


def test_la_descripcion_se_ofrece_pero_no_se_exige(client, session):
    """El reporte queda completo sin escribir una palabra.

    Quien reporta esta parado frente al problema y con prisa: un paso
    obligatorio mas es friccion sobre el sensor.
    """
    post(client, update_con_foto(update_id=1, caption=None))
    r = post(client, update_con_ubicacion(update_id=2))

    fila = session.execute(text("SELECT status, caption FROM reports")).one()
    assert fila.status == "received"
    assert fila.caption is None
    # Se menciona, sin botón ni obligación.
    assert "escribime" in r.json()["text"]
