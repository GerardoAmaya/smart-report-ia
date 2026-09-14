"""Validacion y miniaturas.

La validacion se hace abriendo la imagen, no olfateando sus primeros bytes. Un
archivo con cabecera JPEG y basura detras pasa el olfato y revienta despues, al
generar la miniatura o al mostrarla en el tablero. Si Pillow la parsea, es una
imagen.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

# Formatos que aceptamos. Telegram manda JPEG para fotos; los otros entran por
# si algun dia otro canal manda algo distinto. Lista blanca y no negra: una
# lista negra deja pasar todo lo que nadie penso en prohibir.
# Sin HEIF: Pillow no lo abre sin pillow-heif, y aceptarlo en la lista seria
# prometer algo que reventaria al procesar. Telegram manda JPEG para fotos.
FORMATOS_ACEPTADOS = {"JPEG", "PNG", "WEBP"}

MIME_POR_FORMATO = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}

EXTENSION_POR_FORMATO = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}

# Tope de pixeles descomprimidos. Un archivo de pocos kilobytes puede declarar
# dimensiones enormes y reventar la memoria del trabajador al abrirlo; es un
# ataque conocido y el unico coste de pararlo es este numero.
Image.MAX_IMAGE_PIXELS = 50_000_000


class ImagenInvalida(Exception):
    """Los bytes no son una imagen que sepamos tratar."""


@dataclass(frozen=True)
class ImagenValidada:
    formato: str
    mime: str
    extension: str
    width: int
    height: int


def validate(data: bytes) -> ImagenValidada:
    """Comprueba que los bytes sean una imagen de un formato aceptado."""
    if not data:
        raise ImagenInvalida("archivo vacio")

    try:
        # verify() detecta corrupcion pero deja la imagen inutilizable, asi que
        # se abre dos veces: una para verificar y otra para leer las medidas.
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            formato = (img.format or "").upper()
            width, height = img.size
    except UnidentifiedImageError as exc:
        raise ImagenInvalida("no es una imagen reconocible") from exc
    except Image.DecompressionBombError as exc:
        raise ImagenInvalida("imagen con dimensiones desproporcionadas") from exc
    except Exception as exc:
        raise ImagenInvalida(f"imagen ilegible: {type(exc).__name__}") from exc

    if formato not in FORMATOS_ACEPTADOS:
        raise ImagenInvalida(f"formato no aceptado: {formato or 'desconocido'}")

    return ImagenValidada(
        formato=formato,
        mime=MIME_POR_FORMATO[formato],
        extension=EXTENSION_POR_FORMATO[formato],
        width=width,
        height=height,
    )


def thumbnail(data: bytes) -> bytes:
    """Miniatura para la cola del tablero.

    Siempre JPEG, aunque el original no lo sea: el tablero pide cientos de estas
    a la vez y no es el sitio para negociar formatos. El original se guarda
    aparte y sin tocar, porque es la evidencia.
    """
    with Image.open(io.BytesIO(data)) as img:
        # exif_transpose respeta la orientacion que grabo el telefono. Sin esto
        # las fotos verticales salen acostadas en la cola.
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        ancho = settings.thumbnail_width
        alto = max(1, round(img.height * (ancho / img.width)))
        img = img.resize((ancho, alto), Image.LANCZOS)

        salida = io.BytesIO()
        img.save(salida, format="JPEG", quality=settings.thumbnail_quality, optimize=True)
        return salida.getvalue()


# --- Huella perceptual ---

# dHash sobre 8x8: se compara cada pixel con su vecino de la derecha, lo que da
# 64 bits. Sobrevive al reescalado y al cambio de calidad JPEG, que es lo que
# hace Telegram. No sobrevive a un recorte fuerte ni a un giro, y eso esta bien:
# lo que detecta es "la misma foto otra vez", no "el mismo bache desde otro
# angulo". Confundir las dos cosas seria agrupar mal.
HASH_LADO = 8


def perceptual_hash(data: bytes) -> int:
    """64 bits que identifican la imagen, no su contenido semantico."""
    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img).convert("L")
        # Ancho+1 para poder comparar cada pixel con el de su derecha.
        img = img.resize((HASH_LADO + 1, HASH_LADO), Image.LANCZOS)
        pixeles = list(img.getdata())

    bits = 0
    for fila in range(HASH_LADO):
        base = fila * (HASH_LADO + 1)
        for col in range(HASH_LADO):
            izquierda = pixeles[base + col]
            derecha = pixeles[base + col + 1]
            bits = (bits << 1) | int(izquierda > derecha)

    # Postgres no tiene enteros de 64 bits sin signo: se desplaza al rango con
    # signo para que quepa en un BIGINT sin perder informacion.
    return bits - (1 << 63)


def hamming(a: int, b: int) -> int:
    """Cuantos bits difieren. Cero es la misma imagen."""
    return bin((a - (-1 << 63)) ^ (b - (-1 << 63))).count("1")
