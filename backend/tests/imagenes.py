"""Imagenes sinteticas calibradas contra una foto real de Telegram.

La referencia es el reporte que entro desde un telefono en la fase 1:
167 502 bytes, 721x1280, JPEG. Telegram comprime a 1280px de lado mayor.

Para el costo de **almacenamiento** esto vale: depende de bytes, no de
contenido. Para el costo de **clasificacion** no valdria, porque ahi importa lo
que el modelo ve; esas fotos tienen que ser reales y son de la fase 3.

La calibracion es por busqueda de calidad, no a ojo. El primer intento generaba
ruido en bloques y pesaba 1,84 veces la referencia: el ruido es el peor caso
para JPEG, y medir con eso habria inflado el costo un 84 por ciento. Una foto
de calle tiene zonas suaves, bordes y detalle moderado; lo que se genera aca
imita esa mezcla, y despues se ajusta la calidad hasta caer en el tamano real.
"""

from __future__ import annotations

import io
import math
import random

from PIL import Image, ImageDraw, ImageFilter

REFERENCIA_BYTES = 167_502
REFERENCIA_ANCHO = 721
REFERENCIA_ALTO = 1280

# Margen aceptable respecto a la referencia. Mas estrecho no aporta: la propia
# foto real variaria mas que esto de una toma a otra.
TOLERANCIA = 0.10


def _lienzo(ancho: int, alto: int, semilla: int) -> Image.Image:
    """Algo con la estructura de una foto: zonas suaves, bordes y grano."""
    rng = random.Random(semilla)
    img = Image.new("RGB", (ancho, alto), (90, 92, 95))
    dibujo = ImageDraw.Draw(img)

    # Degradado de fondo, como la luz cayendo sobre el pavimento.
    for y in range(alto):
        t = y / max(1, alto - 1)
        dibujo.line(
            [(0, y), (ancho, y)],
            fill=(int(70 + 90 * t), int(72 + 88 * t), int(78 + 80 * t)),
        )

    # Formas grandes: bordes reales, que es lo que JPEG tiene que codificar.
    for _ in range(14):
        x0, y0 = rng.randint(0, ancho), rng.randint(0, alto)
        x1 = x0 + rng.randint(40, ancho // 2)
        y1 = y0 + rng.randint(40, alto // 3)
        color = tuple(rng.randint(30, 210) for _ in range(3))
        if rng.random() < 0.5:
            dibujo.ellipse([x0, y0, x1, y1], fill=color)
        else:
            dibujo.rectangle([x0, y0, x1, y1], fill=color)

    # Grano fino sobre todo lo anterior, suavizado: textura, no ruido puro.
    grano = Image.new("RGB", (max(1, ancho // 4), max(1, alto // 4)))
    pix = grano.load()
    for y in range(grano.height):
        for x in range(grano.width):
            v = rng.randint(96, 160)
            pix[x, y] = (v, v, v)
    grano = grano.resize((ancho, alto), Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.2))

    return Image.blend(img, grano, 0.22)


def foto_sintetica(
    ancho: int = REFERENCIA_ANCHO,
    alto: int = REFERENCIA_ALTO,
    semilla: int = 0,
    objetivo_bytes: int | None = REFERENCIA_BYTES,
) -> bytes:
    """JPEG del tamano pedido, buscando la calidad que lo consigue.

    Con `objetivo_bytes` en None no calibra y usa calidad 85: sirve para las
    pruebas que solo necesitan una imagen valida y no un tamano concreto.
    """
    img = _lienzo(ancho, alto, semilla)

    def codificar(calidad: int) -> bytes:
        salida = io.BytesIO()
        img.save(salida, format="JPEG", quality=calidad, optimize=True)
        return salida.getvalue()

    if objetivo_bytes is None:
        return codificar(85)

    # El tamano crece con la calidad de forma monotona, asi que busqueda binaria.
    # Se escala el objetivo con el area: pedir los bytes de una foto de 721x1280
    # a una miniatura de 40x30 no tendria sentido.
    escala = (ancho * alto) / (REFERENCIA_ANCHO * REFERENCIA_ALTO)
    objetivo = max(1_000, int(objetivo_bytes * escala))

    bajo, alto_q = 5, 98
    mejor = codificar(85)
    while bajo <= alto_q:
        medio = (bajo + alto_q) // 2
        datos = codificar(medio)
        if abs(len(datos) - objetivo) < abs(len(mejor) - objetivo):
            mejor = datos
        if len(datos) < objetivo:
            bajo = medio + 1
        else:
            alto_q = medio - 1

    return mejor


def dentro_de_tolerancia(datos: bytes, objetivo: int = REFERENCIA_BYTES) -> bool:
    return abs(len(datos) - objetivo) / objetivo <= TOLERANCIA


def png_pequeno(ancho: int = 40, alto: int = 30) -> bytes:
    img = Image.new("RGB", (ancho, alto), (30, 110, 90))
    salida = io.BytesIO()
    img.save(salida, format="PNG")
    return salida.getvalue()


def desviacion(datos: bytes, objetivo: int = REFERENCIA_BYTES) -> float:
    """Cuanto se aparta del objetivo, en tanto por uno."""
    return (len(datos) - objetivo) / objetivo if objetivo else math.inf
