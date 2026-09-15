"""La direccion escrita.

El punto es el dato y la direccion la comodidad, asi que casi todas estas
pruebas son sobre lo que pasa **cuando no se puede resolver**: que no se invente
nada, que no se reintente para siempre lo que ya se sabe, y que el aviso siga
llevando a la cuadrilla al sitio correcto sin ella.
"""

from datetime import UTC, datetime

import httpx
import pytest

from app import geocode, geocode_worker
from app.config import settings
from app.models import Report


class RespuestaFalsa:
    def __init__(self, status_code=200, datos=None, texto=None):
        self.status_code = status_code
        self._datos = datos
        self._texto = texto

    def json(self):
        if self._texto is not None:
            raise ValueError("no es JSON")
        return self._datos


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    """El tope de una por segundo es real, pero no hace falta pagarlo aqui."""
    monkeypatch.setattr(settings, "geocode_min_interval_seconds", 0.0)


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    """Por omision no se sale a la red, y cada prueba pone lo que contesta.

    Sin esto, una prueba a la que se le olvide el parcheo le pega al servicio
    publico de verdad: lento, distinto cada dia, y consumiendo la cuota de
    alguien. Un fallo asi se disfraza de prueba inestable.
    """

    def prohibido(*args, **kwargs):
        raise AssertionError("esta prueba iba a salir a la red")

    monkeypatch.setattr(geocode.httpx, "get", prohibido)


def responder(monkeypatch, respuesta):
    def falso(*args, **kwargs):
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    monkeypatch.setattr(geocode.httpx, "get", falso)


# --- Como se arma la direccion ---


def test_usa_calle_colonia_y_ciudad():
    assert (
        geocode._componer(
            {"road": "Alameda Araujo", "suburb": "Colonia San Francisco", "city": "San Salvador"}
        )
        == "Alameda Araujo, Colonia San Francisco, San Salvador"
    )


def test_sin_calle_se_queda_con_la_colonia():
    """Pasa de verdad: en la Escalon el punto cae dentro de una urbanizacion."""
    assert geocode._componer({"suburb": "Colonia Escalón", "city": "San Salvador"}) == (
        "Colonia Escalón, San Salvador"
    )


def test_sin_calle_ni_colonia_no_hay_direccion():
    """«San Salvador» a secas no lleva a nadie a ningun lado.

    Y una direccion que no sirve para llegar es peor que el enlace al punto,
    porque parece que sirve.
    """
    assert geocode._componer({"city": "San Salvador", "country": "El Salvador"}) is None


def test_no_repite_cuando_colonia_y_ciudad_coinciden():
    assert geocode._componer({"road": "Calle Real", "suburb": "Nejapa", "city": "Nejapa"}) == (
        "Calle Real, Nejapa"
    )


def test_nunca_usa_el_nombre_del_lugar():
    """El servicio devuelve el negocio mas cercano; eso no es la direccion.

    «Megacentro de Vacunacion» como direccion de un bache manda a la cuadrilla
    a mirar la puerta equivocada.
    """
    datos = {
        "display_name": "Megacentro de Vacunacion, Alameda Araujo, San Salvador",
        "name": "Megacentro de Vacunacion",
        "address": {"road": "Alameda Araujo", "city": "San Salvador"},
    }
    assert "Megacentro" not in (geocode._componer(datos["address"]) or "")


# --- Cuando el servicio falla ---


def test_el_servicio_frenandonos_es_transitorio(monkeypatch):
    responder(monkeypatch, RespuestaFalsa(status_code=429))
    with pytest.raises(geocode.FalloTransitorio):
        geocode.reverse(13.7, -89.2)


def test_un_fallo_de_red_es_transitorio(monkeypatch):
    responder(monkeypatch, httpx.ConnectError("sin ruta"))
    with pytest.raises(geocode.FalloTransitorio):
        geocode.reverse(13.7, -89.2)


