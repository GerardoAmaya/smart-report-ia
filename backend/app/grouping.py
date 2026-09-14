"""Agrupacion de reportes en casos. La parte dificil.

**El modelo propone, el codigo decide.** Aca no interviene ningun modelo: la
decision la toma codigo con umbrales, sobre distancia medida con PostGIS y
categoria confirmada por una persona.

**La asimetria que manda todo.** Separar dos reportes que eran el mismo caso
genera trabajo duplicado, que es molesto. Juntar dos problemas distintos esconde
uno detras de un ticket resuelto, y nadie se entera nunca. El umbral se calibra
contra el segundo error, no contra el promedio de los dos.

Por eso hay **tres salidas y no dos**:

- `grouped`  — entra al caso, con la evidencia escrita
- `doubtful` — queda en su propio caso, con el candidato anotado y el motivo.
               Se equivoca hacia el error molesto, nunca hacia el grave.
- `alone`    — caso nuevo, sin nada cerca

Lo que queda en el limite no se agrupa ni se descarta: espera decision humana.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Case, GroupingEvidence, Report, ReportPhoto
from app.taxonomy import Category

log = logging.getLogger("smart_report.grouping")


@dataclass(frozen=True)
class Candidato:
    case: Case
    distance_m: float
    hours_apart: float
    text_similarity: float
    visual_distance: int | None


def umbrales() -> dict:
    """Los umbrales con los que se decide, para guardarlos con la evidencia.

    Sin esto, una agrupacion vieja no se puede interpretar despues de
    recalibrar: no se sabria si se decidio con estos numeros o con otros.
    """
    return {
        "group_max_distance_m": settings.group_max_distance_m,
        "doubtful_max_distance_m": settings.doubtful_max_distance_m,
        "same_image_max_bits": settings.same_image_max_bits,
    }


# --- Semejanza textual ---

_PALABRA = re.compile(r"[a-záéíóúñü]{4,}", re.IGNORECASE)

# Palabras que aparecen en casi todos los reportes y no distinguen nada. Sin
# quitarlas, "hay un hueco aqui" y "hay una fuga aqui" se parecerian mucho.
VACIAS = {
    "hay",
    "esta",
    "este",
    "esto",
    "aqui",
    "alli",
    "para",
    "como",
    "pero",
    "todo",
    "toda",
    "muy",
    "que",
    "por",
    "con",
    "una",
    "unos",
    "unas",
    "calle",
    "zona",
    "lugar",
    "favor",
    "urgente",
    "arreglar",
    "reparar",
}


def text_similarity(a: str | None, b: str | None) -> float:
    """Jaccard sobre palabras largas. Cero a uno.

    Deliberadamente tosco: los textos son cortos, muchos estan vacios, y algo
    mas fino daria una precision que el dato no tiene. Se guarda como evidencia
    pero no decide por si solo.
    """
    if not a or not b:
        return 0.0
    pa = {p.lower() for p in _PALABRA.findall(a)} - VACIAS
    pb = {p.lower() for p in _PALABRA.findall(b)} - VACIAS
    if not pa or not pb:
        return 0.0
    return len(pa & pb) / len(pa | pb)


# --- Busqueda de candidatos ---


def candidatos(session: Session, reporte: Report) -> list[Candidato]:
    """Casos abiertos de la misma categoria, cerca, ordenados por distancia.

    Solo casos **abiertos**: un caso cerrado significa que alguien lo arreglo, y
    un reporte nuevo en el mismo sitio es un problema que volvio, no el mismo
    ticket. Eso ademas hace innecesaria una ventana de tiempo explicita.
    """
    categoria = _categoria_de(session, reporte)
    if categoria is None or reporte.location is None:
        return []

    punto = reporte.location
    distancia = func.ST_Distance(Case.centroid, punto)

    condiciones = [
        Case.status == "open",
        Case.category == categoria,
        # ST_DWithin usa el indice GIST; ST_Distance solo, no.
        func.ST_DWithin(Case.centroid, punto, settings.doubtful_max_distance_m),
    ]
    # Excluir el caso propio solo si ya tiene uno. Escrito como
    # `Case.id != (reporte.case_id or Case.id)`, con case_id nulo quedaba
    # `Case.id != Case.id`, falso para todas las filas: descartaba a todos los
    # candidatos y nada se agrupaba nunca.
    if reporte.case_id is not None:
        condiciones.append(Case.id != reporte.case_id)

    filas = session.execute(
        select(Case, distancia.label("distancia")).where(*condiciones).order_by(distancia).limit(5)
    ).all()

    resultado: list[Candidato] = []
    for caso, dist in filas:
        resultado.append(
            Candidato(
                case=caso,
                distance_m=float(dist),
                hours_apart=_horas_entre(reporte, caso),
                text_similarity=_texto_contra_caso(session, reporte, caso),
                visual_distance=_visual_contra_caso(session, reporte, caso),
            )
        )
    return resultado


def _categoria_de(session: Session, reporte: Report) -> str | None:
    """La categoria **confirmada por una persona**, no la propuesta.

    Agrupar por lo que propuso el modelo sin confirmar seria dejar que el
    modelo decida agrupaciones por la puerta de atras.
    """
    from app.models import Classification

    return session.execute(
        select(Classification.final_category)
        .where(
            Classification.report_id == reporte.id,
            Classification.final_category.is_not(None),
        )
        .order_by(Classification.confirmed_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _horas_entre(reporte: Report, caso: Case) -> float:
    delta = (reporte.created_at or datetime.now(UTC)) - caso.created_at
    return abs(delta.total_seconds()) / 3600


def _texto_contra_caso(session: Session, reporte: Report, caso: Case) -> float:
    textos = (
        session.execute(select(Report.caption).where(Report.case_id == caso.id)).scalars().all()
    )
    return max((text_similarity(reporte.caption, t) for t in textos), default=0.0)


def _visual_contra_caso(session: Session, reporte: Report, caso: Case) -> int | None:
    """Bits de diferencia con la foto mas parecida del caso."""
    from app import images

    mio = session.execute(
        select(ReportPhoto.phash).where(
            ReportPhoto.report_id == reporte.id, ReportPhoto.phash.is_not(None)
        )
    ).scalar_one_or_none()
    if mio is None:
        return None

    otros = (
        session.execute(
            select(ReportPhoto.phash)
            .join(Report, Report.id == ReportPhoto.report_id)
            .where(Report.case_id == caso.id, ReportPhoto.phash.is_not(None))
        )
        .scalars()
        .all()
    )
    if not otros:
        return None
    return min(images.hamming(mio, o) for o in otros)


# --- La decision ---


def decidir(candidato: Candidato | None) -> tuple[str, str]:
    """Que hacer con el mejor candidato. Devuelve (decision, motivo).

    El motivo se escribe en español y legible porque el tablero lo muestra tal
    cual: "a 12 m del caso, misma categoria" se puede discutir; un 0,87 no.
    """
    if candidato is None:
        return "alone", "No hay ningun caso abierto de la misma categoria cerca."

    d = candidato.distance_m
    if d <= settings.group_max_distance_m:
        motivo = f"A {d:.0f} m del caso, misma categoria."
        if candidato.visual_distance is not None and (
            candidato.visual_distance <= settings.same_image_max_bits
        ):
            motivo += " Ademas la foto es la misma imagen."
        elif candidato.text_similarity >= 0.5:
            motivo += f" El texto coincide en {candidato.text_similarity:.0%}."
        return "grouped", motivo

    # Entre los dos umbrales: ni se junta ni se descarta. Se equivoca hacia el
    # error molesto —dos casos que eran uno— y nunca hacia el grave.
    motivo = (
        f"A {d:.0f} m de un caso de la misma categoria: demasiado lejos para "
        f"juntarlos automaticamente (el limite son {settings.group_max_distance_m:.0f} m) "
        f"y demasiado cerca para ignorarlo. Queda esperando revision."
    )
    if candidato.visual_distance is not None and (
        candidato.visual_distance <= settings.same_image_max_bits
    ):
        # La misma imagen a 60 m puede ser un reenvio con ubicacion propia, que
        # seria una agrupacion falsa de las graves. Se señala, no se junta.
        motivo += " La foto es la misma imagen, lo que puede ser un reenvio."
    return "doubtful", motivo


def group_report(session: Session, reporte: Report) -> str:
    """Agrupa un reporte. Devuelve el estado de agrupacion que le quedo."""
    categoria = _categoria_de(session, reporte)

    if categoria is None:
        # Sin categoria confirmada no se agrupa: seria dejar que el modelo
        # decida por la puerta de atras.
        reporte.grouping_status = "pending"
        return "pending"

    if categoria == Category.NO_ES_REPORTE.value or reporte.location is None:
        reporte.grouping_status = "alone"
        reporte.case_id = None
        return "alone"

    encontrados = candidatos(session, reporte)
    mejor = encontrados[0] if encontrados else None
    decision, motivo = decidir(mejor)

    # Los que se miraron y no se eligieron tambien quedan escritos: saber que se
    # descarto es tan util como saber que se junto.
    for otro in encontrados[1:]:
        session.add(
            GroupingEvidence(
                report_id=reporte.id,
                case_id=otro.case.id,
                decision="rejected",
                distance_m=otro.distance_m,
                category_match=True,
                hours_apart=otro.hours_apart,
                text_similarity=otro.text_similarity,
                visual_distance=otro.visual_distance,
                reason=f"Habia otro caso a {otro.distance_m:.0f} m, mas lejos que el elegido.",
                thresholds=umbrales(),
            )
        )

    if decision == "grouped" and mejor is not None:
        _unir(session, reporte, mejor.case)
        reporte.grouping_status = "grouped"
    else:
        # Tanto "alone" como "doubtful" abren su propio caso. La diferencia es
        # que el dudoso lleva anotado con quien casi se junta.
        caso = _crear_caso(session, reporte, categoria)
        _unir(session, reporte, caso)
        reporte.grouping_status = "alone" if decision == "alone" else "doubtful"

    session.add(
        GroupingEvidence(
            report_id=reporte.id,
            case_id=(mejor.case.id if mejor else reporte.case_id),
            decision=decision,
            distance_m=mejor.distance_m if mejor else None,
            category_match=True if mejor else None,
            hours_apart=mejor.hours_apart if mejor else None,
            text_similarity=mejor.text_similarity if mejor else None,
            visual_distance=mejor.visual_distance if mejor else None,
            reason=motivo,
            thresholds=umbrales(),
        )
    )

    log.info("reporte %s -> %s: %s", reporte.id, reporte.grouping_status, motivo)
    return reporte.grouping_status


def _crear_caso(session: Session, reporte: Report, categoria: str) -> Case:
    from app.models import Classification

    severidad = session.execute(
        select(Classification.final_severity)
        .where(Classification.report_id == reporte.id)
        .order_by(Classification.confirmed_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    caso = Case(category=categoria, severity=severidad, status="open", report_count=0)
    session.add(caso)
    session.flush()
    return caso


def _unir(session: Session, reporte: Report, caso: Case) -> None:
    reporte.case_id = caso.id
    session.flush()
    _recalcular(session, caso)


def _recalcular(session: Session, caso: Case) -> None:
    """Centro y cuenta del caso, a partir de sus reportes.

    El centro se recalcula porque comparar contra el promedio es mas estable que
    contra el primer reporte, que por ser el primero no tiene por que ser el mas
    exacto.
    """
    # location es geography: para promediar hay que pasar por geometry y volver.
    # ST_Centroid no acepta geography, y sin el casteo de vuelta la columna
    # rechaza el valor con "parse error - invalid geometry".
    session.execute(
        text(
            """
            UPDATE cases SET
                report_count = sub.n,
                centroid = sub.c,
                updated_at = now()
            FROM (
                SELECT count(*) AS n,
                       ST_Centroid(ST_Collect(location::geometry))::geography AS c
                FROM reports
                WHERE case_id = :cid AND location IS NOT NULL
            ) AS sub
            WHERE cases.id = :cid
            """
        ),
        {"cid": caso.id},
    )
    # El objeto en memoria quedo viejo tras el UPDATE directo.
    session.expire(caso)


def ungroup(session: Session, reporte: Report, motivo: str = "separado a mano") -> None:
    """Saca un reporte de su caso y le da uno propio.

    **Se puede deshacer** es parte del contrato: una agrupacion que no se puede
    romper obliga a confiar en el umbral, y el umbral no esta calibrado.
    """
    anterior = reporte.case_id
    categoria = _categoria_de(session, reporte)

    if categoria is None:
        reporte.case_id = None
        reporte.grouping_status = "alone"
    else:
        caso = _crear_caso(session, reporte, categoria)
        _unir(session, reporte, caso)
        reporte.grouping_status = "alone"

    if anterior:
        viejo = session.get(Case, anterior)
        if viejo is not None:
            _recalcular(session, viejo)

    session.add(
        GroupingEvidence(
            report_id=reporte.id,
            case_id=anterior,
            decision="rejected",
            reason=motivo,
            thresholds=umbrales(),
        )
    )
