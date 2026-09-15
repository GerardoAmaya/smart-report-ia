"""El respaldo de la base.

Esto solo corre en el servidor, y ahi no se puede probar por primera vez: se
descubriria que esta roto el dia que haga falta restaurar. De las tres partes,
`pg_dump` es la unica que no se cubre aqui —necesita el binario, que solo esta
en la imagen de produccion—; se comprueba al construirla.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app import backup, storage
from app.config import settings


@pytest.fixture
def bucket_limpio():
    """Sin respaldos de una prueba anterior, antes y despues.

    Se borra solo el prefijo de respaldos y no el bucket entero: ahi viven
    tambien las fotos, y una prueba que vacia el bucket de al lado es
    exactamente como se perdieron objetos reales una vez.
    """
    _borrar_respaldos()
    yield
    _borrar_respaldos()


def _borrar_respaldos() -> None:
    cliente = storage.client()
    respuesta = cliente.list_objects_v2(Bucket=settings.s3_bucket, Prefix=backup.PREFIJO)
    for objeto in respuesta.get("Contents", []):
        cliente.delete_object(Bucket=settings.s3_bucket, Key=objeto["Key"])


def _claves() -> set[str]:
    cliente = storage.client()
    respuesta = cliente.list_objects_v2(Bucket=settings.s3_bucket, Prefix=backup.PREFIJO)
    return {o["Key"] for o in respuesta.get("Contents", [])}


def test_el_respaldo_se_sube_con_la_fecha_del_dia(monkeypatch, bucket_limpio):
    """Uno por dia y no por minuto: reiniciar no debe llenar el bucket."""
    monkeypatch.setattr(backup, "volcar", lambda: b"volcado de mentira")

    primera = backup.respaldar()
    segunda = backup.respaldar()

    assert primera == segunda
    assert primera == f"{backup.PREFIJO}{datetime.now(UTC):%Y-%m-%d}.dump"
    assert _claves() == {primera}


def test_no_borra_los_respaldos_de_dentro_de_la_ventana(monkeypatch, bucket_limpio):
    monkeypatch.setattr(backup, "volcar", lambda: b"x")
    clave = backup.respaldar()

    # Un corte de hace un año: nada es tan viejo.
    assert backup.limpiar_viejos(datetime.now(UTC) - timedelta(days=365)) == 0
    assert clave in _claves()


def test_borra_los_que_pasaron_de_la_ventana(monkeypatch, bucket_limpio):
    """Sin esto el bucket crece sin fin, que es como se agota el nivel gratuito."""
    monkeypatch.setattr(backup, "volcar", lambda: b"x")
    backup.respaldar()

    # Un corte en el futuro: todo es viejo.
    assert backup.limpiar_viejos(datetime.now(UTC) + timedelta(days=1)) == 1
    assert _claves() == set()


def test_solo_mira_sus_propios_objetos(monkeypatch, bucket_limpio):
    """El bucket es el mismo donde viven las fotos de los reportes.

    Un barrido que se lleve por delante una foto porque es mas vieja que la
    ventana de respaldos seria destruir la evidencia de un caso.
    """
    monkeypatch.setattr(backup, "volcar", lambda: b"x")
    backup.respaldar()
    storage.put("reports/foto-vieja.jpg", b"no me toques", "image/jpeg")

    backup.limpiar_viejos(datetime.now(UTC) + timedelta(days=1))

    assert storage.exists("reports/foto-vieja.jpg")
    storage.delete("reports/foto-vieja.jpg")
