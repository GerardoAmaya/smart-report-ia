"""La API del tablero.

Quien despacha mira esto ocho horas y su problema no es recibir reportes sino
**saber cuales son el mismo**. Por eso el detalle de un caso trae la evidencia
de cada union escrita, no un puntaje.

Todo pide permiso. `VER` para mirar, `DESPACHAR` para cambiar algo, `BORRAR`
para lo que no vuelve. El permiso se comprueba **aqui** y no en la interfaz:
esconder un boton no impide llamar a la API.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from geoalchemy2 import Geometry
from sqlalchemy import case, cast, func, select, text
from sqlalchemy.orm import Session as OrmSession

from app import dispatch, grouping, images, storage
from app.auth import requiere
from app.config import settings
from app.db import SesionBD
from app.models import (
    Case,
    CasePhoto,
    Classification,
    Crew,
    GroupingEvidence,
    Notification,
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

    crew = session.get(Crew, caso.crew_id) if caso.crew_id else None

    evidencias = (
        session.execute(
            select(CasePhoto)
            .where(CasePhoto.case_id == case_id, CasePhoto.deleted_at.is_(None))
            .order_by(CasePhoto.created_at)
        )
        .scalars()
        .all()
    )

    # Cuantos avisos salieron y a cuantos les llego. Se enseña porque es la
    # parte que casi nadie construye: si no se ve, nadie sabe que existe.
    avisos = dict(
        session.execute(
            select(Notification.status, func.count(Notification.id))
            .where(Notification.case_id == case_id)
            .group_by(Notification.status)
        ).all()
    )

    return {
        "id": str(caso.id),
        "status": caso.status,
        "category": caso.category,
        "severity": caso.severity,
        "report_count": caso.report_count,
        "created_at": caso.created_at.isoformat(),
        "crew": {"id": str(crew.id), "name": crew.name} if crew else None,
        "assigned_at": caso.assigned_at.isoformat() if caso.assigned_at else None,
        "closed_at": caso.closed_at.isoformat() if caso.closed_at else None,
        "closing_note": caso.closing_note,
        "evidence": [
            {
                "id": str(f.id),
                "thumbnail_url": _url_de_foto(f.thumbnail_key),
                "original_url": _url_de_foto(f.storage_key),
                "uploaded_by": f.uploaded_by,
                "created_at": f.created_at.isoformat(),
            }
            for f in evidencias
        ],
        "notifications": {
            "sent": avisos.get("sent", 0),
            "pending": avisos.get("pending", 0) + avisos.get("processing", 0),
            "failed": avisos.get("failed", 0),
        },
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


@router.get("/metrics")
def metricas(
    usuario: Ver,
    session: SesionBD,
    dias: int = Query(30, ge=1, le=365),
) -> dict:
    """Lo que el sistema logra, no lo que contiene.

    La cifra de arriba es **la proporcion de reportes que terminan agrupados**,
    que PLAN.md llama la medida directa de cuanto trabajo ahorra el sistema:
    cuarenta y siete reportes en un dia son dieciocho problemas. Un tablero que
    solo lista casos no enseña eso, y es lo unico que justifica todo lo demas.
    """
    desde = datetime.now(UTC) - timedelta(days=dias)

    reportes, casos = session.execute(
        select(
            func.count(Report.id),
            func.count(func.distinct(Report.case_id)),
        ).where(Report.created_at >= desde, Report.case_id.is_not(None))
    ).one()

    # Entrada por dia. Se rellenan los dias sin reportes: una serie con huecos
    # dibuja una linea que salta y miente sobre el ritmo real.
    filas = session.execute(
        select(
            func.date_trunc("day", Report.created_at).label("dia"),
            func.count(Report.id),
        )
        .where(Report.created_at >= desde)
        .group_by(text("dia"))
        .order_by(text("dia"))
    ).all()
    por_dia = {d.date().isoformat(): n for d, n in filas}

    # Desde hoy hacia atras: contar desde `desde` dejaba el ultimo dia en ayer
    # y la grafica terminaba un dia antes que el reloj, que es de esos fallos
    # que nadie mira hasta que alguien pregunta por un reporte de hoy.
    hoy = datetime.now(UTC).date()
    serie = []
    for i in range(dias - 1, -1, -1):
        dia = (hoy - timedelta(days=i)).isoformat()
        serie.append({"dia": dia, "reportes": por_dia.get(dia, 0)})

    categorias = session.execute(
        select(Case.category, func.count(Case.id), func.sum(Case.report_count))
        .where(Case.category.is_not(None), Case.status != "discarded")
        .group_by(Case.category)
        .order_by(func.count(Case.id).desc())
    ).all()

    severidades = dict(
        session.execute(
            select(Case.severity, func.count(Case.id))
            .where(Case.status.in_(("open", "assigned", "in_progress")))
            .group_by(Case.severity)
        ).all()
    )

    dudosos = session.execute(
        select(func.count(Report.id)).where(Report.grouping_status == "doubtful")
    ).scalar_one()

    # Lo que costo hasta ahora. Se muestra porque el costo por reporte es una
    # de las cuatro metricas del proyecto y esconderlo lo volveria una promesa.
    costo = session.execute(
        select(func.coalesce(func.sum(Classification.cost_usd), 0))
    ).scalar_one()

    return {
        "dias": dias,
        "reportes": reportes,
        "casos": casos,
        # Cuantos reportes se ahorraron de atender por separado.
        "ahorro": max(0, reportes - casos),
        "serie": serie,
        "categorias": [
            {"categoria": c, "casos": n, "reportes": int(r or 0)} for c, n, r in categorias
        ],
        "severidades": {
            "alta": severidades.get("alta", 0),
            "media": severidades.get("media", 0),
            "baja": severidades.get("baja", 0),
        },
        "dudosos": dudosos,
        "costo_usd": float(costo or 0),
    }


# --- Despacho y cierre ---


@router.get("/crews")
def listar_cuadrillas(usuario: Ver, session: SesionBD) -> dict:
    filas = (
        session.execute(select(Crew).where(Crew.is_active.is_(True)).order_by(Crew.name))
        .scalars()
        .all()
    )
    return {"crews": [{"id": str(c.id), "name": c.name, "notes": c.notes} for c in filas]}


@router.post("/cases/{case_id}/assign")
def asignar(
    case_id: UUID,
    usuario: Despachar,
    session: SesionBD,
    crew_id: Annotated[UUID, Query()],
) -> dict:
    """Asigna el caso a una cuadrilla y **avisa a todos los que reportaron**."""
    caso = _caso_o_404(session, case_id)
    crew = session.get(Crew, crew_id)
    if crew is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no existe esa cuadrilla")

    try:
        avisados = dispatch.assign(session, caso, crew)
    except dispatch.NoSePuede as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    session.commit()
    return {"ok": True, "status": caso.status, "crew": crew.name, "avisados": avisados}


@router.post("/cases/{case_id}/start")
def empezar(case_id: UUID, usuario: Despachar, session: SesionBD) -> dict:
    caso = _caso_o_404(session, case_id)
    try:
        avisados = dispatch.start(session, caso)
    except dispatch.NoSePuede as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    session.commit()
    return {"ok": True, "status": caso.status, "avisados": avisados}


@router.post("/cases/{case_id}/evidence")
async def subir_evidencia(
    case_id: UUID,
    usuario: Despachar,
    session: SesionBD,
    archivo: Annotated[UploadFile, File()],
) -> dict:
    """La foto del arreglo.

    Se valida abriendola, igual que las de reporte: un archivo con cabecera JPEG
    y basura detras pasa cualquier numero magico y revienta despues.
    """
    caso = _caso_o_404(session, case_id)

    datos = await archivo.read()
    if len(datos) > settings.max_photo_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"la foto pasa de {settings.max_photo_bytes // 1024 // 1024} MB",
        )
    try:
        validada = images.validate(datos)
    except images.ImagenInvalida as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    foto_id = uuid4()
    clave = storage.build_key(caso.id, foto_id, kind="evidencia", ext=validada.extension)
    guardado = storage.put(clave, datos, validada.mime)

    miniatura = images.thumbnail(datos)
    clave_min = storage.build_key(caso.id, foto_id, kind="evidencia-thumb", ext="jpg")
    guardada_min = storage.put(clave_min, miniatura, "image/jpeg")

    session.add(
        CasePhoto(
            id=foto_id,
            case_id=caso.id,
            uploaded_by=usuario.email,
            storage_key=guardado.key,
            thumbnail_key=guardada_min.key,
            content_sha256=guardado.sha256,
            bytes=guardado.bytes,
            thumbnail_bytes=guardada_min.bytes,
            width=validada.width,
            height=validada.height,
            mime_type=validada.mime,
        )
    )
    session.commit()
    return {"ok": True, "id": str(foto_id)}


@router.post("/cases/{case_id}/close")
def cerrar(
    case_id: UUID,
    usuario: Despachar,
    session: SesionBD,
    nota: Annotated[str | None, Query(max_length=500)] = None,
) -> dict:
    """Cierra el caso **con foto de evidencia** y avisa a todos.

    Sin foto no se cierra: cerrar sin evidencia convierte el cierre en una
    afirmacion que nadie puede comprobar, y el tablero existe para que las
    afirmaciones se puedan comprobar.
    """
    caso = _caso_o_404(session, case_id)
    try:
        avisados = dispatch.close(session, caso, nota)
    except dispatch.NoSePuede as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    session.commit()
    return {"ok": True, "status": caso.status, "avisados": avisados}


@router.post("/cases/{case_id}/reopen")
def reabrir(case_id: UUID, usuario: Despachar, session: SesionBD) -> dict:
    caso = _caso_o_404(session, case_id)
    try:
        dispatch.reopen(session, caso)
    except dispatch.NoSePuede as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    session.commit()
    return {"ok": True, "status": caso.status}


def _caso_o_404(session: OrmSession, case_id: UUID) -> Case:
    caso = session.get(Case, case_id)
    if caso is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no existe ese caso")
    return caso
