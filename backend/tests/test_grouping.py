"""La agrupacion. La parte dificil.

La asimetria manda: juntar dos problemas distintos esconde uno detras de un
ticket resuelto, y eso es grave. Separar dos que eran el mismo duplica trabajo,
y eso es molesto. Estas pruebas estan escritas contra el primer error.

**Las distancias son reales.** Se construyen coordenadas separadas por metros
medidos, no por grados inventados, porque un umbral en metros probado con
grados no prueba nada.
"""

import math
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select

from app import grouping
from app.config import settings
from app.models import Case, Classification, GroupingEvidence, Report, ReportPhoto
from app.taxonomy import Category

# San Salvador. Un grado de latitud son ~111 320 m en cualquier parte; uno de
# longitud se encoge con el coseno de la latitud.
LAT0, LON0 = 13.6929, -89.2182


def desplazar(metros_norte: float, metros_este: float = 0.0) -> tuple[float, float]:
    lat = LAT0 + metros_norte / 111_320
    lon = LON0 + metros_este / (111_320 * math.cos(math.radians(LAT0)))
    return lat, lon


def crear_reporte(
    session,
    *,
    lat: float = LAT0,
    lon: float = LON0,
    categoria: str = Category.VIALIDAD.value,
    caption: str | None = None,
    usuario: str = "1",
    phash: int | None = None,
    confirmar: bool = True,
) -> Report:
    r = Report(
        channel="telegram",
        external_user_id=usuario,
        status="received",
        caption=caption,
        location=func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326),
    )
    session.add(r)
    session.flush()

    if phash is not None:
        session.add(
            ReportPhoto(
                report_id=r.id,
                channel="telegram",
                external_file_id=f"f{uuid.uuid4()}",
                status="stored",
                phash=phash,
            )
        )

    c = Classification(
        report_id=r.id,
        status="confirmed" if confirmar else "proposed",
        proposed_category=categoria,
        proposed_severity="media",
        proposed_reason="prueba",
    )
    if confirmar:
        c.final_category = categoria
        c.final_severity = "media"
        c.confirmed_at = datetime.now(UTC)
    session.add(c)
    session.commit()
    session.refresh(r)
    return r


def agrupar(session, reporte) -> str:
    estado = grouping.group_report(session, reporte)
    session.commit()
    return estado


# --- El error grave: juntar lo que no va junto ---


def test_categorias_distintas_nunca_se_juntan(session):
    """Un bache y una luminaria rota en la misma esquina son dos problemas.

    Juntarlos haria que arreglar uno cerrara los dos.
    """
    a = crear_reporte(session, categoria=Category.VIALIDAD.value)
    agrupar(session, a)

    b = crear_reporte(session, categoria=Category.ALUMBRADO.value, usuario="2")
    agrupar(session, b)

    session.refresh(a)
    session.refresh(b)
    assert a.case_id != b.case_id


def test_lejos_no_se_junta(session):
    a = crear_reporte(session)
    agrupar(session, a)

    lejos = desplazar(300)
    b = crear_reporte(session, lat=lejos[0], lon=lejos[1], usuario="2")
    assert agrupar(session, b) == "alone"

    session.refresh(a)
    session.refresh(b)
    assert a.case_id != b.case_id


def test_en_la_banda_de_duda_no_se_junta(session):
    """Lo que queda en el limite no se agrupa ni se descarta.

    Se equivoca hacia el error molesto —dos casos que eran uno— y nunca hacia
    el grave.
    """
    a = crear_reporte(session)
    agrupar(session, a)

    medio = (settings.group_max_distance_m + settings.doubtful_max_distance_m) / 2
    p = desplazar(medio)
    b = crear_reporte(session, lat=p[0], lon=p[1], usuario="2")

    assert agrupar(session, b) == "doubtful"
    session.refresh(a)
    session.refresh(b)
    # Casos distintos: el dudoso NO entra al caso ajeno.
    assert b.case_id != a.case_id


def test_la_misma_foto_lejos_no_fuerza_la_union(session):
    """Una imagen identica a 60 m puede ser un reenvio con ubicacion propia.

    Dejar que la foto mande seria una agrupacion falsa de las graves, asi que
    se señala en la evidencia pero no junta nada.
    """
    a = crear_reporte(session, phash=1234567890)
    agrupar(session, a)

    p = desplazar(60)
    b = crear_reporte(session, lat=p[0], lon=p[1], usuario="2", phash=1234567890)

    assert agrupar(session, b) == "doubtful"
    session.refresh(b)
    assert b.case_id != a.case_id

    ev = session.execute(
        select(GroupingEvidence).where(
            GroupingEvidence.report_id == b.id, GroupingEvidence.decision == "doubtful"
        )
    ).scalar_one()
    assert ev.visual_distance == 0
    assert "reenvío" in ev.reason


