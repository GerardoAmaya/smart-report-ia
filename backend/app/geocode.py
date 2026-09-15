"""De coordenadas a nombre del sitio.

**El punto es el dato; la direccion es una comodidad.** Lo que recibe la
cuadrilla y lo que decide la agrupacion son las coordenadas. Esto solo pone
palabras encima para que un aviso diga "sobre la Alameda Araujo" en vez de dos
numeros que nadie lee.

De ahi las dos reglas. Si el servicio no contesta o no reconoce el sitio, no se
inventa nada: se deja sin direccion y el mensaje cae en el enlace al punto, que
siempre es correcto. Y la direccion se arma de los campos con estructura
—calle, colonia, ciudad— y nunca del nombre del lugar que devuelve el servicio:
ese nombre es el del negocio o edificio mas cercano, y "Megacentro de
Vacunacion" como direccion de un bache manda a la cuadrilla a mirar la puerta
equivocada.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

log = logging.getLogger("smart_report.geocode")


class FalloTransitorio(Exception):
    """La red o el servicio. Vuelve a la cola."""


def _componer(direccion: dict) -> str | None:
    """Arma la direccion de los campos con estructura.

    Devuelve None cuando no hay ni calle ni colonia: "San Salvador" a secas no
    lleva a nadie a ningun lado, y una direccion que no sirve para llegar es
    peor que el enlace al punto, porque parece que sirve.
    """
    calle = direccion.get("road") or direccion.get("pedestrian") or direccion.get("footway")
    colonia = (
        direccion.get("neighbourhood")
        or direccion.get("suburb")
        or direccion.get("quarter")
        or direccion.get("residential")
    )
    ciudad = (
        direccion.get("city")
        or direccion.get("town")
        or direccion.get("village")
        or direccion.get("municipality")
    )

    if not calle and not colonia:
        return None

    partes = [p for p in (calle, colonia, ciudad) if p]
    # Sin repetir: en algunos sitios la colonia y la ciudad vienen iguales.
    vistas: list[str] = []
    for p in partes:
        if p not in vistas:
            vistas.append(p)
    return ", ".join(vistas)[:200]


def reverse(lat: float, lon: float) -> str | None:
    """El nombre del sitio, o None si no lo tiene.

    Lanza `FalloTransitorio` cuando el que fallo fue el servicio, que es
    distinto de que el sitio no tenga nombre: lo primero se reintenta y lo
    segundo no.
    """
    url = f"{settings.geocode_base_url.rstrip('/')}/reverse"
    parametros = {
        "format": "jsonv2",
        "lat": f"{lat:.6f}",
        "lon": f"{lon:.6f}",
        # Zoom 18 es el nivel de calle. Mas lejos devuelve la ciudad, que ya
        # se descarta abajo; mas cerca devuelve el edificio, que no se usa.
        "zoom": "18",
        "accept-language": "es",
    }
    # El servicio libre exige identificarse con algo que permita contactar.
    # Sin esto bloquea, y bloquea sin avisar.
    cabeceras = {"User-Agent": settings.geocode_user_agent}

    try:
        respuesta = httpx.get(
            url,
            params=parametros,
            headers=cabeceras,
            timeout=settings.geocode_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise FalloTransitorio(str(exc)) from exc

    if respuesta.status_code in (429, 503):
        # Nos estan frenando. Reintentar mas tarde es justo lo correcto.
        raise FalloTransitorio(f"el servicio respondio {respuesta.status_code}")
    if respuesta.status_code >= 500:
        raise FalloTransitorio(f"el servicio respondio {respuesta.status_code}")
    if respuesta.status_code != 200:
        # Un 4xx nuestro no mejora repitiendolo.
        log.warning("geocodificacion rechazada con %s", respuesta.status_code)
        return None

    try:
        datos = respuesta.json()
    except ValueError as exc:
        raise FalloTransitorio("respuesta que no es JSON") from exc

    if not isinstance(datos, dict) or "error" in datos:
        return None

    direccion = datos.get("address")
    if not isinstance(direccion, dict):
        return None
    return _componer(direccion)