def test_un_sitio_sin_nombre_no_es_fallo(monkeypatch):
    responder(monkeypatch, RespuestaFalsa(datos={"error": "Unable to geocode"}))
    assert geocode.reverse(13.7, -89.2) is None


def test_se_identifica_como_pide_la_politica(monkeypatch):
    """Sin User-Agent el servicio publico bloquea, y bloquea sin avisar."""
    visto = {}

    def falso(url, params=None, headers=None, timeout=None):
        visto["headers"] = headers
        visto["params"] = params
        return RespuestaFalsa(datos={"address": {"road": "X", "city": "Y"}})

    monkeypatch.setattr(geocode.httpx, "get", falso)
    geocode.reverse(13.7, -89.2)

    assert visto["headers"]["User-Agent"]
    assert visto["params"]["lat"] == "13.700000"


# --- La cola ---


def _reporte(session, lat=13.7, lon=-89.2):
    r = Report(
        channel="telegram",
        external_user_id="900",
        status="received",
        created_at=datetime(2026, 9, 14, 23, 18, tzinfo=UTC),
        location=f"SRID=4326;POINT({lon} {lat})",
    )
    session.add(r)
    session.commit()
    return r


def test_un_sitio_sin_nombre_no_se_reintenta(session, monkeypatch):
    """El bucle que esta prueba evita: reintentar para siempre un descampado.

    Sin marcar la fecha, «se intento y no tiene nombre» seria indistinguible de
    «falta intentarlo», y el reporte volveria a la cola en cada pasada.
    """
    reporte = _reporte(session)
    responder(monkeypatch, RespuestaFalsa(datos={"error": "Unable to geocode"}))

    assert geocode_worker.run_once(session) == 1
    session.refresh(reporte)
    assert reporte.address_text is None
    assert reporte.geocoded_at is not None
    assert geocode_worker.claim(session, 10) == []


def test_un_fallo_del_servicio_deja_el_reporte_en_la_cola(session, monkeypatch):
    reporte = _reporte(session)
    responder(monkeypatch, RespuestaFalsa(status_code=503))

    geocode_worker.run_once(session)
    session.refresh(reporte)
    assert reporte.geocoded_at is None
    assert reporte.geocode_attempts == 1
    assert len(geocode_worker.claim(session, 10)) == 1


def test_deja_de_intentarlo_tras_el_tope(session, monkeypatch):
    """Reintentar sin fin esconde un problema permanente tras una cola."""
    reporte = _reporte(session)
    responder(monkeypatch, RespuestaFalsa(status_code=503))

    for _ in range(settings.geocode_max_attempts + 2):
        geocode_worker.run_once(session)

    session.refresh(reporte)
    assert reporte.geocode_attempts == settings.geocode_max_attempts
    assert geocode_worker.claim(session, 10) == []


def test_apagado_no_toca_la_red(session, monkeypatch):
    """Sin direccion el sistema funciona igual; por eso se puede apagar."""
    _reporte(session)

    def prohibido(*args, **kwargs):
        raise AssertionError("no deberia salir a la red")

    monkeypatch.setattr(geocode.httpx, "get", prohibido)
    monkeypatch.setattr(settings, "geocode_enabled", False)

    assert geocode_worker.run_once(session) == 0


def test_la_direccion_llega_al_aviso(session, monkeypatch):
    from app import dispatch
    from app.models import Case

    caso = Case(category="agua", status="assigned")
    session.add(caso)
    session.flush()
    reporte = _reporte(session)
    reporte.case_id = caso.id
    session.commit()

    responder(
        monkeypatch,
        RespuestaFalsa(datos={"address": {"road": "Calle Real", "city": "Nejapa"}}),
    )
    geocode_worker.run_once(session)
    session.refresh(reporte)

    texto = dispatch.mensaje(caso, "assigned", None, reporte, session)
    assert "en Calle Real, Nejapa." in texto
    # El punto sigue: la direccion es la comodidad, no el dato.
    assert "maps.google.com" in texto
