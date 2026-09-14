"""Configuracion de las pruebas.

**Las pruebas corren contra su propia base, nunca contra la de desarrollo.**

Esto no es pulcritud: las pruebas vacian tablas entre casos, y apuntando a la
base de desarrollo eso borra reportes reales. Paso de verdad —un reporte
mandado desde un telefono desaparecio en un `make test`— y la unica defensa que
no depende de acordarse es que la conexion sea otra.

El cambio de URL ocurre antes de importar `app.db`, porque el motor se
construye al importar: si se cambia despues, el motor ya apunta a la base
equivocada.
"""

from __future__ import annotations

import sqlalchemy
from sqlalchemy import text

from app.config import settings

URL_DESARROLLO = settings.database_url


def _url_de_pruebas(url: str) -> str:
    base, _, nombre = url.rpartition("/")
    nombre = nombre.split("?")[0]
    return f"{base}/{nombre}_test"


def _crear_base_de_pruebas() -> None:
    """Crea la base de pruebas si no existe, conectandose a la de desarrollo."""
    motor = sqlalchemy.create_engine(URL_DESARROLLO, isolation_level="AUTOCOMMIT")
    nombre = _url_de_pruebas(URL_DESARROLLO).rpartition("/")[2]
    with motor.connect() as conn:
        existe = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": nombre}
        ).scalar()
        if not existe:
            # Identificador interpolado porque CREATE DATABASE no admite
            # parametros ligados; el nombre sale de nuestra propia configuracion
            # y no de una peticion, y se valida antes de usarlo.
            if not nombre.replace("_", "").isalnum():
                raise RuntimeError(f"nombre de base sospechoso: {nombre}")
            conn.execute(text(f'CREATE DATABASE "{nombre}"'))
    motor.dispose()


def _crear_bucket_de_pruebas() -> None:
    """Bucket propio para las pruebas.

    La base ya estaba aislada pero el bucket no, y eso mordio: una prueba del
    barrido de huerfanos borro objetos reales, porque un huerfano se define como
    "ningun registro lo apunta" y los registros de desarrollo no estaban en la
    base de pruebas. Aislar la base sin aislar el almacenamiento deja el mismo
    agujero con otra forma.
    """
    from app import storage

    settings.s3_bucket = f"{BUCKET_DESARROLLO}-test"
    storage.client.cache_clear()
    cliente = storage.client()
    try:
        cliente.head_bucket(Bucket=settings.s3_bucket)
    except Exception:
        cliente.create_bucket(Bucket=settings.s3_bucket)


BUCKET_DESARROLLO = settings.s3_bucket

_crear_base_de_pruebas()
settings.database_url = _url_de_pruebas(URL_DESARROLLO)
_crear_bucket_de_pruebas()

# A partir de aca todo se construye contra la base de pruebas.
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import SecretStr  # noqa: E402

from app import health  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

SECRETO_DE_PRUEBA = "secreto-de-prueba-32-bytes-largo"


def _migrar() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(health.ALEMBIC_INI))
    cfg.set_main_option("script_location", str(health.ALEMBIC_INI.parent / "alembic"))
    command.upgrade(cfg, "head")


def pytest_configure(config):
    _migrar()
    with SessionLocal() as session:
        session.execute(
            text(
                "INSERT INTO channels (code, display_name) VALUES ('telegram', 'Telegram') "
                "ON CONFLICT (code) DO NOTHING"
            )
        )
        session.commit()


@pytest.fixture(autouse=True)
def guardia_de_base():
    """Se niega a correr si la conexion apunta a la base de desarrollo.

    La ultima linea de defensa. Si alguien cambia la configuracion y las
    pruebas terminan apuntando a la base real, esto para antes del primer
    TRUNCATE en vez de despues.
    """
    actual = str(engine.url)
    if not actual.endswith("_test"):
        raise RuntimeError(f"las pruebas no corren contra {actual}: falta el sufijo _test")
    # El bucket tambien: aislar la base sin aislar el almacenamiento deja el
    # mismo agujero con otra forma.
    if not settings.s3_bucket.endswith("-test"):
        raise RuntimeError(
            f"las pruebas no escriben en {settings.s3_bucket}: falta el sufijo -test"
        )
    yield


@pytest.fixture(autouse=True)
def clean_model_cache():
    health.reset_model_cache()
    yield
    health.reset_model_cache()


# Lo unico que sobrevive entre pruebas. `channels` porque lo siembra el seeder y
# las claves foraneas lo piden; `alembic_version` porque es del esquema.
TABLAS_PERMANENTES = {"channels", "alembic_version"}


def _tablas_a_vaciar() -> list[str]:
    """Todas las tablas del modelo menos las permanentes.

    Derivada del esquema y no escrita a mano: una lista a mano se queda vieja
    en cuanto se agrega una tabla, y el sintoma es horrible —datos de una prueba
    filtrandose a la siguiente, fallos que solo aparecen en la suite completa y
    desaparecen al correr la prueba sola—. Paso con `cases` al llegar la fase 4.
    """
    from app.models import Base

    return [t.name for t in Base.metadata.sorted_tables if t.name not in TABLAS_PERMANENTES]


@pytest.fixture(autouse=True)
def base_limpia():
    """Cada prueba arranca con la base vacia.

    TRUNCATE y no DELETE: reinicia tambien las secuencias, asi que los ids no
    arrastran de una prueba a otra.
    """
    tablas = ", ".join(_tablas_a_vaciar())
    with SessionLocal() as session:
        session.execute(text(f"TRUNCATE {tablas} RESTART IDENTITY CASCADE"))
        session.commit()
    yield


@pytest.fixture(autouse=True)
def ventana_fija(monkeypatch):
    """Congela el reloj del limitador durante cada prueba.

    Sin esto, una prueba que cruza el borde de la ventana ve el contador
    reiniciarse a mitad y falla sin motivo aparente. Paso una vez.
    """
    from datetime import UTC, datetime

    from app import rate_limit

    fijo = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(rate_limit, "ahora", lambda: fijo)
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
