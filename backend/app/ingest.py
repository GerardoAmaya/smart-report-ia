"""De mensaje normalizado a filas en la base.

La foto llega en un mensaje y la ubicacion en otro, asi que hay estado entre
los dos. Ese estado es el propio reporte incompleto y no una tabla de sesiones:
un reporte sin ubicacion es exactamente lo que hay que representar, y dice la
verdad al mirarlo en la base.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.channels.base import InboundMessage
from app.config import settings
from app.models import InboundUpdate, Report, ReportPhoto

# Tope del texto acumulado por reporte. El limite por usuario ya frena el
# volumen; esto evita que un solo reporte crezca sin fin a fuerza de
# mensajes sueltos.
CAPTION_MAX = 2000

PEDIR_FOTO = "Mandame una foto del problema y despues tu ubicacion."
PEDIR_UBICACION = (
    "Recibi la foto. Ahora mandame la ubicacion con el boton de abajo, para saber donde esta."
)
# No dice "quedo registrado" y punto: despues de esto llega la propuesta de
# categoria, y un mensaje que suena a final hace que la pregunta siguiente
# parezca de otra conversacion.
LISTO = (
    "Listo, ya tengo la foto y la ubicacion. Dame unos segundos, estoy "
    "revisando la foto y te digo que creo que es.\n\n"
    "Si querés, escribime que pasó. Ayuda a no confundirlo con otro reporte "
    "cercano."
)
DETALLE_GUARDADO = "Anotado, gracias."
YA_ESTA = "Ese reporte ya quedo listo. Si querés reportar otra cosa, mandame una foto."
DETALLE_Y_FALTA_UBICACION = "Anotado. Todavia me falta la ubicacion."
SIN_FOTO = "Primero mandame la foto del problema, y despues la ubicacion."
NO_ENTIENDO = "Solo puedo recibir fotos y ubicaciones."
FOTO_MUY_GRANDE = "Esa foto es demasiado grande. Mandala como foto normal, no como archivo."
UBICACION_INVALIDA = "Esas coordenadas no son validas. Usa el boton de ubicacion."
DEMASIADOS = "Ya mandaste varios reportes en poco rato. Intenta de nuevo mas tarde."


@dataclass(frozen=True)
class Reply:
    text: str
    ask_location: bool = False
    # Botones, cuando la respuesta es una pregunta cerrada.
    options: list[tuple[str, str]] | None = None
    # Id de la pulsacion que hay que acusar, si la hubo.
    choice_id: str | None = None
    # Mensaje a reemplazar, cuando la respuesta son otras opciones.
    edit_message_id: str | None = None
    # Si el texto reemplaza al mensaje de los botones o sale como aviso.
    replace_message: bool = False


def record_raw(
    session: Session, message_channel: str, external_update_id: str, payload: dict
) -> int | None:
    """Guarda el payload crudo. Devuelve None si ya estaba.

    El None es la idempotencia: Telegram reenvia el update si el webhook tarda,
    y sin esto cada reintento seria un reporte duplicado. ON CONFLICT DO
    NOTHING y no un SELECT previo porque entre el SELECT y el INSERT cabe otro
    reintento, y ahi la carrera la gana la base, no nosotros.
    """
    stmt = (
        insert(InboundUpdate)
        .values(channel=message_channel, external_update_id=external_update_id, payload=payload)
        .on_conflict_do_nothing(constraint="uq_inbound_updates_channel_extid")
        .returning(InboundUpdate.id)
    )
    return session.execute(stmt).scalar_one_or_none()


def find_open_report(session: Session, channel: str, external_user_id: str) -> Report | None:
    """El reporte de esta persona que todavia espera ubicacion."""
    corte = datetime.now(UTC) - timedelta(minutes=settings.open_report_window_minutes)
    stmt = (
        select(Report)
        .where(
            Report.channel == channel,
            Report.external_user_id == external_user_id,
            Report.status == "incomplete",
            Report.created_at >= corte,
        )
        .order_by(Report.created_at.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def find_recent_report(session: Session, channel: str, external_user_id: str) -> Report | None:
    """El ultimo reporte de esta persona, este completo o no.

    Distinto de `find_open_report`: para pegar una descripcion no hace falta que
    el reporte espere ubicacion. Quien escribe "era un hueco enorme" justo
    despues de completarlo se refiere a ese, y descartarlo seria tirar una de
    las senales con las que la fase 4 decide si dos reportes son el mismo caso.
    """
    corte = datetime.now(UTC) - timedelta(minutes=settings.open_report_window_minutes)
    stmt = (
        select(Report)
        .where(
            Report.channel == channel,
            Report.external_user_id == external_user_id,
            Report.created_at >= corte,
        )
        .order_by(Report.created_at.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def append_caption(reporte: Report, texto: str) -> None:
    """Suma texto al reporte sin pisar lo que ya habia.

    Se acumula en vez de reemplazar: alguien que manda dos frases sueltas
    escribio las dos, y quedarse con la ultima seria perder la mitad de lo que
    dijo.
    """
    texto = texto.strip()
    if not texto:
        return
    actual = (reporte.caption or "").strip()
    if texto in actual:
        # Reenvio o repeticion: no duplicar la misma frase.
        return
    combinado = f"{actual}\n{texto}".strip() if actual else texto
    reporte.caption = combinado[:CAPTION_MAX]


def coordinates_are_sane(lat: float | None, lon: float | None) -> bool:
    """Rango valido del planeta.

    Telegram no manda coordenadas invalidas, pero este endpoint es publico y la
    validacion no cuesta nada. Filtrar por el pais es otra decision y no esta
    tomada: un reporte fuera de El Salvador hoy se guarda y se ve.
    """
    if lat is None or lon is None:
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def handle(session: Session, message: InboundMessage, inbound_update_id: int | None) -> Reply:
    """Aplica el mensaje y devuelve que contestarle a la persona."""
    if message.kind == "photo":
        return _handle_photo(session, message, inbound_update_id)
    if message.kind == "location":
        return _handle_location(session, message)
    if message.kind == "start":
        return Reply(PEDIR_FOTO)
    if message.kind == "text":
        return _handle_text(session, message)
    if message.kind == "choice":
        return _handle_choice(session, message)
    return Reply(NO_ENTIENDO)


def _handle_photo(
    session: Session, message: InboundMessage, inbound_update_id: int | None
) -> Reply:
    foto = message.photo
    if foto is None:
        return Reply(NO_ENTIENDO)

    # Se compara contra lo que el update declara, antes de pedir nada: bajar
    # veinte megas para despues decidir que sobraban es pagar el ancho de banda
    # del abuso.
    if foto.declared_bytes is not None and foto.declared_bytes > settings.max_photo_bytes:
        return Reply(FOTO_MUY_GRANDE)

    reporte = find_open_report(session, message.channel, message.external_user_id)
    if reporte is None:
        reporte = Report(
            channel=message.channel,
            external_user_id=message.external_user_id,
            inbound_update_id=inbound_update_id,
            caption=(message.caption or "").strip()[:CAPTION_MAX] or None,
            status="incomplete",
        )
        session.add(reporte)
        session.flush()
    elif message.caption:
        append_caption(reporte, message.caption)

    # storage_key queda nulo y status pendiente: la subida es de la fase 2.
    session.add(
        ReportPhoto(
            report_id=reporte.id,
            channel=message.channel,
            kind="report",
            external_file_id=foto.external_file_id,
            external_file_unique_id=foto.external_file_unique_id,
            declared_bytes=foto.declared_bytes,
            width=foto.width,
            height=foto.height,
            status="pending",
        )
    )
    return Reply(PEDIR_UBICACION, ask_location=True)


def _handle_location(session: Session, message: InboundMessage) -> Reply:
    if not coordinates_are_sane(message.lat, message.lon):
        return Reply(UBICACION_INVALIDA, ask_location=True)

    reporte = find_open_report(session, message.channel, message.external_user_id)
    if reporte is None:
        return Reply(SIN_FOTO)

    # func.ST_MakePoint con floats de Python: SQLAlchemy los manda como
    # parametros ligados. Construir este SQL con una f-string seria inyeccion
    # por una via que nadie mira.
    reporte.location = func.ST_SetSRID(func.ST_MakePoint(message.lon, message.lat), 4326)
    reporte.status = "received"
    return Reply(LISTO)


def mark_processed(session: Session, inbound_update_id: int) -> None:
    """Deja constancia de que este update ya se aplico."""
    session.execute(
        update(InboundUpdate)
        .where(InboundUpdate.id == inbound_update_id)
        .values(processed_at=func.now(), process_error=None)
    )


def record_failure(session: Session, inbound_update_id: int, detalle: str) -> None:
    """Anota que fallo, sobre la fila cruda que ya esta confirmada.

    Se guarda el tipo de excepcion y no el texto completo: el mensaje puede
    llevar datos del usuario y esta tabla se mira para depurar, no para
    coleccionar datos personales.
    """
    session.execute(
        update(InboundUpdate)
        .where(InboundUpdate.id == inbound_update_id)
        .values(process_error=detalle[:500])
    )


def _handle_text(session: Session, message: InboundMessage) -> Reply:
    """Texto suelto: descripcion del problema, no ruido.

    No se pide en ningun momento. Quien reporta esta parado frente al problema y
    con prisa, y un paso obligatorio mas es fricción sobre el sensor. Pero lo
    que escribe por su cuenta es gratis, y tirarlo lo pierde para siempre.
    """
    texto = (message.caption or "").strip()
    if not texto:
        return Reply(NO_ENTIENDO)

    reporte = find_recent_report(session, message.channel, message.external_user_id)
    if reporte is None:
        return Reply(PEDIR_FOTO)

    # Confirmada la categoria, la conversacion de ese reporte se acabo. Seguir
    # pegando texto convierte un "Hola" en parte de la evidencia que lee la
    # cuadrilla, y peor: contesta "Anotado, gracias" a un saludo, que es
    # exactamente lo que hace pensar que el bot no entiende nada.
    if _ya_confirmado(session, reporte):
        return Reply(YA_ESTA)

    append_caption(reporte, texto)

    if reporte.status == "incomplete":
        return Reply(DETALLE_Y_FALTA_UBICACION, ask_location=True)
    return Reply(DETALLE_GUARDADO)


def _ya_confirmado(session: Session, reporte: Report) -> bool:
    """Si una persona ya confirmo o corrigio la categoria de este reporte."""
    from app.models import Classification

    return (
        session.execute(
            select(Classification.id).where(
                Classification.report_id == reporte.id,
                Classification.confirmed_at.is_not(None),
            )
        ).first()
        is not None
    )


def _handle_choice(session: Session, message: InboundMessage) -> Reply:
    """Un boton pulsado: confirmar o corregir la categoria propuesta."""
    from app import confirm

    if not message.choice:
        return Reply(NO_ENTIENDO)

    texto, opciones, reemplaza = confirm.handle_choice(
        session, message.external_user_id, message.choice
    )
    return Reply(
        texto,
        options=opciones or None,
        choice_id=message.choice_id,
        edit_message_id=message.choice_message_id,
        replace_message=reemplaza,
    )
