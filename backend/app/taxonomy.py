"""Las categorias del primer alcance, y que significa cada una.

Lo que tienen en comun: se ve, se fotografia, y esta en un punto del mapa.

Las definiciones no son documentacion: **son el prompt**. Lo que dice aca es lo
que el modelo lee, asi que un limite mal escrito aca es una confusion que
aparece en la matriz de confusion de la fase 3.
"""

from __future__ import annotations

from enum import StrEnum


class Category(StrEnum):
    VIALIDAD = "vialidad"
    ALUMBRADO = "alumbrado"
    AGUA = "agua"
    DESECHOS = "desechos"
    RIESGO_ESTRUCTURAL = "riesgo_estructural"
    ESPACIO_PUBLICO = "espacio_publico"
    # No es una categoria del alcance: es la salida para lo que no es un
    # reporte. Un bot publico recibe eso desde el primer dia, y sin esta opcion
    # el modelo se veria obligado a meter una selfie en "vialidad".
    NO_ES_REPORTE = "no_es_reporte"


class Severity(StrEnum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"


DEFINICIONES: dict[Category, str] = {
    Category.VIALIDAD: (
        "Daño en la superficie por donde circulan vehiculos o personas: baches, "
        "hundimientos, grietas, pavimento levantado, tapaderas de pozo hundidas "
        "o faltantes, señalizacion vial caida."
    ),
    Category.ALUMBRADO: (
        "Iluminacion publica: luminarias apagadas, quebradas, colgando o con el "
        "poste dañado. Tambien cables de alumbrado sueltos."
    ),
    Category.AGUA: (
        "Agua donde no deberia estar o ausente donde deberia: fugas, tuberias "
        "rotas, encharcamientos permanentes, drenajes tapados o desbordados, "
        "aguas negras a cielo abierto."
    ),
    Category.DESECHOS: (
        "Basura acumulada, botaderos improvisados, escombros abandonados, "
        "contenedores desbordados o volcados."
    ),
    Category.RIESGO_ESTRUCTURAL: (
        "Algo construido que amenaza con caerse o ceder: muros agrietados o "
        "inclinados, taludes deslavados, techos o balcones desprendiendose, "
        "postes inclinados, puentes dañados."
    ),
    Category.ESPACIO_PUBLICO: (
        "Deterioro de lo que la gente usa para estar: parques, aceras rotas, "
        "bancas o juegos destruidos, canchas, rampas de acceso bloqueadas."
    ),
    Category.NO_ES_REPORTE: (
        "La imagen no muestra un problema en la via publica: fotos personales, "
        "interiores privados, capturas de pantalla, imagenes sin relacion, o "
        "contenido que no corresponde."
    ),
}

SEVERIDADES: dict[Severity, str] = {
    Severity.ALTA: (
        "Hay riesgo de que alguien salga lastimado hoy: obstruye el paso de "
        "forma peligrosa, puede colapsar, o expone a algo dañino."
    ),
    Severity.MEDIA: ("Estorba o se va a agravar, pero no amenaza a nadie de inmediato."),
    Severity.BAJA: ("Deterioro que conviene atender sin urgencia; nadie corre peligro."),
}


def categorias_reales() -> list[Category]:
    """Las del alcance, sin la salida de 'esto no es un reporte'."""
    return [c for c in Category if c is not Category.NO_ES_REPORTE]


def prompt_de_categorias() -> str:
    lineas = [f"- {c.value}: {DEFINICIONES[c]}" for c in Category]
    return "\n".join(lineas)


def prompt_de_severidades() -> str:
    lineas = [f"- {s.value}: {SEVERIDADES[s]}" for s in Severity]
    return "\n".join(lineas)
