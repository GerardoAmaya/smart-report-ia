"""Limite de intentos en la entrada del invitado (OWASP A07).

La contraseña del invitado es publica: va en el README. Lo que se protege no es
el secreto sino el servicio, asi que se cuentan todos los intentos, aciertos
incluidos. Antes no habia ningun limite.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from app import rate_limit
from app.config import settings
from app.models import RateLimitBucket

PASSWORD = "contraseña-de-prueba-larga"

# A mitad de una ventana de un minuto: una prueba que cruzara el borde veria el
# contador reiniciarse y fallaria de vez en cuando.
MOMENTO = datetime(2026, 11, 20, 12, 0, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    monkeypatch.setattr(settings, "demo_password", SecretStr(PASSWORD))
    monkeypatch.setattr(settings, "demo_email", "demo@smart-report.local")
    # Los de produccion, fijados: el contenedor de desarrollo los sube para que
    # las E2E puedan entrar muchas veces por corrida.
    monkeypatch.setattr(settings, "demo_login_per_minute", 10)
    monkeypatch.setattr(settings, "demo_login_global_per_minute", 300)
    # La IP sale de X-Forwarded-For contando un salto, como detras de Caddy:
    # asi cada prueba elige desde donde entra.
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    monkeypatch.setattr(rate_limit, "ahora", lambda: MOMENTO)


def _entrar(client, ip: str, password: str = PASSWORD):
    return client.post("/auth/demo", json={"password": password}, headers={"x-forwarded-for": ip})


def test_al_undecimo_intento_responde_429(client):
    for _ in range(9):
        assert _entrar(client, "203.0.113.7", "mala").status_code == 401
    # El decimo, con la buena, todavia pasa: cuenta, pero no se paso.
    assert _entrar(client, "203.0.113.7").status_code == 200

    r = _entrar(client, "203.0.113.7")

    assert r.status_code == 429
    assert r.json()["detail"] == "Demasiados intentos. Espera un minuto."
    assert 1 <= int(r.headers["retry-after"]) <= 60


def test_con_la_contraseña_buena_tambien_se_corta(client):
    """Los aciertos cuentan: lo que se defiende es el servicio."""
    for _ in range(10):
        assert _entrar(client, "203.0.113.8").status_code == 200
    assert _entrar(client, "203.0.113.8").status_code == 429


def test_otra_ip_no_se_ve_afectada(client):
    for _ in range(11):
        _entrar(client, "203.0.113.9", "mala")
    assert _entrar(client, "203.0.113.9").status_code == 429

    assert _entrar(client, "198.51.100.4").status_code == 200


def test_el_tope_global_frena_a_quien_rota_ips(client, monkeypatch):
    monkeypatch.setattr(settings, "demo_login_global_per_minute", 3)
    for i in range(3):
        assert _entrar(client, f"192.0.2.{i}", "mala").status_code == 401

    assert _entrar(client, "192.0.2.99").status_code == 429


def test_en_la_ventana_siguiente_se_vuelve_a_poder(client, monkeypatch):
    for _ in range(11):
        _entrar(client, "203.0.113.10", "mala")
    assert _entrar(client, "203.0.113.10").status_code == 429

    monkeypatch.setattr(rate_limit, "ahora", lambda: MOMENTO + timedelta(minutes=1))

    assert _entrar(client, "203.0.113.10").status_code == 200


def test_su_barrido_no_borra_los_contadores_de_otros_ambitos(client, session, monkeypatch):
    """Ya paso una vez: el barrido no filtraba por ambito y el tope diario del
    asistente se reiniciaba con cualquier otra peticion."""
    rate_limit.hit(
        session,
        scope="asistente",
        key="k",
        limit=10,
        window_seconds=86400,
        now=MOMENTO - timedelta(hours=3),
    )
    session.commit()
    monkeypatch.setattr(rate_limit, "_SWEEP_PROBABILITY", 1.0)

    _entrar(client, "203.0.113.11")

    session.expire_all()
    quedan = session.execute(
        select(func.count())
        .select_from(RateLimitBucket)
        .where(RateLimitBucket.scope == "asistente")
    ).scalar_one()
    assert quedan == 1
