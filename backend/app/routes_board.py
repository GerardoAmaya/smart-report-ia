"""La API del tablero.

Quien despacha mira esto ocho horas y su problema no es recibir reportes sino
**saber cuales son el mismo**. Por eso el detalle de un caso trae la evidencia
de cada union escrita, no un puntaje.

Todo pide permiso. `VER` para mirar, `DESPACHAR` para cambiar algo, `BORRAR`
para lo que no vuelve. El permiso se comprueba **aqui** y no en la interfaz:
esconder un boton no impide llamar a la API.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2 import Geometry
from sqlalchemy import case, cast, func, select

from app import grouping, storage
from app.auth import requiere
from app.db import SesionBD
from app.models import (
    Case,
    Classification,
    GroupingEvidence,
    Report,
    ReportPhoto,
    User,
)
from app.permissions import Permission

router = APIRouter(prefix="/board", tags=["board"])

Ver = Annotated[User, Depends(requiere(Permission.VER))]
Despachar = Annotated[User, Depends(requiere(Permission.DESPACHAR))]
Borrar = Annotated[User, Depends(requiere(Permission.BORRAR))]


def _url_de_foto(clave: str | None) -> str | None:
    """Enlace temporal. El navegador baja directo del almacenamiento."""
    return storage.presigned_url(clave) if clave else None


@router.get("/cases")
def listar_casos(
    usuario: Ver,
    session: SesionBD,
    status_: str | None = Query(None, alias="status"),
    category: str | None = None,
    limite: int = Query(50, ge=1, le=200),
) -> dict:
    """La cola. Lo mas urgente y lo mas reportado primero."""
    condiciones = []
    if status_:
        condiciones.append(Case.status == status_)
    if category:
        condiciones.append(Case.category == category)

    # El orden no es por fecha: quien despacha necesita ver primero lo que mas
    # gente reporta y lo mas grave, no lo mas reciente.
    orden_severidad = case(
        (Case.severity == "alta", 0),
        (Case.severity == "media", 1),
        (Case.severity == "baja", 2),
        else_=3,
    )

    filas = session.execute(
        select(
            Case,
            func.count(func.distinct(Report.id)).label("reportes"),
            func.count(func.distinct(Report.id))
            .filter(Report.grouping_status == "doubtful")
            .label("dudosos"),
        )
        .outerjoin(Report, Report.case_id == Case.id)
        .where(*condiciones)
        .group_by(Case.id)
        .order_by(orden_severidad, func.count(Report.id).desc(), Case.created_at)
        .limit(limite)
    ).all()

    return {
        "cases": [
            {
                "id": str(caso.id),
                "status": caso.status,
                "category": caso.category,
                "severity": caso.severity,
                "report_count": reportes,
                "doubtful_count": dudosos,
                "created_at": caso.created_at.isoformat(),
                "updated_at": caso.updated_at.isoformat(),
            }
            for caso, reportes, dudosos in filas
        ]
    }


@router.get("/cases/map")
def casos_para_el_mapa(
    usuario: Ver,
    session: SesionBD,
    limite: int = Query(500, ge=1, le=2000),
) -> dict:
    """Puntos para el mapa, con cuantos reportan cada uno.

    **El tamaño del pin es cuantos reportan lo mismo.** Un mapa de puntos
    iguales tira a la basura la informacion de donde se concentra el reclamo.
    """
    filas = session.execute(
        select(
            Case.id,
            Case.category,
            Case.severity,
            Case.status,
            Case.report_count,
            func.ST_Y(cast(Case.centroid, Geometry)).label("lat"),
            func.ST_X(cast(Case.centroid, Geometry)).label("lon"),
        )
        .where(Case.centroid.is_not(None), Case.status != "discarded")
        .limit(limite)
    ).all()

    return {
        "points": [
            {
                "id": str(cid),
                "category": categoria,
                "severity": severidad,
                "status": estado,
                "report_count": cuantos,
                "lat": lat,
                "lon": lon,
            }
            for cid, categoria, severidad, estado, cuantos, lat, lon in filas
        ]
    }


@router.get("/cases/{case_id}")
def detalle_del_caso(
    case_id: UUID,
    usuario: Ver,
    session: SesionBD,
) -> dict:
    """El caso con sus reportes y **por que estan juntos**.

    La verificacion de esta fase es que un operador que no vio el sistema antes
    entienda por que cuatro reportes estan juntos sin que nadie se lo explique.
    Eso se juega aqui: cada reporte trae su distancia al caso y el motivo en
    español.
    """
    caso = session.get(Case, case_id)
    if caso is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no existe ese caso")

    reportes = (
        session.execute(select(Report).where(Report.case_id == case_id).order_by(Report.created_at))
        .scalars()
        .all()
    )

    evidencias = (
        session.execute(
            select(GroupingEvidence)
            .where(GroupingEvidence.report_id.in_([r.id for r in reportes] or [None]))
            .order_by(GroupingEvidence.created_at)
        )
        .scalars()
        .all()
    )
    por_reporte: dict[str, list[GroupingEvidence]] = {}
    for ev in evidencias:
        por_reporte.setdefault(str(ev.report_id), []).append(ev)

    salida = []
    for reporte in reportes:
        fotos = (
            session.execute(
                select(ReportPhoto)
                .where(ReportPhoto.report_id == reporte.id, ReportPhoto.deleted_at.is_(None))
                .order_by(ReportPhoto.created_at)
            )
            .scalars()
            .all()
        )
        clasificacion = session.execute(
            select(Classification)
            .where(Classification.report_id == reporte.id)
            .order_by(Classification.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        coords = session.execute(
            select(
                func.ST_Y(cast(Report.location, Geometry)),
                func.ST_X(cast(Report.location, Geometry)),
            ).where(Report.id == reporte.id)
        ).one_or_none()

        salida.append(
            {
                "id": str(reporte.id),
                "caption": reporte.caption,
                "grouping_status": reporte.grouping_status,
                "created_at": reporte.created_at.isoformat(),
                "lat": coords[0] if coords else None,
                "lon": coords[1] if coords else None,
                "photos": [
                    {
                        "id": str(f.id),
                        "thumbnail_url": _url_de_foto(f.thumbnail_key),
                        "original_url": _url_de_foto(f.storage_key),
                        "status": f.status,
                    }
                    for f in fotos
                ],
                "classification": (
                    {
                        "proposed_category": clasificacion.proposed_category,
                        "final_category": clasificacion.final_category,
                        "severity": clasificacion.final_severity,
                        "reason": clasificacion.proposed_reason,
                        "confirmed": clasificacion.confirmed_at is not None,
                        # Se dice si la persona corrigio al modelo: eso es lo
                        # que deja ver donde el modelo se equivoca.
                        "corrected": clasificacion.status == "corrected",
                    }
                    if clasificacion
                    else None
                ),
                "evidence": [
                    {
                        "decision": ev.decision,
                        "distance_m": ev.distance_m,
                        "hours_apart": ev.hours_apart,
                        "text_similarity": ev.text_similarity,
                        "visual_distance": ev.visual_distance,
                        "reason": ev.reason,
                        "thresholds": ev.thresholds,
                    }
                    for ev in por_reporte.get(str(reporte.id), [])
                ],
            }
        )

    return {
        "id": str(caso.id),
        "status": caso.status,
        "category": caso.category,
        "severity": caso.severity,
        "report_count": caso.report_count,
        "created_at": caso.created_at.isoformat(),
        "reports": salida,
    }


@router.post("/reports/{report_id}/ungroup")
def separar_del_caso(
    report_id: UUID,
    usuario: Despachar,
    session: SesionBD,
) -> dict:
    """Saca un reporte de su caso.

    **Se puede deshacer** es parte del contrato: una agrupacion irreversible
    obliga a confiar en un umbral que todavia no esta calibrado.
    """
    reporte = session.get(Report, report_id)
    if reporte is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no existe ese reporte")
    if reporte.case_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "ese reporte no esta en ningun caso")

    grouping.ungroup(session, reporte, f"separado por {usuario.email}")
    session.commit()
    return {"ok": True, "case_id": str(reporte.case_id) if reporte.case_id else None}


@router.post("/cases/{case_id}/status")
def cambiar_estado(
    case_id: UUID,
    usuario: Despachar,
    nuevo: Annotated[str, Query(pattern="^(open|assigned|in_progress|closed)$")],
    session: SesionBD,
) -> dict:
    """Cambia el estado del caso. `discarded` no esta: eso es borrar."""
    caso = session.get(Case, case_id)
    if caso is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no existe ese caso")

    caso.status = nuevo
    session.commit()
    return {"ok": True, "status": caso.status}


@router.delete("/cases/{case_id}")
def descartar_caso(
    case_id: UUID,
    usuario: Borrar,
    session: SesionBD,
) -> dict:
    """Descarta un caso. **El usuario de prueba no llega aqui.**

    Va a entrar gente a tocar todo, que para eso esta: que asigne, agrupe,
    separe y cierre; que no vacie la base.
    """
    caso = session.get(Case, case_id)
    if caso is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no existe ese caso")

    # Se marca, no se borra: el historial de los reportes no tiene por que
    # evaporarse porque alguien descarte el caso.
    caso.status = "discarded"
    session.commit()
    return {"ok": True}
