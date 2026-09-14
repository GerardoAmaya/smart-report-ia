"""El trabajador que copia las fotos a almacenamiento propio."""

import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app import storage, worker
from app.channels.telegram import TelegramChannel
from app.config import settings
from app.db import SessionLocal
from app.models import Report, ReportPhoto
from tests.imagenes import foto_sintetica, png_pequeno


@pytest.fixture
def reporte(session):
    r = Report(channel="telegram", external_user_id="7001", status="received")
    session.add(r)
    session.commit()
    return r


def nueva_foto(session, reporte, **campos) -> ReportPhoto:
    foto = ReportPhoto(
        report_id=reporte.id,
        channel="telegram",
        external_file_id=campos.pop("file_id", f"fid-{uuid.uuid4()}"),
        external_file_unique_id=str(uuid.uuid4())[:20],
        status="pending",
        **campos,
    )
    session.add(foto)
    session.commit()
    return foto


@pytest.fixture
def descarga_ok(monkeypatch):
    """Telegram devuelve una foto valida."""
    datos = foto_sintetica(semilla=21)

    async def falso(self, file_id):
        return datos

    monkeypatch.setattr(TelegramChannel, "fetch_media", falso)
    return datos


@pytest.fixture(autouse=True)
def limpiar_bucket():
    creadas: list[str] = []
    original = storage.put

    def registrando(key, data, content_type):
        creadas.append(key)
        return original(key, data, content_type)

    storage.put = registrando
    yield
    storage.put = original
    for k in creadas:
        with contextlib.suppress(Exception):
            storage.delete(k)


def test_guarda_original_y_miniatura(session, reporte, descarga_ok):
    foto = nueva_foto(session, reporte)

    assert worker.run_once(session) == 1
    session.refresh(foto)

    assert foto.status == "stored"
    assert foto.storage_key and foto.thumbnail_key
    assert foto.bytes == len(descarga_ok)
    assert foto.thumbnail_bytes < foto.bytes
    assert foto.mime_type == "image/jpeg"
    assert (foto.width, foto.height) == (721, 1280)
    assert foto.stored_at is not None
    assert foto.locked_at is None

    # Los bytes guardados son los que llegaron, sin reencodear: es evidencia.
    assert storage.get(foto.storage_key) == descarga_ok


def test_el_sha256_queda_anotado(session, reporte, descarga_ok):
    import hashlib

    foto = nueva_foto(session, reporte)
    worker.run_once(session)
    session.refresh(foto)
    assert foto.content_sha256 == hashlib.sha256(descarga_ok).hexdigest()


def test_la_misma_foto_dos_veces_se_detecta_pero_se_guarda_aparte(session, reporte, descarga_ok):
    """Duplicados detectables, bytes no compartidos.

    Compartir bytes obliga a contar referencias, y contarlas mal es como la
    retencion borra una foto que otro caso todavia usaba.
    """
    a = nueva_foto(session, reporte)
    b = nueva_foto(session, reporte)

    worker.run_once(session)
    session.refresh(a)
    session.refresh(b)

    assert a.content_sha256 == b.content_sha256
    assert a.storage_key != b.storage_key


def test_imagen_invalida_no_se_reintenta(session, reporte, monkeypatch):
    async def basura(self, file_id):
        return b"esto no es una imagen"

    monkeypatch.setattr(TelegramChannel, "fetch_media", basura)
    foto = nueva_foto(session, reporte)

    worker.run_once(session)
    session.refresh(foto)

    assert foto.status == "failed"
    assert foto.next_attempt_at is None
    assert foto.attempts == 1
    assert "imagen" in foto.failure_reason.lower()


def test_foto_mas_grande_que_el_tope_no_se_descarga(session, reporte, monkeypatch):
    pedidas = []

    async def no_deberia(self, file_id):
        pedidas.append(file_id)
        return b""

    monkeypatch.setattr(TelegramChannel, "fetch_media", no_deberia)
    monkeypatch.setattr(settings, "max_photo_bytes", 1000)
    foto = nueva_foto(session, reporte, declared_bytes=5_000_000)

    worker.run_once(session)
    session.refresh(foto)

    assert foto.status == "failed"
    # Lo importante: no se llego a pedir el archivo.
    assert pedidas == []


def test_fallo_de_red_se_reintenta_con_espera_creciente(session, reporte, monkeypatch):
    async def se_cae(self, file_id):
        raise ConnectionError("la red")

    monkeypatch.setattr(TelegramChannel, "fetch_media", se_cae)
    foto = nueva_foto(session, reporte)

    worker.run_once(session)
    session.refresh(foto)
    assert foto.status == "pending"
    assert foto.attempts == 1
    primera_espera = foto.next_attempt_at

    # La siguiente pasada no la toca todavia: le toca mas tarde.
    assert worker.run_once(session) == 0

    foto.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    worker.run_once(session)
    session.refresh(foto)

    assert foto.attempts == 2
    assert foto.next_attempt_at > primera_espera


def test_tras_los_intentos_maximos_queda_en_failed(session, reporte, monkeypatch):
    async def se_cae(self, file_id):
        raise ConnectionError("la red")

    monkeypatch.setattr(TelegramChannel, "fetch_media", se_cae)
    monkeypatch.setattr(settings, "worker_max_attempts", 3)
    foto = nueva_foto(session, reporte)

    for _ in range(3):
        foto.next_attempt_at = None
        session.commit()
        worker.run_once(session)
        session.refresh(foto)

    assert foto.status == "failed"
    assert foto.attempts == 3
    assert foto.next_attempt_at is None


def test_dos_trabajadores_no_toman_la_misma_foto(session, reporte, descarga_ok):
    """SKIP LOCKED: el segundo salta lo que el primero tiene, no espera."""
    for _ in range(4):
        nueva_foto(session, reporte)

    with SessionLocal() as otra:
        primeras = worker.claim(session, 2)
        segundas = worker.claim(otra, 2)

    ids_primeras = {f.id for f in primeras}
    ids_segundas = {f.id for f in segundas}

    assert len(primeras) == 2
    assert len(segundas) == 2
    assert ids_primeras.isdisjoint(ids_segundas)


def test_se_reclama_lo_que_dejo_un_trabajador_muerto(session, reporte, descarga_ok):
    """Sin esto, un contenedor que se cae deja fotos en processing para siempre."""
    foto = nueva_foto(session, reporte)
    foto.status = "processing"
    foto.locked_at = datetime.now(UTC) - timedelta(seconds=settings.worker_stale_lock_seconds + 60)
    session.commit()

    assert worker.reclaim_stale(session) == 1
    session.commit()
    session.refresh(foto)
    assert foto.status == "pending"


def test_no_se_reclama_lo_que_alguien_esta_trabajando(session, reporte):
    foto = nueva_foto(session, reporte)
    foto.status = "processing"
    foto.locked_at = datetime.now(UTC)
    session.commit()

    assert worker.reclaim_stale(session) == 0


def test_acepta_png(session, reporte, monkeypatch):
    datos = png_pequeno()

    async def devuelve_png(self, file_id):
        return datos

    monkeypatch.setattr(TelegramChannel, "fetch_media", devuelve_png)
    foto = nueva_foto(session, reporte)

    worker.run_once(session)
    session.refresh(foto)

    assert foto.status == "stored"
    assert foto.mime_type == "image/png"
    assert foto.storage_key.endswith(".png")
    # La miniatura siempre es JPEG, aunque el original no lo sea.
    assert foto.thumbnail_key.endswith(".jpg")


def test_la_cola_vacia_no_hace_nada(session):
    assert worker.run_once(session) == 0
