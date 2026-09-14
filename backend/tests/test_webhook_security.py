"""Las defensas del borde. Cada una con la forma del ataque que para."""

from pydantic import SecretStr
from sqlalchemy import text

from app.config import settings
from app.webhook import SECRET_HEADER
from tests.conftest import SECRETO_DE_PRUEBA
from tests.factories import update_con_foto

URL = "/webhooks/telegram"


def test_sin_secreto_rechaza(client):
    """Quien descubra la URL no entra: sin cabecera no hay reporte."""
    r = client.post(URL, json=update_con_foto())
    assert r.status_code == 403


def test_secreto_equivocado_rechaza(client):
    r = client.post(URL, json=update_con_foto(), headers={SECRET_HEADER: "otro"})
    assert r.status_code == 403


def test_sin_secreto_configurado_cierra_la_puerta(client, monkeypatch, session):
    """El fallo cierra, no abre.

    Si la variable de entorno falta, el webhook tiene que rechazar todo. Abrir
    seria el peor error posible: el bot aceptaria reportes de cualquiera y
    nadie se enteraria hasta ver datos falsos en el tablero.
    """
    monkeypatch.setattr(settings, "telegram_webhook_secret", SecretStr(""))
    r = client.post(URL, json=update_con_foto(), headers={SECRET_HEADER: ""})
    assert r.status_code == 403
    assert session.execute(text("SELECT count(*) FROM inbound_updates")).scalar() == 0


def test_secreto_correcto_pasa(client):
    r = client.post(URL, json=update_con_foto(), headers={SECRET_HEADER: SECRETO_DE_PRUEBA})
    assert r.status_code == 200


def test_cabeceras_de_seguridad(client):
    r = client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert r.headers["Cache-Control"] == "no-store"


def test_cuerpo_demasiado_grande_se_corta(client, monkeypatch):
    """Un POST enorme se rechaza sin leerlo entero."""
    monkeypatch.setattr(settings, "max_webhook_body_bytes", 1024)
    enorme = {"update_id": 1, "relleno": "x" * 5000}
    r = client.post(URL, json=enorme, headers={SECRET_HEADER: SECRETO_DE_PRUEBA})
    assert r.status_code == 413


def test_limite_por_ip(client, monkeypatch, session):
    monkeypatch.setattr(settings, "rate_limit_ip_per_minute", 3)
    codigos = [
        client.post(
            URL, json=update_con_foto(update_id=i), headers={SECRET_HEADER: SECRETO_DE_PRUEBA}
        ).status_code
        for i in range(1, 6)
    ]
    assert codigos[:3] == [200, 200, 200]
    assert codigos[3:] == [429, 429]


def test_limite_por_ip_devuelve_retry_after(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_ip_per_minute", 1)
    client.post(URL, json=update_con_foto(update_id=1), headers={SECRET_HEADER: SECRETO_DE_PRUEBA})
    r = client.post(
        URL, json=update_con_foto(update_id=2), headers={SECRET_HEADER: SECRETO_DE_PRUEBA}
    )
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1


def test_limite_por_usuario_no_crea_reporte(client, monkeypatch, session):
    """Pasado el limite, la persona recibe respuesta pero no se guarda reporte.

    Es lo que protege los diez gigas gratuitos: quien mande mil fotos ocupa
    filas en inbound_updates, que son bytes, y no fotos, que son megas.
    """
    monkeypatch.setattr(settings, "rate_limit_user_per_hour", 2)
    for i in range(1, 5):
        client.post(
            URL, json=update_con_foto(update_id=i), headers={SECRET_HEADER: SECRETO_DE_PRUEBA}
        )
    assert session.execute(text("SELECT count(*) FROM report_photos")).scalar() == 2


def test_forwarded_for_no_se_cree_sin_proxy(client, monkeypatch):
    """Sin proxy declarado, X-Forwarded-For se ignora.

    Si se leyera, bastaria mandar una IP distinta en cada peticion para que el
    limite por IP no limite nada.
    """
    monkeypatch.setattr(settings, "rate_limit_ip_per_minute", 2)
    monkeypatch.setattr(settings, "trusted_proxy_hops", 0)
    codigos = [
        client.post(
            URL,
            json=update_con_foto(update_id=i),
            headers={SECRET_HEADER: SECRETO_DE_PRUEBA, "X-Forwarded-For": f"10.0.0.{i}"},
        ).status_code
        for i in range(1, 5)
    ]
    assert 429 in codigos, "el limite se salto cambiando X-Forwarded-For"


def test_ip_no_se_guarda_en_claro(client, session):
    """La tabla de limites guarda un HMAC, no la direccion."""
    client.post(URL, json=update_con_foto(), headers={SECRET_HEADER: SECRETO_DE_PRUEBA})
    claves = session.execute(text("SELECT key FROM rate_limit_buckets")).scalars().all()
    assert claves
    for clave in claves:
        assert len(clave) == 64 and all(c in "0123456789abcdef" for c in clave)
        assert "." not in clave and ":" not in clave
