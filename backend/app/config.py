"""Configuracion leida del entorno. Ningun secreto vive en el codigo."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://smart_report:smart_report@localhost:5432/smart_report"

    # SecretStr y no str: un repr de Settings en una traza o en un log de
    # arranque imprimiria la llave en claro. Asi imprime "**********".
    anthropic_api_key: SecretStr = SecretStr("")

    # El chequeo del modelo se cachea: /health puede consultarse cada pocos
    # segundos y no queremos gastar cuota ni latencia en cada llamada.
    model_probe_ttl_seconds: int = 60
    model_probe_timeout_seconds: float = 5.0

    # --- Canal de Telegram ---
    telegram_bot_token: SecretStr = SecretStr("")

    # Telegram devuelve este valor en X-Telegram-Bot-Api-Secret-Token en cada
    # update. Sin el, cualquiera que descubra la URL inyecta reportes falsos.
    telegram_webhook_secret: SecretStr = SecretStr("")

    # --- Topes de entrada ---
    # Un update de Telegram es JSON con metadatos: nunca llega a esto. El tope
    # existe para que un POST de un giga no se lea entero antes de rechazarlo.
    max_webhook_body_bytes: int = 1 * 1024 * 1024

    # Tope duro de la API de bots: no se puede descargar mas que esto. Se
    # comprueba contra file_size del update, antes de pedir nada.
    max_photo_bytes: int = 20 * 1024 * 1024

    # --- Limites de uso ---
    # Por IP protege el servicio; por usuario protege el almacenamiento y la
    # cuota del modelo. Son cosas distintas y por eso son dos limites.
    rate_limit_ip_per_minute: int = 60
    rate_limit_user_per_hour: int = 20

    # Cuantos proxies de confianza hay delante. Cero significa usar la IP
    # del socket e ignorar X-Forwarded-For, que es lo correcto sin proxy:
    # esa cabecera la escribe cualquiera y falsearla saltaria el limite.
    # Con cloudflared o un balanceador delante, poner 1.
    trusted_proxy_hops: int = 0

    # Cuanto sigue abierto un reporte esperando su ubicacion. La foto llega
    # en un mensaje y la ubicacion en otro; pasado este rato, una ubicacion
    # suelta ya no se pega a una foto de hace horas.
    open_report_window_minutes: int = 60

    # --- Almacenamiento de objetos (S3-compatible) ---
    # MinIO en local, R2 al desplegar: mismo protocolo, cambian las variables.
    s3_endpoint_url: str = "http://minio:9000"
    s3_bucket: str = "smart-report-photos"
    s3_access_key_id: SecretStr = SecretStr("")
    s3_secret_access_key: SecretStr = SecretStr("")
    s3_region: str = "us-east-1"

    environment: str = "dev"
    cors_origins: str = "http://localhost:3100"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"prod", "production"}


settings = Settings()
