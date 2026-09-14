import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text

from app import health
from app.config import settings
from app.db import SessionLocal
from app.main import app

SECRETO_DE_PRUEBA = "secreto-de-prueba-32-bytes-largo"


@pytest.fixture(autouse=True)
def clean_model_cache():
    health.reset_model_cache()
    yield
    health.reset_model_cache()


@pytest.fixture(autouse=True)
def base_limpia():
    """Cada prueba arranca con las tablas del canal vacias.

    TRUNCATE y no DELETE: reinicia tambien las secuencias, asi que los ids no
    arrastran de una prueba a otra y un fallo se lee sin adivinar.
    `channels` se deja: la siembra el seeder y las claves foraneas la piden.
    """
    with SessionLocal() as session:
        session.execute(
            text(
                "TRUNCATE report_photos, reports, inbound_updates, "
                "rate_limit_buckets RESTART IDENTITY CASCADE"
            )
        )
        session.execute(
            text(
                "INSERT INTO channels (code, display_name) VALUES ('telegram', 'Telegram') "
                "ON CONFLICT (code) DO NOTHING"
            )
        )
        session.commit()
    yield


@pytest.fixture(autouse=True)
def ajustes_de_prueba(monkeypatch):
    """Secreto conocido y limites altos, salvo que la prueba diga otra cosa."""
    monkeypatch.setattr(settings, "telegram_webhook_secret", SecretStr(SECRETO_DE_PRUEBA))
    monkeypatch.setattr(settings, "rate_limit_ip_per_minute", 1000)
    monkeypatch.setattr(settings, "rate_limit_user_per_hour", 1000)
    monkeypatch.setattr(settings, "trusted_proxy_hops", 0)
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def session():
    with SessionLocal() as s:
        yield s
