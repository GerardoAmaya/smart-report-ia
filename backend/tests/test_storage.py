"""Almacenamiento de objetos, contra MinIO de verdad.

No se simula el cliente de S3: lo que importa comprobar es justo lo que un
simulacro daria por bueno —firmas, tipos de contenido, enlaces prefirmados— y
esas son las diferencias que aparecen al cambiar MinIO por R2.
"""

import contextlib
import urllib.request
import uuid

import pytest

from app import storage
from app.config import settings
from tests.imagenes import foto_sintetica


@pytest.fixture
def clave():
    k = f"pruebas/{uuid.uuid4()}.jpg"
    yield k
    # La prueba puede haberla borrado ya; limpiar no tiene que fallar por eso.
    with contextlib.suppress(Exception):
        storage.delete(k)


def test_sube_y_recupera(clave):
    datos = foto_sintetica(semilla=11)
    guardado = storage.put(clave, datos, "image/jpeg")

    assert guardado.key == clave
    assert guardado.bytes == len(datos)
    assert storage.get(clave) == datos


def test_el_sha256_es_de_los_bytes_guardados(clave):
    import hashlib

    datos = foto_sintetica(semilla=12)
    guardado = storage.put(clave, datos, "image/jpeg")
    assert guardado.sha256 == hashlib.sha256(datos).hexdigest()


def test_existe_y_se_borra(clave):
    storage.put(clave, b"x" * 100, "application/octet-stream")
    assert storage.exists(clave) is True

    storage.delete(clave)
    assert storage.exists(clave) is False


def test_existe_devuelve_falso_y_no_revienta():
    assert storage.exists(f"no-existe/{uuid.uuid4()}") is False


def test_la_clave_no_lleva_nada_del_usuario():
    """Un nombre de archivo ajeno en una ruta es como se escribe fuera del sitio."""
    clave = storage.build_key(uuid.uuid4(), uuid.uuid4(), kind="original", ext="jpg")
    assert ".." not in clave
    assert not clave.startswith("/")
    # Fecha primero: deja el bucket navegable para borrar por antiguedad.
    assert clave.count("/") == 4


def test_enlace_prefirmado_sirve_para_bajar(clave):
    datos = foto_sintetica(semilla=13)
    storage.put(clave, datos, "image/jpeg")

    url = storage.presigned_url(clave, expires_seconds=60)
    with urllib.request.urlopen(url) as r:
        assert r.read() == datos
        assert r.headers["Content-Type"] == "image/jpeg"


def test_el_bucket_no_es_publico(clave):
    """Sin firma no se baja nada. Si esto falla, las fotos estan abiertas."""
    storage.put(clave, b"secreto", "text/plain")
    directa = f"{settings.s3_endpoint_url}/{settings.s3_bucket}/{clave}"

    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(directa)
    assert exc.value.code in (401, 403)


def test_health_ve_el_almacenamiento():
    estado = storage.check()
    assert estado["ok"] is True
    assert estado["bucket"] == settings.s3_bucket


# --- El enlace que recibe el navegador ---


def test_la_url_firmada_apunta_al_endpoint_publico(clave, monkeypatch):
    """El navegador corre en el host, no dentro de la red de compose.

    Firmar contra `http://minio:9000` daba una URL que el navegador no puede
    resolver: las fotos salian rotas en el tablero sin error en ningun log. Y no
    se arregla cambiando el texto despues de firmar, porque la firma v4 incluye
    el host.
    """
    monkeypatch.setattr(settings, "s3_public_endpoint_url", "http://localhost:9000")
    storage.public_client.cache_clear()

    storage.put(clave, b"x" * 50, "image/jpeg")
    url = storage.presigned_url(clave, expires_seconds=60)

    try:
        assert url.startswith("http://localhost:9000/")
        assert "minio:9000" not in url
    finally:
        storage.public_client.cache_clear()


def test_sin_endpoint_publico_se_usa_el_interno(monkeypatch):
    """Al desplegar contra R2 los dos valores coinciden y esto deja de importar."""
    monkeypatch.setattr(settings, "s3_public_endpoint_url", "")
    storage.public_client.cache_clear()
    try:
        url = storage.presigned_url("cualquier/clave.jpg", expires_seconds=60)
        assert settings.s3_endpoint_url.rstrip("/") in url
    finally:
        # El cliente esta cacheado: sin limpiarlo, la siguiente prueba firmaria
        # contra el endpoint de esta.
        storage.public_client.cache_clear()


def test_la_firma_va_en_la_url():
    """Sin firma el bucket privado devuelve 403: la firma es lo que la hace util."""
    url = storage.presigned_url("alguna/clave.jpg", expires_seconds=60)
    assert "X-Amz-Signature=" in url
    assert "X-Amz-Expires=60" in url
