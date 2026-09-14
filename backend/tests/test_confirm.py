"""La confirmacion de la categoria.

El modelo propone, el codigo decide, y **la persona confirma**. Estas pruebas
cubren esa ultima parte: que el boton vuelva, que solo su dueño pueda usarlo, y
que el webhook la conteste entera sin salir a la red.
"""

import uuid

import pytest

from app import confirm
from app.channels.telegram import TelegramChannel
from app.models import Classification, Report
from app.taxonomy import Category
from app.webhook import SECRET_HEADER
from tests.conftest import SECRETO_DE_PRUEBA
from tests.factories import update_con_boton

URL = "/webhooks/telegram"
CAB = {SECRET_HEADER: SECRETO_DE_PRUEBA}
USUARIO = 4242


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    """Cualquier llamada de red desde el webhook hace fallar la prueba.

    Es la prueba del bug: la confirmacion salia por BackgroundTasks a mandar un
    mensaje, o sea una llamada saliente dentro del webhook. Rompia la regla de
    la fase 1 y se veia como un boton girando segundos.
    """

    async def prohibido(*args, **kwargs):
        raise AssertionError("el webhook no puede hacer llamadas de red")

    monkeypatch.setattr(TelegramChannel, "notify", prohibido)
    monkeypatch.setattr(TelegramChannel, "ask_out_of_band", prohibido)
    monkeypatch.setattr(TelegramChannel, "fetch_media", prohibido)


@pytest.fixture
def propuesta(session):
    reporte = Report(channel="telegram", external_user_id=str(USUARIO), status="received")
    session.add(reporte)
    session.flush()
    c = Classification(
        report_id=reporte.id,
        status="proposed",
        proposed_category=Category.VIALIDAD.value,
        proposed_severity="media",
        proposed_reason="Se ve un bache en el asfalto.",
        model="claude-haiku-4-5",
    )
    session.add(c)
    session.commit()
    return c


def post(client, payload):
    return client.post(URL, json=payload, headers=CAB)


def test_confirmar_deja_la_categoria_propuesta(client, session, propuesta):
    r = post(client, update_con_boton(data=f"s:{propuesta.id}"))

    assert r.status_code == 200
    # Se contesta dentro de la misma respuesta HTTP, sin mandar nada aparte.
    cuerpo = r.json()
    assert cuerpo["method"] == "editMessageText"

    session.refresh(propuesta)
    assert propuesta.status == "confirmed"
    assert propuesta.final_category == Category.VIALIDAD.value
    assert propuesta.confirmed_at is not None


def test_confirmar_se_ve_en_el_chat(client, session, propuesta):
    """El bug: confirmar parecia no hacer nada.

    Se contestaba con `answerCallbackQuery`, que Telegram pinta como un aviso
    de un segundo sobre el chat. Corregir —el camino raro— reescribia el
    mensaje y si se veia; confirmar —el camino normal— no dejaba rastro.
    Alguien probo desde su telefono, le dio dos veces, y las dos veces habia
    funcionado.
    """
    r = post(client, update_con_boton(data=f"s:{propuesta.id}", message_id=900))
    cuerpo = r.json()

    assert cuerpo["method"] == "editMessageText"
    assert cuerpo["message_id"] == 900
    # El texto reemplaza a la propuesta, asi que tiene que repetir que se
    # confirmo: si solo dijera "gracias", el chat perderia el dato.
    assert "Calle o acera" in cuerpo["text"]
    # Sin botones: ya no hay nada que elegir.
    assert "reply_markup" not in cuerpo


def test_corregir_muestra_las_categorias(client, session, propuesta):
    r = post(client, update_con_boton(data=f"n:{propuesta.id}", message_id=901))
    cuerpo = r.json()

    # Edita el mensaje en el sitio: no acumula preguntas viejas con botones
    # que ya no valen.
    assert cuerpo["method"] == "editMessageText"
    assert cuerpo["message_id"] == 901
    etiquetas = [b[0]["text"] for b in cuerpo["reply_markup"]["inline_keyboard"]]
    assert "Alumbrado" in etiquetas
    assert len(etiquetas) == len(Category)

    session.refresh(propuesta)
    # Todavia no se decidio nada.
    assert propuesta.final_category is None


def test_elegir_otra_categoria_la_marca_corregida(client, session, propuesta):
    from app.taxonomy import categorias_reales

    indice = categorias_reales().index(Category.AGUA)
    r = post(client, update_con_boton(data=f"c:{propuesta.id}:{indice}"))

    cuerpo = r.json()
    assert cuerpo["method"] == "editMessageText"
    # Nombra la categoria elegida, no la que se habia propuesto.
    assert "Agua o drenaje" in cuerpo["text"]
    assert "reply_markup" not in cuerpo

    session.refresh(propuesta)
    assert propuesta.status == "corrected"
    assert propuesta.final_category == Category.AGUA.value
    # La severidad propuesta se conserva: corrigio la categoria, no dijo nada
    # de la urgencia, e inventarsela seria ponerle palabras.
    assert propuesta.final_severity == "media"


def test_nadie_puede_confirmar_el_reporte_de_otro(client, session, propuesta):
    """El callback_data lo manda el cliente y se puede falsear.

    Sin comprobar el dueño, cualquiera que adivine un uuid confirmaria reportes
    ajenos, y el tablero mostraria categorias que su autor nunca aprobo.
    """
    r = post(client, update_con_boton(user_id=99999, data=f"s:{propuesta.id}"))

    assert r.json()["text"] == confirm.NO_ENCONTRADO
    session.refresh(propuesta)
    assert propuesta.status == "proposed"
    assert propuesta.final_category is None


def test_confirmar_dos_veces_no_pisa_la_primera(client, session, propuesta):
    post(client, update_con_boton(update_id=60, data=f"s:{propuesta.id}"))
    session.refresh(propuesta)
    primera = propuesta.confirmed_at

    r = post(client, update_con_boton(update_id=61, data=f"s:{propuesta.id}"))
    assert r.json()["text"] == confirm.YA_CONFIRMADO

    session.refresh(propuesta)
    assert propuesta.confirmed_at == primera


def test_uuid_inventado_no_revienta(client, session):
    r = post(client, update_con_boton(data=f"s:{uuid.uuid4()}"))
    assert r.status_code == 200
    assert r.json()["text"] == confirm.NO_ENCONTRADO


def test_callback_con_basura_no_revienta(client):
    for basura in ("", "x", "s:no-es-uuid", "c:abc:99", "c::", "z:1"):
        r = post(client, update_con_boton(data=basura))
        assert r.status_code == 200


def test_indice_de_categoria_fuera_de_rango(client, session, propuesta):
    r = post(client, update_con_boton(data=f"c:{propuesta.id}:99"))
    assert r.json()["text"] == confirm.NO_ENCONTRADO
    session.refresh(propuesta)
    assert propuesta.final_category is None


def test_el_callback_data_cabe_en_telegram(session, propuesta):
    """Telegram corta callback_data en 64 bytes y falla la llamada entera."""
    _, opciones = confirm.pregunta(propuesta)
    _, categorias = confirm.opciones_de_categoria(propuesta)

    for _, valor in opciones + categorias:
        assert len(valor.encode()) <= 64, valor
