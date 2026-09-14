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
    # Desde donde lo alcanza **el navegador**, que corre en el host y no
    # dentro de la red de compose: "minio" no existe para el. No se puede
    # arreglar cambiando el texto de la URL despues de firmarla, porque con
    # firma v4 el host va dentro de la firma. Al desplegar contra R2 los dos
    # valores coinciden y esto deja de importar.
    s3_public_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "smart-report-photos"
    s3_access_key_id: SecretStr = SecretStr("")
    s3_secret_access_key: SecretStr = SecretStr("")
    s3_region: str = "us-east-1"

    # Vida del enlace prefirmado. Cubre una sesion de trabajo sin dejar un
    # enlace vivo durante dias si alguien lo comparte fuera del tablero.
    s3_presigned_ttl_seconds: int = 900

    # --- Trabajador de fotos ---
    worker_poll_seconds: float = 2.0
    worker_batch_size: int = 5
    # Tras estos intentos se deja de reintentar y queda en failed con el
    # motivo. Reintentar sin fin esconde un problema permanente detras de
    # una cola que nunca baja.
    worker_max_attempts: int = 5
    # Una fila tomada hace mas de esto es de un trabajador que murio.
    worker_stale_lock_seconds: int = 300

    # Ancho de la miniatura. El tablero muestra una cola y un mapa; el
    # original queda para el detalle.
    thumbnail_width: int = 320
    thumbnail_quality: int = 80

    # --- Clasificacion ---
    # El mas barato de los tres, elegido con el saldo a la vista. La foto es
    # dos tercios del costo, asi que la miniatura ahorra mas que cambiar de
    # modelo. Si la evaluacion muestra que pierde acierto en casos dificiles,
    # subir de modelo es cambiar esta variable.
    classify_model: str = "claude-haiku-4-5"
    classify_timeout_seconds: float = 60.0
    # Que se le manda: la foto original o la miniatura. Cambia el costo y
    # puede cambiar el acierto; se mide antes de fijarlo.
    classify_image_variant: str = "thumbnail"
    classify_max_attempts: int = 3

    # Avisos de vuelta. Mas intentos que en lo demas: que a alguien no le
    # llegue el aviso de que su reporte se resolvio es justo lo que hace que
    # no vuelva a reportar.
    notify_max_attempts: int = 6

    # --- Agrupacion ---
    # **Estos numeros son provisionales.** PLAN.md pide calibrarlos contra
    # doscientos reportes agrupados a mano, y eso todavia no existe. Van con
    # un valor razonado, no medido, y el razonamiento esta en el README.
    #
    # La asimetria manda: juntar dos problemas distintos esconde uno, que es
    # grave; separar dos que eran el mismo duplica trabajo, que es molesto.
    # Por eso el margen para agrupar es estrecho y hay una banda de duda
    # entre agrupar y dejar solo.
    group_max_distance_m: float = 30.0
    doubtful_max_distance_m: float = 80.0
    # Bits de diferencia por debajo de los cuales dos fotos son la misma
    # imagen. Medido: 0 reescalando a un tercio, 2 recomprimiendo, 26 entre
    # fotos distintas.
    same_image_max_bits: int = 6

    # --- Retencion ---
    # Politica escrita, no un numero suelto: ver README. Son fotos de la via
    # publica con caras y placas de gente que no pidio salir.
    retention_closed_days: int = 90
    retention_incomplete_days: int = 7
    retention_rejected_hours: int = 24
    # Gracia antes de considerar huerfano un objeto del bucket. El trabajador
    # sube los bytes y despues confirma la fila; sin margen, barrer durante
    # esa ventana borraria una foto que estaba entrando.
    orphan_grace_hours: int = 24

    # --- Entrada al tablero ---
    # Firma las cookies de sesion. Cambiarla cierra la sesion de todos, que
    # es justo lo que se quiere si se sospecha que se filtro.
    session_secret: SecretStr = SecretStr("")
    session_max_age_seconds: int = 60 * 60 * 12

    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    # A donde vuelve Google. Tiene que coincidir exactamente con lo
    # registrado en la consola de Google o el intercambio falla.
    oauth_redirect_url: str = "http://localhost:8000/auth/google/callback"
    # A donde mandar al navegador cuando termina el intercambio.
    frontend_url: str = "http://localhost:3100"

    # El usuario de prueba. La contraseña va aqui y nunca en el codigo:
    # una credencial escrita en el repositorio queda en el historial de git
    # para siempre, y cuando haga falta cambiarla ya no se puede.
    demo_email: str = "demo@smart-report.local"
    demo_password: SecretStr = SecretStr("")

    # Correo del primer administrador. Lo siembra el seeder.
    admin_email: str = ""

    environment: str = "dev"
    cors_origins: str = "http://localhost:3100"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"prod", "production"}


settings = Settings()
