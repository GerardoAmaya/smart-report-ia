"""Cuando el modelo no contesta, la categoria la elige la persona.

Existe por un hueco real: una clasificacion en `failed` dejaba el reporte sin
categoria para siempre. No se agrupaba, no aparecia como caso, y el bot ya le
habia dicho a quien reporto que la revision venia en camino. Lo dispara algo
tan comun como quedarse sin saldo en el modelo.
"""

import pytest

from app import classify_worker
from app.channels.telegram import TelegramChannel
from app.config import settings
from app.models import Classification, Report
from app.taxonomy import Category
from app.webhook import SECRET_HEADER
from tests.conftest import SECRETO_DE_PRUEBA
from tests.factories import update_con_boton

USUARIO = 4242
preguntas: list[dict] = []


@pytest.fixture(autouse=True)
def telegram_anotado(monkeypatch):
    """Recoge lo que el trabajador le pregunta a la persona, sin red."""
    preguntas.clear()

    async def anotar(self, external_user_id, text, options):
        preguntas.append({"chat_id": external_user_id, "text": text, "options": options})

    async def sin_red(self, *args, **kwargs):
        return None

    monkeypatch.setattr(TelegramChannel, "ask_out_of_band", anotar)
    monkeypatch.setattr(TelegramChannel, "edit_out_of_band", sin_red)


@pytest.fixture
def modelo_caido(monkeypatch):
    def falla(session, clasificacion):
        raise RuntimeError("credit balance is too low")

    monkeypatch.setattr(classify_worker, "process_one", falla)


@pytest.fixture
def ultimo_intento(session):
    """Una clasificacion a la que solo le queda un intento."""
    reporte = Report(channel="telegram", external_user_id=str(USUARIO), status="received")
    session.add(reporte)
    session.flush()
    c = Classification(
        report_id=reporte.id,
        status="pending",
        attempts=settings.classify_max_attempts - 1,
    )
    session.add(c)
    session.commit()
    return c


def test_al_fallar_se_le_pide_la_categoria_a_la_persona(session, modelo_caido, ultimo_intento):
    classify_worker.run_once(session)

    session.refresh(ultimo_intento)
    assert ultimo_intento.status == "failed"

    assert len(preguntas) == 1
    pregunta = preguntas[0]
    assert pregunta["chat_id"] == str(USUARIO)
    assert pregunta["text"] == (
        "No pude revisar la foto automáticamente. ¿Qué tipo de problema es?"
    )
    # Los mismos botones que al corregir: la respuesta entra por ese camino.
    datos = [valor for _, valor in pregunta["options"]]
    assert f"c:{ultimo_intento.id}:0" in datos
    assert f"c:{ultimo_intento.id}:x" in datos


def test_se_pregunta_una_sola_vez(session, modelo_caido, ultimo_intento):
    classify_worker.run_once(session)
    classify_worker.run_once(session)
    classify_worker.run_once(session)

    assert len(preguntas) == 1


def test_un_reintento_no_le_pregunta_nada(session, modelo_caido, ultimo_intento):
    """Mientras queden intentos, el modelo todavia puede contestar."""
    ultimo_intento.attempts = 0
    session.commit()

    classify_worker.run_once(session)

    session.refresh(ultimo_intento)
    assert ultimo_intento.status == "pending"
    assert preguntas == []


def test_si_telegram_falla_el_trabajador_sigue(session, modelo_caido, ultimo_intento, monkeypatch):
    async def se_cae(self, *args, **kwargs):
        raise ConnectionError("telegram no contesta")

    monkeypatch.setattr(TelegramChannel, "ask_out_of_band", se_cae)

    classify_worker.run_once(session)

    session.refresh(ultimo_intento)
    assert ultimo_intento.status == "failed"


def test_elegir_la_categoria_la_deja_con_severidad(client, session, modelo_caido, ultimo_intento):
    """Sin propuesta no hay severidad que conservar; el caso necesita una."""
    classify_worker.run_once(session)

    r = client.post(
        "/webhooks/telegram",
        json=update_con_boton(user_id=USUARIO, data=f"c:{ultimo_intento.id}:0"),
        headers={SECRET_HEADER: SECRETO_DE_PRUEBA},
    )
    assert r.status_code == 200

    session.refresh(ultimo_intento)
    assert ultimo_intento.final_category == Category.VIALIDAD.value
    assert ultimo_intento.final_severity == "media"
    assert ultimo_intento.confirmed_at is not None


def test_elegir_sin_propuesta_queda_elegida_y_no_corregida(
    client, session, modelo_caido, ultimo_intento
):
    """Sin propuesta nadie corrigio al modelo: la persona eligio desde cero.

    Quedaba como "corrected" y el tablero decia «La persona corrigió la
    categoría que propuso el modelo», cuando el modelo no propuso nada.
    """
    classify_worker.run_once(session)

    client.post(
        "/webhooks/telegram",
        json=update_con_boton(user_id=USUARIO, data=f"c:{ultimo_intento.id}:0"),
        headers={SECRET_HEADER: SECRETO_DE_PRUEBA},
    )

    session.refresh(ultimo_intento)
    assert ultimo_intento.status == "chosen"
    assert ultimo_intento.proposed_category is None
