import pytest
from fastapi.testclient import TestClient

from app import health
from app.main import app


@pytest.fixture(autouse=True)
def clean_model_cache():
    health.reset_model_cache()
    yield
    health.reset_model_cache()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
