"""Configuracion leida del entorno. Ningun secreto vive en el codigo."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://smart_report:smart_report@localhost:5432/smart_report"
    anthropic_api_key: str = ""

    # El chequeo del modelo se cachea: /health puede consultarse cada pocos
    # segundos y no queremos gastar cuota ni latencia en cada llamada.
    model_probe_ttl_seconds: int = 60
    model_probe_timeout_seconds: float = 5.0

    environment: str = "dev"
    cors_origins: str = "http://localhost:3100"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
