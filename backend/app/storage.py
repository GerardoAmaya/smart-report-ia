"""Almacenamiento de objetos, hablando S3.

MinIO en local y R2 al desplegar: el codigo no distingue, cambian las variables
de entorno. Lo que no es reversible es el protocolo, y por eso se eligio antes
de escribir el esquema.

Sincrono a proposito. Esto corre en el trabajador, fuera del camino del webhook,
donde un segundo de mas no le cuesta nada a nadie; `aioboto3` clavaria una
version vieja de aiobotocore a cambio de asincronia en el unico sitio donde no
hace falta.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import settings


@dataclass(frozen=True)
class StoredObject:
    key: str
    bytes: int
    sha256: str


def _construir(endpoint: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        region_name=settings.s3_region,
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=10,
            read_timeout=60,
        ),
    )


@lru_cache(maxsize=1)
def public_client():
    """Cliente que firma contra el endpoint **publico**.

    Solo para firmar: firmar no toca la red, asi que este cliente nunca conecta.
    Existe porque el navegador corre fuera de la red de compose y no resuelve
    "minio"; y como la firma v4 incluye el host, cambiar la URL despues de
    firmarla la invalida.
    """
    return _construir(settings.s3_public_endpoint_url or settings.s3_endpoint_url)


@lru_cache(maxsize=1)
def client():
    """Cliente S3 compartido.

    Cacheado porque construirlo firma y resuelve configuracion, y el trabajador
    lo usa en bucle. `s3v4` explicito: R2 solo acepta esa firma.
    """
    return _construir(settings.s3_endpoint_url)


def build_key(report_id: uuid.UUID, photo_id: uuid.UUID, *, kind: str, ext: str) -> str:
    """Clave del objeto en el bucket.

    Nunca lleva nada que venga del usuario: ni el nombre de archivo que mando
    ni el que diga Telegram. Un nombre de archivo ajeno en una ruta es como se
    escribe fuera del directorio previsto. Van identificadores propios y la
    fecha, que ademas deja el bucket navegable cuando haya que borrar por
    antiguedad.
    """
    hoy = datetime.now(UTC)
    return f"{hoy:%Y/%m/%d}/{report_id}/{photo_id}-{kind}.{ext}"


def put(key: str, data: bytes, content_type: str) -> StoredObject:
    """Sube un objeto y devuelve lo que quedo guardado.

    El sha256 se calcula sobre los bytes que se suben, no sobre los que se
    creyo tener: es lo que permite detectar la misma foto mandada dos veces, y
    comprobar mas tarde que lo guardado es lo que llego.
    """
    digest = hashlib.sha256(data).hexdigest()
    client().put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
        # Metadatos utiles al depurar sin tener que cruzar con la base.
        Metadata={"sha256": digest},
    )
    return StoredObject(key=key, bytes=len(data), sha256=digest)


def get(key: str) -> bytes:
    return client().get_object(Bucket=settings.s3_bucket, Key=key)["Body"].read()


def delete(key: str) -> None:
    """Borra de verdad. La politica de retencion depende de que esto borre."""
    client().delete_object(Bucket=settings.s3_bucket, Key=key)


def exists(key: str) -> bool:
    try:
        client().head_object(Bucket=settings.s3_bucket, Key=key)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def presigned_url(key: str, expires_seconds: int | None = None) -> str:
    """Enlace temporal para que el navegador baje el objeto directo.

    El tablero no proxea las fotos: ni ancho de banda ni latencia de la API en
    el camino, y el bucket queda privado. La vida corta es lo que limita el
    dano si un enlace se comparte fuera.
    """
    # public_client y no client: la firma lleva el host dentro.
    return public_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires_seconds or settings.s3_presigned_ttl_seconds,
    )


def check() -> dict:
    """Estado del almacenamiento para /health."""
    try:
        client().head_bucket(Bucket=settings.s3_bucket)
    except Exception as exc:
        from app.health import safe_detail

        return {"ok": False, "detail": safe_detail(exc), "bucket": settings.s3_bucket}
    return {"ok": True, "detail": None, "bucket": settings.s3_bucket}