def test_sin_categoria_confirmada_no_se_agrupa(session):
    """Agrupar por lo que **propuso** el modelo seria dejarlo decidir de lado."""
    a = crear_reporte(session)
    agrupar(session, a)

    b = crear_reporte(session, usuario="2", confirmar=False)
    assert agrupar(session, b) == "pending"
    session.refresh(b)
    assert b.case_id is None


def test_no_es_reporte_queda_solo(session):
    r = crear_reporte(session, categoria=Category.NO_ES_REPORTE.value)
    assert agrupar(session, r) == "alone"
    session.refresh(r)
    assert r.case_id is None


def test_caso_cerrado_no_absorbe_reportes_nuevos(session):
    """Un caso cerrado es un problema arreglado; si vuelve, es otro caso."""
    a = crear_reporte(session)
    agrupar(session, a)
    session.refresh(a)
    caso = session.get(Case, a.case_id)
    caso.status = "closed"
    session.commit()

    b = crear_reporte(session, usuario="2")
    assert agrupar(session, b) == "alone"
    session.refresh(b)
    assert b.case_id != caso.id


# --- El caso que sí debe agruparse ---


def test_cerca_y_misma_categoria_se_junta(session):
    a = crear_reporte(session, caption="hueco grande")
    agrupar(session, a)

    p = desplazar(10)
    b = crear_reporte(session, lat=p[0], lon=p[1], usuario="2", caption="hueco en la calle")

    assert agrupar(session, b) == "grouped"
    session.refresh(a)
    session.refresh(b)
    assert b.case_id == a.case_id

    caso = session.get(Case, a.case_id)
    assert caso.report_count == 2


def test_tres_reportes_del_mismo_problema_son_un_caso(session):
    """Cuarenta y siete reportes en un dia son dieciocho problemas."""
    primero = crear_reporte(session)
    agrupar(session, primero)

    for i, metros in enumerate((8, 15, 22), start=2):
        p = desplazar(metros)
        r = crear_reporte(session, lat=p[0], lon=p[1], usuario=str(i))
        agrupar(session, r)

    assert session.execute(select(func.count(Case.id))).scalar() == 1
    assert session.execute(select(Case.report_count)).scalar() == 4


# --- La evidencia ---


def test_cada_agrupacion_deja_su_evidencia(session):
    """Un numero de confianza no sirve; la distancia escrita si."""
    a = crear_reporte(session)
    agrupar(session, a)
    p = desplazar(12)
    b = crear_reporte(session, lat=p[0], lon=p[1], usuario="2")
    agrupar(session, b)

    ev = session.execute(
        select(GroupingEvidence).where(
            GroupingEvidence.report_id == b.id, GroupingEvidence.decision == "grouped"
        )
    ).scalar_one()

    assert 10 <= ev.distance_m <= 14
    assert ev.category_match is True
    assert "12 m" in ev.reason or "11 m" in ev.reason or "13 m" in ev.reason
    # Con que umbrales se decidio: sin esto una agrupacion vieja no se puede
    # interpretar despues de recalibrar.
    assert ev.thresholds["group_max_distance_m"] == settings.group_max_distance_m


def test_la_evidencia_esta_en_español_y_se_entiende(session):
    a = crear_reporte(session)
    agrupar(session, a)
    p = desplazar(50)
    b = crear_reporte(session, lat=p[0], lon=p[1], usuario="2")
    agrupar(session, b)

    ev = session.execute(
        select(GroupingEvidence).where(
            GroupingEvidence.report_id == b.id, GroupingEvidence.decision == "doubtful"
        )
    ).scalar_one()

    # Un operador que no vio el sistema tiene que entender por que no se junto.
    assert "metros" in ev.reason or " m " in ev.reason
    assert "revisión" in ev.reason.lower()


# --- Deshacer ---


