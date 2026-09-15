"""Modelos del dominio.

Una tabla por concepto y una migracion por tabla. Los identificadores van en
ingles aunque los comentarios vayan en espanol; ver CLAUDE.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from geoalchemy2 import Geography
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
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
# "doubtful" es el estado que pide PLAN.md: lo que queda en el limite no se
# agrupa ni se descarta, se marca con el motivo esperando decision humana.
GROUPING_STATUSES = ("pending", "grouped", "alone", "doubtful")
CASE_STATUSES = ("open", "assigned", "in_progress", "closed", "discarded")
# "alone" incluido: un reporte sin nada cerca tambien deja constancia, y esa
# constancia es lo que deja ver que no se agrupo por decision y no por olvido.
GROUPING_DECISIONS = ("grouped", "rejected", "doubtful", "alone")
NOTIFICATION_STATUSES = ("pending", "processing", "sent", "failed")
NOTIFICATION_KINDS = ("assigned", "in_progress", "closed")
PHOTO_STATUSES = ("pending", "processing", "stored", "failed", "rejected")
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

    # Como se llama ese punto, resuelto aparte y cacheado. Nulo con
    # `geocoded_at` puesto significa "se intento y el sitio no tiene nombre",
    # que no es lo mismo que "falta intentarlo": sin esa distincion el
    # trabajador reintentaria para siempre los descampados.
    address_text: Mapped[str | None] = mapped_column(String(200))
    geocoded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    geocode_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # SET NULL en la migracion, no CASCADE: deshacer una agrupacion devuelve los
    # reportes, no los borra.
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="SET NULL")
    )
    grouping_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )

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
        Index("ix_reports_case", "case_id"),
        Index(
            "ix_reports_grouping_pending",
            "created_at",
            postgresql_where=text("grouping_status = 'pending'"),
        ),
        CheckConstraint(
            "grouping_status IN " + str(GROUPING_STATUSES), name="ck_reports_grouping_status"
        ),
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

    # Huella perceptual: 64 bits que sobreviven al reescalado. Detecta la
    # misma foto reenviada; NO dos fotos distintas del mismo bache.
    phash: Mapped[int | None] = mapped_column(BigInteger)

    # Lo rellena el trabajador de la fase 2. Nulo no es un error: es "todavia
    # no subida", y por eso el estado lo dice aparte.
    storage_key: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    bytes: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(64))

    # La miniatura va aparte: el original se guarda tal cual llego, sin
    # reencodear, porque es evidencia.
    thumbnail_key: Mapped[str | None] = mapped_column(Text)
    thumbnail_bytes: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    failure_reason: Mapped[str | None] = mapped_column(Text)

    # Reintentos con espera creciente, y marca de quien la tiene tomada. Sin
    # locked_at, un trabajador que muere a mitad de una descarga deja la fila
    # en processing para siempre.
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
            "ix_report_photos_phash",
            "phash",
            postgresql_where=text("phash IS NOT NULL"),
        ),
        Index(
            "ix_report_photos_pending",
            "next_attempt_at",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "ix_report_photos_processing",
            "locked_at",
            postgresql_where=text("status = 'processing'"),
        ),
    )


CLASSIFICATION_STATUSES = (
    "pending",
    "processing",
    "proposed",
    "confirmed",
    "corrected",
    "failed",
)


class Classification(Base):
    """Un intento de clasificar un reporte.

    Tabla aparte y no columnas en `reports`: va a haber mas de uno por reporte
    —reintentos, modelos distintos, reclasificar cuando mejore el prompt— y
    aplastarlo contra el reporte perderia con que se clasifico cada cosa, que es
    justo lo que esta fase tiene que medir.
    """

    __tablename__ = "classifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")

    # Lo que propone el modelo. Nunca es la categoria final.
    proposed_category: Mapped[str | None] = mapped_column(String(32))
    proposed_severity: Mapped[str | None] = mapped_column(String(16))
    proposed_reason: Mapped[str | None] = mapped_column(Text)

    # Lo que quedo tras confirmar. La diferencia entre las dos columnas es la
    # medida de acierto en uso real, sin etiquetar nada a mano.
    final_category: Mapped[str | None] = mapped_column(String(32))
    final_severity: Mapped[str | None] = mapped_column(String(16))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    model: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    image_variant: Mapped[str | None] = mapped_column(String(16))

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN " + str(CLASSIFICATION_STATUSES), name="ck_classifications_status"
        ),
        Index("ix_classifications_report", "report_id"),
        Index(
            "ix_classifications_pending",
            "next_attempt_at",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "ix_classifications_processing",
            "locked_at",
            postgresql_where=text("status = 'processing'"),
        ),
    )


class Case(Base):
    """Un problema real. Varios reportes pueden apuntar al mismo.

    Descubrir eso es la razon de ser del sistema: cuarenta y siete reportes en
    un dia son dieciocho problemas.
    """

    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")
    category: Mapped[str | None] = mapped_column(String(32))
    severity: Mapped[str | None] = mapped_column(String(16))

    # Se recalcula al entrar un reporte nuevo. Comparar contra el centro es mas
    # estable que contra el primer reporte, que por ser el primero no tiene por
    # que ser el mas exacto.
    centroid: Mapped[object | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False)
    )
    report_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # RESTRICT: borrar una cuadrilla con casos asignados falla en vez de dejar
    # los casos apuntando al vacio. Primero se reasignan.
    crew_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crews.id", ondelete="RESTRICT")
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Fecha propia y no `updated_at`: la retencion de las fotos cuelga de cuando
    # se cerro, y `updated_at` se mueve con cualquier cambio.
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closing_note: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("status IN " + str(CASE_STATUSES), name="ck_cases_status"),
        Index("ix_cases_centroid_gist", "centroid", postgresql_using="gist"),
        Index("ix_cases_category_status", "category", "status"),
        Index("ix_cases_crew", "crew_id"),
    )


class GroupingEvidence(Base):
    """Por que un reporte entro a un caso, o por que no entro.

    Un numero de confianza que cada quien interpreta distinto no sirve. Una
    lista de reportes cercanos con la distancia escrita, si. Se guardan tambien
    los descartes: saber que se decidio no agrupar es tan util como lo otro.
    """

    __tablename__ = "grouping_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE")
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)

    # Cada senal en su unidad y por separado. Un solo puntaje combinado no se
    # puede discutir; "a 12 metros y misma categoria" si.
    distance_m: Mapped[float | None] = mapped_column(Float)
    category_match: Mapped[bool | None] = mapped_column(Boolean)
    hours_apart: Mapped[float | None] = mapped_column(Float)
    text_similarity: Mapped[float | None] = mapped_column(Float)
    visual_distance: Mapped[int | None] = mapped_column(Integer)

    # En español y legible: el tablero lo muestra tal cual.
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # Con que umbrales se decidio. Sin esto, una agrupacion vieja no se puede
    # interpretar despues de recalibrar.
    thresholds: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "decision IN " + str(GROUPING_DECISIONS), name="ck_grouping_evidence_decision"
        ),
        Index("ix_grouping_evidence_report", "report_id"),
        Index("ix_grouping_evidence_case", "case_id"),
    )


class User(Base):
    """Quien puede entrar al tablero, y con que rol.

    Google dice quien es; esta tabla dice si puede. Sin ella, cualquiera con una
    cuenta de Google entraria al tablero de una institucion.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # En minusculas siempre: los proveedores no coinciden en el uso de
    # mayusculas, y comparar sin normalizar deja entrar un correo dos veces o
    # ninguna.
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'operator', 'demo')", name="ck_users_role"),
        Index("ix_users_email", "email", unique=True),
    )


