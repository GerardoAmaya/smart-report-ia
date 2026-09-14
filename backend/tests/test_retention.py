"""La politica de retencion.

Lo que se comprueba no es que marque filas, sino que **los bytes desaparezcan
del bucket**. Una retencion que marca sin borrar es peor que ninguna: deja creer
que el dato se fue.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app import retention, storage
from app.config import settings
from app.models import Report, ReportPhoto
from tests.imagenes import foto_sintetica


def reporte_con_foto(session, estado: str, antiguedad: timedelta) -> tuple[Report, ReportPhoto]:
    r = Report(channel="telegram", external_user_id="8001", status=estado)
    session.add(r)
    session.flush()

    datos = foto_sintetica(semilla=31)
    clave = storage.build_key(r.id, uuid.uuid4(), kind="original", ext="jpg")
    clave_min = storage.build_key(r.id, uuid.uuid4(), kind="thumb", ext="jpg")
    storage.put(clave, datos, "image/jpeg")
    storage.put(clave_min, datos[:5000], "image/jpeg")

    p = ReportPhoto(
        report_id=r.id,
        channel="telegram",
        external_file_id=f"fid-{uuid.uuid4()}",
        storage_key=clave,
        thumbnail_key=clave_min,
        status="stored",
        bytes=len(datos),
    )
    session.add(p)
    session.commit()

    # Se envejece el reporte por SQL: updated_at tiene onupdate y asignarlo
    # desde el modelo lo pisaria al confirmar.
    session.execute(
        text("UPDATE reports SET updated_at = :t WHERE id = :i"),
        {"t": datetime.now(UTC) - antiguedad, "i": r.id},
    )
    session.commit()
    session.refresh(p)
    return r, p


def test_borra_los_bytes_de_un_reporte_incompleto_viejo(session):
    _, foto = reporte_con_foto(
        session, "incomplete", timedelta(days=settings.retention_incomplete_days + 1)
    )
    clave, clave_min = foto.storage_key, foto.thumbnail_key

    retention.run(session)
    session.refresh(foto)

    # Lo que importa: los bytes ya no estan.
    assert storage.exists(clave) is False
    assert storage.exists(clave_min) is False
    # La fila queda, para que el historial no se evapore.
    assert foto.deleted_at is not None
    assert foto.storage_key is None
    assert "retencion" in foto.failure_reason


def test_no_toca_lo_que_todavia_no_vencio(session):
    _, foto = reporte_con_foto(session, "incomplete", timedelta(days=1))
    clave = foto.storage_key

    retention.run(session)
    session.refresh(foto)

    assert storage.exists(clave) is True
    assert foto.deleted_at is None
    storage.delete(clave)
    storage.delete(foto.thumbnail_key)


def test_no_toca_un_reporte_recibido(session):
    """Un reporte vivo no caduca. Solo lo incompleto, lo rechazado y lo cerrado."""
    _, foto = reporte_con_foto(session, "received", timedelta(days=400))
    clave = foto.storage_key

    retention.run(session)
    session.refresh(foto)

    assert storage.exists(clave) is True
    assert foto.deleted_at is None
    storage.delete(clave)
    storage.delete(foto.thumbnail_key)


def test_rechazado_caduca_en_horas(session):
    _, foto = reporte_con_foto(
        session, "rejected", timedelta(hours=settings.retention_rejected_hours + 1)
    )
    clave = foto.storage_key

    retention.run(session)
    assert storage.exists(clave) is False


def test_dry_run_no_borra_nada(session):
    _, foto = reporte_con_foto(
        session, "incomplete", timedelta(days=settings.retention_incomplete_days + 1)
    )
    clave = foto.storage_key

    resultado = retention.run(session, dry_run=True)
    session.refresh(foto)

    assert resultado["incompleto"] == 1
    assert storage.exists(clave) is True
    assert foto.deleted_at is None
    storage.delete(clave)
    storage.delete(foto.thumbnail_key)


def test_correrla_dos_veces_no_falla(session):
    reporte_con_foto(session, "incomplete", timedelta(days=settings.retention_incomplete_days + 1))
    retention.run(session)
    segunda = retention.run(session)
    # Ya no queda nada que borrar: no se reintenta sobre claves muertas.
    assert segunda["incompleto"] == 0


def test_la_regla_de_cerrado_existe_aunque_el_estado_no(session):
    """Escrita ahora, inerte hasta la fase 6.

    La politica esta completa desde ya; empieza a borrar sola el dia que haya
    cierres, sin que nadie tenga que acordarse de volver aca.
    """
    nombres = {r.nombre for r in retention.reglas()}
    assert nombres == {"rechazado", "incompleto", "cerrado"}

    cerrado = next(r for r in retention.reglas() if r.nombre == "cerrado")
    assert cerrado.antiguedad == timedelta(days=settings.retention_closed_days)
    # Hoy no alcanza a nada porque ningun reporte puede estar cerrado todavia.
    assert retention.expired(session, cerrado) == []


# --- Huerfanos ---


def test_encuentra_objetos_que_ninguna_fila_apunta(session, monkeypatch):
    """Bytes fuera del alcance de la politica.

    Aparecen cuando una fila se borra sin pasar por la retencion: un borrado a
    mano, una restauracion parcial, o un script equivocado. Sin barrido, esos
    objetos no los encuentra ni los borra nadie — el peor sitio donde puede
    quedar una foto de la via publica.
    """
    monkeypatch.setattr(settings, "orphan_grace_hours", 0)
    clave = storage.build_key(uuid.uuid4(), uuid.uuid4(), kind="original", ext="jpg")
    storage.put(clave, foto_sintetica(semilla=41), "image/jpeg")

    try:
        assert clave in retention.orphans(session)
    finally:
        storage.delete(clave)


def test_no_toca_lo_que_una_fila_apunta(session, monkeypatch):
    monkeypatch.setattr(settings, "orphan_grace_hours", 0)
    _, foto = reporte_con_foto(session, "received", timedelta(days=1))

    huerfanos = retention.orphans(session)
    assert foto.storage_key not in huerfanos
    assert foto.thumbnail_key not in huerfanos

    storage.delete(foto.storage_key)
    storage.delete(foto.thumbnail_key)


def test_respeta_la_gracia(session, monkeypatch):
    """El trabajador sube los bytes y despues confirma la fila.

    Barrer durante esa ventana borraria una foto que estaba entrando.
    """
    monkeypatch.setattr(settings, "orphan_grace_hours", 24)
    clave = storage.build_key(uuid.uuid4(), uuid.uuid4(), kind="original", ext="jpg")
    storage.put(clave, foto_sintetica(semilla=42), "image/jpeg")

    try:
        # Recien subido: no se toca aunque nadie lo apunte.
        assert clave not in retention.orphans(session)
    finally:
        storage.delete(clave)


def test_purga_los_huerfanos(session, monkeypatch):
    monkeypatch.setattr(settings, "orphan_grace_hours", 0)
    clave = storage.build_key(uuid.uuid4(), uuid.uuid4(), kind="original", ext="jpg")
    storage.put(clave, foto_sintetica(semilla=43), "image/jpeg")

    assert retention.purge_orphans(session) >= 1
    assert storage.exists(clave) is False


def test_dry_run_no_borra_huerfanos(session, monkeypatch):
    monkeypatch.setattr(settings, "orphan_grace_hours", 0)
    clave = storage.build_key(uuid.uuid4(), uuid.uuid4(), kind="original", ext="jpg")
    storage.put(clave, foto_sintetica(semilla=44), "image/jpeg")

    try:
        assert retention.purge_orphans(session, dry_run=True) >= 1
        assert storage.exists(clave) is True
    finally:
        storage.delete(clave)
