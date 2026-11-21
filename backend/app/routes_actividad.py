"""Lo que acaba de pasar: el feed de actividad del tablero.

Se arma con lo que ya hay —reportes, casos, avisos— y no con una tabla de
eventos aparte. Una tabla mas seria un segundo registro de los mismos hechos, y
el segundo registro es el que se queda viejo: basta un sitio que cambie un caso
sin escribir su evento. Asi el feed no puede decir nada que los datos no digan.

**Nada que identifique a quien reporto.** Ni su usuario de Telegram ni lo que
escribio: el feed lo ve cualquiera con permiso de mirar, incluido el invitado
publico. Sale la categoria, la direccion y los numeros.

Una consulta por tipo de evento, cada una con su propio tope, y la mezcla se
ordena aca. Son cinco consultas para veinte filas; un UNION de cinco formas
distintas seria mas dificil de leer sin ser mas rapido.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.auth import requiere
from app.confirm import ETIQUETAS
from app.db import SesionBD
from app.models import Case, Crew, Notification, Report, User
from app.permissions import Permission
from app.routes_board import direccion_del_caso

router = APIRouter(prefix="/board", tags=["actividad"])

Ver = Annotated[User, Depends(requiere(Permission.VER))]


def _personas(n: int) -> str:
    return "1 persona" if n == 1 else f"{n} personas"


def _lugar(categoria: str | None, direccion: str | None) -> str:
    """«Calle o acera · Colonia Escalón». Lo que dice donde y que, sin quien."""
    partes = [ETIQUETAS.get(categoria, categoria) if categoria else None, direccion]
    return " · ".join(p for p in partes if p)


def _evento(tipo: str, clave: str, cuando: datetime, caso_id, texto: str, detalle: str) -> dict:
    return {
        # Estable entre lecturas: el tablero lo usa para saber que evento es
        # nuevo y animar solo ese.
        "id": f"{tipo}:{clave}",
        "tipo": tipo,
        "cuando": cuando.isoformat(),
        "caso_id": str(caso_id),
        "texto": texto,
        "detalle": detalle or None,
        # Para ordenar; no sale en la respuesta.
        "_t": cuando,
    }


def _reportes(session: Session, limite: int) -> list[dict]:
    """Reportes que ya estan en un caso: nuevos, juntados o en duda."""
    # El lugar del reporte en su caso, en la misma consulta: «ahora son 3».
    otro = Report.__table__.alias("otro")
    posicion = (
        select(func.count())
        .where(otro.c.case_id == Report.case_id, otro.c.created_at <= Report.created_at)
        .correlate(Report)
        .scalar_subquery()
    )
    filas = session.execute(
        select(
            Report.id,
            Report.created_at,
            Report.case_id,
            Report.grouping_status,
            Case.category,
            direccion_del_caso(),
            posicion,
        )
        .join(Case, Case.id == Report.case_id)
        .order_by(Report.created_at.desc())
        .limit(limite)
    ).all()

    eventos = []
    for rid, cuando, caso_id, estado, categoria, direccion, n in filas:
        lugar = _lugar(categoria, direccion)
        if estado == "grouped" and n > 1:
            otros = "otro reporte" if n == 2 else f"otros {n - 1} reportes"
            eventos.append(
                _evento(
                    "agrupado",
                    str(rid),
                    cuando,
                    caso_id,
                    f"Se juntó con {otros} · ahora son {n}",
                    lugar,
                )
            )
        elif estado == "doubtful":
            eventos.append(
                _evento(
                    "dudoso",
                    str(rid),
                    cuando,
                    caso_id,
                    "Quedó en duda · espera que alguien decida",
                    lugar,
                )
            )
        else:
            eventos.append(
                _evento("reporte", str(rid), cuando, caso_id, f"Nuevo reporte · {lugar}", "")
            )
    return eventos


def _asignados(session: Session, limite: int) -> list[dict]:
    filas = session.execute(
        select(Case.id, Case.assigned_at, Case.category, Crew.name, direccion_del_caso())
        .join(Crew, Crew.id == Case.crew_id)
        .where(Case.assigned_at.is_not(None))
        .order_by(Case.assigned_at.desc())
        .limit(limite)
    ).all()
    return [
        _evento(
            "asignado",
            f"{caso_id}:{cuando.isoformat()}",
            cuando,
            caso_id,
            f"Asignado a {cuadrilla}",
            _lugar(categoria, direccion),
        )
        for caso_id, cuando, categoria, cuadrilla, direccion in filas
    ]


def _en_curso(session: Session, limite: int) -> list[dict]:
    """El caso no guarda cuando empezo: lo dice el aviso de «en curso».

    El aviso se encola en la misma transaccion que cambia el estado, asi que su
    fecha de creacion es la del cambio.
    """
    cuando = func.min(Notification.created_at).label("cuando")
    filas = session.execute(
        select(Notification.case_id, cuando, Case.category, direccion_del_caso())
        .join(Case, Case.id == Notification.case_id)
        .where(Notification.kind == "in_progress")
        .group_by(Notification.case_id, Case.id)
        .order_by(cuando.desc())
        .limit(limite)
    ).all()
    return [
        _evento(
            "en_curso",
            f"{caso_id}:{momento.isoformat()}",
            momento,
            caso_id,
            "Ya están trabajando",
            _lugar(categoria, direccion),
        )
        for caso_id, momento, categoria, direccion in filas
    ]


def _cerrados(session: Session, limite: int) -> list[dict]:
    # Personas, no mensajes: quien reporto dos veces el mismo problema recibio
    # un aviso, y el feed no puede decir dos.
    avisadas = (
        select(
            func.count(func.distinct(tuple_(Notification.channel, Notification.external_user_id)))
        )
        .where(
            Notification.case_id == Case.id,
            Notification.kind == "closed",
            Notification.status == "sent",
        )
        .correlate(Case)
        .scalar_subquery()
    )
    filas = session.execute(
        select(Case.id, Case.closed_at, Case.category, direccion_del_caso(), avisadas)
        .where(Case.closed_at.is_not(None))
        .order_by(Case.closed_at.desc())
        .limit(limite)
    ).all()
    eventos = []
    for caso_id, cuando, categoria, direccion, n in filas:
        texto = "Resuelto" + (f" · se avisó a {_personas(n)}" if n else "")
        eventos.append(
            _evento(
                "cerrado",
                f"{caso_id}:{cuando.isoformat()}",
                cuando,
                caso_id,
                texto,
                _lugar(categoria, direccion),
            )
        )
    return eventos


def _avisos(session: Session, limite: int) -> list[dict]:
    """Avisos de asignado y en curso que ya llegaron, por caso y tipo.

    El de cierre no va aca: ya lo dice el evento «Resuelto», y repetirlo seria
    contar dos veces el mismo hecho.
    """
    cuando = func.max(Notification.sent_at).label("cuando")
    personas = func.count(
        func.distinct(tuple_(Notification.channel, Notification.external_user_id))
    )
    filas = session.execute(
        select(
            Notification.case_id,
            Notification.kind,
            cuando,
            personas,
            Case.category,
            direccion_del_caso(),
        )
        .join(Case, Case.id == Notification.case_id)
        .where(
            Notification.status == "sent",
            Notification.kind.in_(("assigned", "in_progress")),
        )
        .group_by(Notification.case_id, Notification.kind, Case.id)
        .order_by(cuando.desc())
        .limit(limite)
    ).all()
    que = {"assigned": "que se asignó", "in_progress": "que ya están trabajando"}
    return [
        _evento(
            "aviso",
            f"{caso_id}:{tipo}",
            momento,
            caso_id,
            f"Se avisó a {_personas(n)} {que[tipo]}",
            _lugar(categoria, direccion),
        )
        for caso_id, tipo, momento, n, categoria, direccion in filas
    ]


@router.get("/actividad")
def actividad(
    usuario: Ver,
    session: SesionBD,
    limite: int = Query(20, ge=1, le=100),
) -> dict:
    """Los ultimos hechos del sistema, del mas nuevo al mas viejo."""
    eventos: list[dict] = []
    for fuente in (_reportes, _asignados, _en_curso, _cerrados, _avisos):
        eventos.extend(fuente(session, limite))
    # Por la fecha y no por el texto ISO: sin microsegundos el texto es mas
    # corto, y dos hechos del mismo segundo podian salir al reves.
    eventos.sort(key=lambda e: e["_t"], reverse=True)
    for e in eventos:
        del e["_t"]
    return {"eventos": eventos[:limite]}