class Crew(Base):
    """Una cuadrilla. Tabla y no una cadena suelta en `cases`.

    Una cuadrilla mal escrita crearia una cuadrilla fantasma a la que se le
    asignan casos que nadie mira.
    """

    __tablename__ = "crews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_crews_name", "name", unique=True),)


class CasePhoto(Base):
    """La foto del arreglo.

    Tabla propia y **no** `report_photos.kind = 'evidence'`, que es lo que la
    fase 2 habia anticipado. La anticipacion estaba mal: no se parece a una foto
    de reporte —la sube un operador, no se clasifica, no se le saca huella, y no
    puede entrar en la agrupacion nunca—. Compartiendo tabla, cada consulta de
    agrupacion necesitaria `WHERE kind='report'`, y olvidarlo una vez mete la
    foto del arreglo como si fuera otro reporte del problema.
    """

    __tablename__ = "case_photos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    # Quien la subio: una evidencia sin autor no se puede cuestionar.
    uploaded_by: Mapped[str] = mapped_column(String(320), nullable=False)

    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_key: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    bytes: Mapped[int | None] = mapped_column(Integer)
    thumbnail_bytes: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(64))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_case_photos_case", "case_id"),)


class Notification(Base):
    """Un aviso de vuelta a quien reporto.

    **A todos los que reportaron, no solo al primero.** Es la parte que casi
    nadie construye y sin la cual nadie reporta dos veces; y es lo que le da
    sentido al agrupamiento mas alla de ahorrar trabajo, porque permite
    responderle a cuatro personas con un solo arreglo.
    """

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(32), ForeignKey("channels.code"), nullable=False)
    external_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    body: Mapped[str] = mapped_column(Text, nullable=False)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("status IN " + str(NOTIFICATION_STATUSES), name="ck_notifications_status"),
        CheckConstraint("kind IN " + str(NOTIFICATION_KINDS), name="ck_notifications_kind"),
        # Una persona recibe **un** aviso por caso y tipo, aunque haya reportado
        # el mismo problema tres veces. Sin esto, quien mas reporta mas molesta
        # el sistema, que es al reves de lo que se quiere.
        UniqueConstraint(
            "case_id", "channel", "external_user_id", "kind", name="uq_notifications_destinatario"
        ),
        Index(
            "ix_notifications_pending",
            "next_attempt_at",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "ix_notifications_processing",
            "locked_at",
            postgresql_where=text("status = 'processing'"),
        ),
        Index("ix_notifications_case", "case_id"),
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