def test_se_puede_separar_un_reporte_de_su_caso(session):
    """Una agrupacion que no se puede romper obliga a confiar en el umbral,
    y el umbral no esta calibrado."""
    a = crear_reporte(session)
    agrupar(session, a)
    p = desplazar(10)
    b = crear_reporte(session, lat=p[0], lon=p[1], usuario="2")
    agrupar(session, b)
    session.refresh(b)
    caso_comun = b.case_id

    grouping.ungroup(session, b, "el operador vio que eran dos huecos distintos")
    session.commit()

    session.refresh(a)
    session.refresh(b)
    assert b.case_id != caso_comun
    assert b.grouping_status == "alone"
    # El caso viejo sigue existiendo con el otro reporte: separar no borra.
    assert a.case_id == caso_comun
    assert session.get(Case, caso_comun).report_count == 1


def test_separar_deja_constancia(session):
    a = crear_reporte(session)
    agrupar(session, a)
    p = desplazar(10)
    b = crear_reporte(session, lat=p[0], lon=p[1], usuario="2")
    agrupar(session, b)

    grouping.ungroup(session, b, "eran dos huecos distintos")
    session.commit()

    motivos = (
        session.execute(select(GroupingEvidence.reason).where(GroupingEvidence.report_id == b.id))
        .scalars()
        .all()
    )
    assert any("dos huecos distintos" in m for m in motivos)


# --- Semejanza textual ---


def test_texto_parecido_se_detecta(session):
    assert grouping.text_similarity("hueco grande frente al colegio", "hueco frente colegio") > 0.4


def test_palabras_vacias_no_inflan_el_parecido(session):
    """ "Hay un hueco aqui" y "hay una fuga aqui" no se parecen."""
    assert grouping.text_similarity("hay un hueco aqui urgente", "hay una fuga aqui urgente") < 0.3


def test_texto_ausente_no_suma(session):
    assert grouping.text_similarity(None, "hueco") == 0.0
    assert grouping.text_similarity("", "") == 0.0


def test_la_severidad_del_caso_es_la_peor_de_sus_reportes(session):
    """Si alguien añade "ya se cayo una moto", el caso es urgente.

    La cola ordena por severidad; dejar la del primer reporte esconderia lo que
    hay que atender antes.
    """
    from app.models import Classification

    leve = crear_reporte(session)
    session.execute(
        Classification.__table__.update()
        .where(Classification.report_id == leve.id)
        .values(final_severity="baja")
    )
    session.commit()
    agrupar(session, leve)
    session.refresh(leve)
    caso = session.get(Case, leve.case_id)
    assert caso.severity == "baja"

    p = desplazar(10)
    grave = crear_reporte(session, lat=p[0], lon=p[1], usuario="2")
    agrupar(session, grave)

    session.refresh(caso)
    assert caso.severity == "media", "la severidad sube con el reporte mas grave"


def test_la_severidad_no_baja_al_entrar_uno_leve(session):
    """Un reporte leve no rebaja un caso urgente."""
    from app.models import Classification

    grave = crear_reporte(session)
    session.execute(
        Classification.__table__.update()
        .where(Classification.report_id == grave.id)
        .values(final_severity="alta")
    )
    session.commit()
    agrupar(session, grave)
    session.refresh(grave)
    caso = session.get(Case, grave.case_id)
    assert caso.severity == "alta"

    p = desplazar(10)
    leve = crear_reporte(session, lat=p[0], lon=p[1], usuario="2")
    session.execute(
        Classification.__table__.update()
        .where(Classification.report_id == leve.id)
        .values(final_severity="baja")
    )
    session.commit()
    agrupar(session, leve)

    session.refresh(caso)
    assert caso.severity == "alta"


def test_los_motivos_van_en_español_correcto(session):
    """Lo que lee un operador no puede estar sin tildes.

    Los comentarios del codigo van sin ellas por comodidad; estos textos no: se
    muestran tal cual en el tablero, y "categoria" sin tilde es una falta.
    """
    a = crear_reporte(session)
    agrupar(session, a)
    p = desplazar(12)
    b = crear_reporte(session, lat=p[0], lon=p[1], usuario="2")
    agrupar(session, b)

    motivos = (
        session.execute(select(GroupingEvidence.reason).where(GroupingEvidence.report_id == b.id))
        .scalars()
        .all()
    )
    texto = " ".join(motivos)

    # Palabras que aparecen en estos motivos y llevan tilde.
    for palabra in ("categoría",):
        assert palabra in texto, f"falta la tilde en {palabra!r}: {texto}"
    for sin_tilde in ("categoria", "revision", "reenvio", "automaticamente", "limite"):
        assert sin_tilde not in texto, f"{sin_tilde!r} aparece sin tilde: {texto}"
