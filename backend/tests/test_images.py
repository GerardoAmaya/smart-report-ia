"""Validacion y miniaturas."""

import io

import pytest
from PIL import Image

from app import images
from app.config import settings
from tests.imagenes import (
    REFERENCIA_BYTES,
    dentro_de_tolerancia,
    desviacion,
    foto_sintetica,
    png_pequeno,
)


def test_acepta_jpeg():
    v = images.validate(foto_sintetica())
    assert v.formato == "JPEG"
    assert v.mime == "image/jpeg"
    assert v.extension == "jpg"
    assert (v.width, v.height) == (721, 1280)


def test_acepta_png():
    v = images.validate(png_pequeno())
    assert v.formato == "PNG"
    assert v.extension == "png"


def test_rechaza_basura():
    with pytest.raises(images.ImagenInvalida):
        images.validate(b"esto no es una imagen, ni de lejos")


def test_rechaza_vacio():
    with pytest.raises(images.ImagenInvalida):
        images.validate(b"")


def test_rechaza_cabecera_jpeg_con_basura_detras():
    """Olfatear los primeros bytes no alcanza.

    Este archivo pasa cualquier comprobacion de numero magico y revienta al
    procesarlo. Por eso se valida abriendo la imagen y no mirando la cabecera.
    """
    falso = b"\xff\xd8\xff\xe0" + b"basura" * 200
    with pytest.raises(images.ImagenInvalida):
        images.validate(falso)


def test_rechaza_formato_no_aceptado():
    """Lista blanca: un GIF es una imagen valida y aun asi no entra."""
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, format="GIF")
    with pytest.raises(images.ImagenInvalida, match="formato no aceptado"):
        images.validate(gif.getvalue())


def test_miniatura_respeta_el_ancho_configurado():
    mini = images.thumbnail(foto_sintetica())
    with Image.open(io.BytesIO(mini)) as img:
        assert img.width == settings.thumbnail_width
        assert img.format == "JPEG"


def test_miniatura_conserva_la_proporcion():
    mini = images.thumbnail(foto_sintetica(ancho=800, alto=400))
    with Image.open(io.BytesIO(mini)) as img:
        assert abs(img.width / img.height - 2.0) < 0.05


def test_miniatura_pesa_mucho_menos_que_el_original():
    original = foto_sintetica()
    mini = images.thumbnail(original)
    assert len(mini) < len(original) / 5


def test_miniatura_endereza_segun_exif():
    """Sin exif_transpose las fotos verticales salen acostadas en la cola."""
    vertical = Image.new("RGB", (400, 800), (120, 120, 120))
    con_exif = io.BytesIO()
    exif = Image.Exif()
    exif[274] = 6  # Orientation: rotar 90 grados
    vertical.save(con_exif, format="JPEG", exif=exif)

    mini = images.thumbnail(con_exif.getvalue())
    with Image.open(io.BytesIO(mini)) as img:
        # Tras enderezarla queda apaisada, no vertical.
        assert img.width > img.height


def test_las_sinteticas_estan_calibradas_contra_la_foto_real():
    """El costo medido con fotos mal calibradas no es el costo.

    El primer generador pesaba 1,84 veces la referencia porque producia ruido,
    que es el peor caso para JPEG. Con eso, el costo por foto de la fase 2
    habria salido un 84 por ciento inflado.
    """
    for semilla in range(5):
        datos = foto_sintetica(semilla=semilla)
        assert dentro_de_tolerancia(datos), (
            f"semilla {semilla} se desvia {desviacion(datos):+.1%} "
            f"de los {REFERENCIA_BYTES} bytes reales"
        )


def test_las_sinteticas_no_son_todas_iguales():
    """Semillas distintas dan fotos distintas, no la misma con otro nombre."""
    muestras = {foto_sintetica(semilla=s) for s in range(5)}
    assert len(muestras) == 5
