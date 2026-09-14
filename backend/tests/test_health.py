"""Pruebas del chequeo de salud.

Lo que se comprueba no es que devuelva 200, sino que el cuerpo refleje el
estado real: un chequeo que siempre dice "ok" pasa cualquier prueba floja.
"""

import pytest
from sqlalchemy import create_engine

from app import health
from app.db import engine


@pytest.fixture(autouse=True)
def fake_model_ok(monkeypatch):
    # El sondeo real gastaria cuota en CI. El caso de modelo caido se prueba aparte.
    monkeypatch.setattr(health, "_probe_model", lambda: {"ok": True, "detail": None})


def test_health_reports_postgis_and_schema(client):
    body = client.get("/health").json()

    assert body["status"] == "ok", body["issues"]
    assert body["checks"]["postgis"]["ok"] is True
    assert body["checks"]["postgis"]["version"]
    assert body["schema_revision"] == health.head_revision()
    assert body["issues"] == []


def test_health_degrades_when_database_is_unreachable():
    # Puerto sin nadie escuchando: el fallo tiene que salir en el cuerpo.
    broken = create_engine("postgresql+psycopg://nobody@127.0.0.1:1/none")
    body = health.build_health(broken)

    assert body["status"] == "degraded"
    assert body["checks"]["postgis"]["ok"] is False
    assert any("postgis" in issue for issue in body["issues"])


def test_health_degrades_when_model_is_unreachable(monkeypatch):
    monkeypatch.setattr(health, "_probe_model", lambda: {"ok": False, "detail": "sin llave"})
    body = health.build_health(engine)

    assert body["status"] == "degraded"
    assert any("model" in issue for issue in body["issues"])


def test_health_endpoint_returns_200_while_degraded(client, monkeypatch):
    # Degradado no es caido: un 503 haria que el orquestador reinicie en bucle.
    monkeypatch.setattr(health, "_probe_model", lambda: {"ok": False, "detail": "sin llave"})
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_model_probe_is_cached(monkeypatch):
    calls = []

    def counted():
        calls.append(1)
        return {"ok": True, "detail": None}

    monkeypatch.setattr(health, "_probe_model", counted)
    assert health.check_model(now=100.0)["cached"] is False
    assert health.check_model(now=110.0)["cached"] is True
    assert len(calls) == 1
