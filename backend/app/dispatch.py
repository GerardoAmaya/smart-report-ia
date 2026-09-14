"""Despacho y cierre.

La parte que casi nadie construye: **avisarle de vuelta a todos los que
reportaron, no solo al primero.** Sin eso nadie reporta dos veces, y es lo que
le da sentido al agrupamiento mas alla de ahorrar trabajo — permite responderle
a cuatro personas con un solo arreglo.

El aviso **no se manda desde aqui**: se encola. Mandar cuatro mensajes dentro de
la peticion que cierra el caso la volveria lenta y, peor, un fallo en el cuarto
dejaria el caso sin cerrar. El cierre es un hecho; avisarlo es un intento que
puede reintentarse.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Case, Crew, Notification, Report
from app.taxonomy import Category

log = logging.getLogger("smart_report.dispatch")

ETIQUETA_CATEGORIA: dict[str, str] = {
    Category.VIALIDAD: "la calle o acera",
    Category.ALUMBRADO: "el alumbrado",
    Category.AGUA: "el agua o drenaje",
    Category.DESECHOS: "la basura",
    Category.RIESGO_ESTRUCTURAL: "el riesgo de derrumbe",
    Category.ESPACIO_PUBLICO: "el espacio publico",
}


def _cosa(caso: Case) -> str:
    return ETIQUETA_CATEGORIA.get(caso.category or "", "lo que reportaste")


def mensaje(caso: Case, kind: str, crew: Crew | None = None) -> str:
    """Lo que le llega a quien reporto.

    Se le habla de **su** reporte, no del caso: quien reporto un hueco no sabe
    que existe un "caso 4f2a" ni por que su foto esta junto a otras tres. El
    agrupamiento es un detalle del sistema, no de su problema.
    """
    if kind == "assigned":
        quien = f" a {crew.name}" if crew else ""
        return (
            f"Tu reporte sobre {_cosa(caso)} ya fue asignado{quien}. Te aviso cuando este resuelto."
        )
    if kind == "in_progress":
        return f"Ya estan trabajando en lo que reportaste sobre {_cosa(caso)}."
    if kind == "closed":
        base = f"Lo que reportaste sobre {_cosa(caso)} quedo resuelto."
        if caso.closing_note:
            base += f"\n\n{caso.closing_note}"
        return base + "\n\nGracias por reportarlo."
    return "Hubo un cambio en lo que reportaste."


def destinatarios(session: Session, caso: Case) -> list[tuple[str, str]]:
    """Quienes reportaron este caso, **sin repetir**.

    Distintos por (canal, usuario): alguien que reporto el mismo hueco tres
    veces recibe un aviso, no tres. Quien mas reporta no puede acabar mas
    molestado por el sistema.
    """
    filas = session.execute(
        select(Report.channel, Report.external_user_id).where(Report.case_id == caso.id).distinct()
    ).all()
    return [(c, u) for c, u in filas]


def enqueue(session: Session, caso: Case, kind: str, crew: Crew | None = None) -> int:
    """Encola un aviso por persona. Devuelve cuantos se encolaron nuevos.

    `ON CONFLICT DO NOTHING` sobre el unico de (caso, canal, usuario, tipo): si
    alguien reabre y vuelve a cerrar el caso, no se reenvia el mismo aviso. Un
    sistema que avisa dos veces de lo mismo se aprende a ignorar.
    """
    texto = mensaje(caso, kind, crew)
    nuevos = 0

    for canal, usuario in destinatarios(session, caso):
        resultado = session.execute(
            insert(Notification)
            .values(
                case_id=caso.id,
                channel=canal,
                external_user_id=usuario,
                kind=kind,
                body=texto,
                status="pending",
            )
            .on_conflict_do_nothing(constraint="uq_notifications_destinatario")
            .returning(Notification.id)
        ).scalar_one_or_none()
        if resultado is not None:
            nuevos += 1

    if nuevos:
        log.info("caso %s: %s avisos de '%s' encolados", caso.id, nuevos, kind)
    return nuevos


# --- Acciones sobre el caso ---


class NoSePuede(Exception):
    """La accion no es valida en el estado en que esta el caso."""


def assign(session: Session, caso: Case, crew: Crew) -> int:
    if caso.status in ("closed", "discarded"):
        raise NoSePuede("un caso cerrado no se asigna; primero hay que reabrirlo")
    if not crew.is_active:
        raise NoSePuede(f"la cuadrilla {crew.name} esta dada de baja")

    caso.crew_id = crew.id
    caso.assigned_at = datetime.now(UTC)
    caso.status = "assigned"
    return enqueue(session, caso, "assigned", crew)


def start(session: Session, caso: Case) -> int:
    if caso.crew_id is None:
        raise NoSePuede("primero hay que asignarle una cuadrilla")
    if caso.status in ("closed", "discarded"):
        raise NoSePuede("un caso cerrado no se puede poner en curso")

    caso.status = "in_progress"
    return enqueue(session, caso, "in_progress")


def close(session: Session, caso: Case, nota: str | None, exigir_evidencia: bool = True) -> int:
    """Cierra el caso y encola el aviso a todos los que reportaron.

    **Con foto de evidencia.** Cerrar sin foto convierte el cierre en una
    afirmacion que nadie puede comprobar, y el tablero existe precisamente para
    que las afirmaciones se puedan comprobar.
    """
    from app.models import CasePhoto

    if caso.status == "closed":
        raise NoSePuede("ese caso ya estaba cerrado")

    if exigir_evidencia:
        tiene = session.execute(
            select(CasePhoto.id).where(CasePhoto.case_id == caso.id, CasePhoto.deleted_at.is_(None))
        ).first()
        if tiene is None:
            raise NoSePuede("hace falta una foto del arreglo antes de cerrar")

    caso.status = "closed"
    caso.closed_at = datetime.now(UTC)
    caso.closing_note = (nota or "").strip() or None
    return enqueue(session, caso, "closed")


def reopen(session: Session, caso: Case) -> None:
    """Reabre un caso cerrado.

    Se limpia `closed_at` porque de ahi cuelga la retencion de las fotos: un
    caso reabierto no puede seguir contando los noventa dias del cierre
    anterior.
    """
    if caso.status != "closed":
        raise NoSePuede("solo se reabre lo que esta cerrado")

    caso.status = "assigned" if caso.crew_id else "open"
    caso.closed_at = None
