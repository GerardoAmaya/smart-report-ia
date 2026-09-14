"""Modelos del dominio.

Una tabla por concepto y una migracion por tabla. Los identificadores van en
ingles aunque los comentarios vayan en espanol; ver CLAUDE.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# Estados posibles, declarados una vez y usados por el CHECK de la base. Un
# estado invalido tiene que fallar en el INSERT, no descubrirse en el tablero.
REPORT_STATUSES = ("incomplete", "received", "rejected")
PHOTO_STATUSES = ("pending", "stored", "failed", "rejected")
PHOTO_KINDS = ("report", "evidence")


class Channel(Base):
    """Canal de entrada. El adaptador vive en el codigo; esto es la referencia.

    Es tabla y no una cadena suelta para que `reports.channel` sea una clave
    foranea: un canal mal escrito falla al insertar y no crea un canal fantasma.
    """

    __tablename__ = "channels"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InboundUpdate(Base):
    """El payload crudo tal cual llego, antes de interpretarlo.

    Se guarda entero y aparte porque si el parser tiene un bug, esto es lo
    unico que permite reprocesar. Interpretar y guardar en la misma tabla
    significa que un bug de parseo pierde el dato original.
    """

    __tablename__ = "inbound_updates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(
        String(32), ForeignKey("channels.code", ondelete="RESTRICT"), nullable=False
    )

    # Cadena y no entero: el id de update es de Telegram. Otro canal numerara
    # distinto y no queremos migrar el tipo cuando llegue.
    external_update_id: Mapped[str] = mapped_column(String(64), nullable=False)

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    process_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        # La idempotencia de todo el canal cuelga de aca: si el webhook tarda,
        # Telegram reenvia el mismo update, y sin este unico eso es un reporte
        # duplicado por cada reintento.
        UniqueConstraint("channel", "external_update_id", name="uq_inbound_updates_channel_extid"),
    )


class Report(Base):
    """El reporte interpretado: quien, donde y que foto."""

    __tablename__ = "reports"

    # UUID y no secuencial: el id termina en URLs del tablero, y un entero
    # correlativo deja contar reportes y pedir el de al lado.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    channel: Mapped[str] = mapped_column(
        String(32), ForeignKey("channels.code", ondelete="RESTRICT"), nullable=False
    )
    external_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    inbound_update_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("inbound_updates.id", ondelete="SET NULL")
    )

    # Nula mientras el reporte esta incompleto: la foto llega en un mensaje y
    # la ubicacion en otro. Un reporte sin ubicacion no se puede agrupar, y por
    # eso el estado lo dice en vez de fingir unas coordenadas en cero.
    location: Mapped[object | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False)
    )

    caption: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="incomplete")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("status IN " + str(REPORT_STATUSES), name="ck_reports_status"),
        # GIST: sin esto la fase 4 hace recorrido completo por cada agrupacion.
        Index("ix_reports_location_gist", "location", postgresql_using="gist"),
        # Sirve al limite por usuario: cuenta reportes de una persona en una
        # ventana, y es una busqueda por rango sobre estas dos columnas.
        Index("ix_reports_user_created", "external_user_id", "created_at"),
        Index("ix_reports_status_created", "status", "created_at"),
    )


class ReportPhoto(Base):
    """La foto, separada del reporte.

    Tabla aparte por dos motivos concretos: Telegram manda los albumes como
    updates separados de un mismo problema, y el cierre de la fase 6 adjunta
    foto de evidencia. Las dos cosas son varias fotos por caso.
    """

    __tablename__ = "report_photos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="report")

    channel: Mapped[str] = mapped_column(
        String(32), ForeignKey("channels.code", ondelete="RESTRICT"), nullable=False
    )

    # El comprobante de origen. No es almacenamiento: el file_path que se pide
    # con esto caduca en una hora, y las fotos viven en una cuenta de bot que
    # no controlamos. Sirve para reintentar la copia y para saber de donde vino.
    external_file_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_file_unique_id: Mapped[str | None] = mapped_column(String(128))

    # Lo que el update declara, antes de descargar nada. Se compara contra el
    # tope y se rechaza aca: bajar 20 MB para despues decidir que sobraba es
    # pagar el ancho de banda del abuso.
    declared_bytes: Mapped[int | None] = mapped_column(Integer)

    # Lo rellena el trabajador de la fase 2. Nulo no es un error: es "todavia
    # no subida", y por eso el estado lo dice aparte.
    storage_key: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    bytes: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    failure_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    stored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # La politica de retencion de la fase 2 borra de verdad. Esta columna marca
    # lo que ya no esta en el bucket, para no servir una clave muerta.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN " + str(PHOTO_STATUSES), name="ck_report_photos_status"),
        CheckConstraint("kind IN " + str(PHOTO_KINDS), name="ck_report_photos_kind"),
        Index("ix_report_photos_report", "report_id"),
        Index("ix_report_photos_unique_file", "channel", "external_file_unique_id"),
        # Parcial: la cola de la fase 2 solo mira las pendientes, y el indice
        # no tiene por que crecer con cada foto ya subida.
        Index(
            "ix_report_photos_pending",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )


class RateLimitBucket(Base):
    """Contador de ventana fija. La cola vive en Postgres y los limites tambien.

    Ventana fija y no deslizante a proposito: un solo UPSERT sobre la clave
    primaria, que es lo unico que cabe dentro del segundo que tiene el webhook.
    """

    __tablename__ = "rate_limit_buckets"

    scope: Mapped[str] = mapped_column(String(16), primary_key=True)

    # Nunca la IP en claro: es dato personal y esta tabla solo necesita saber
    # si dos peticiones vienen del mismo lado, no de donde. Se guarda un HMAC.
    key: Mapped[str] = mapped_column(String(128), primary_key=True)

    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        # Para el barrido que borra ventanas viejas.
        Index("ix_rate_limit_window", "window_start"),
    )
