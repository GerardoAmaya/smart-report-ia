"""El comprobador de la agrupacion.

Lo primero que se comprueba es que **no use el codigo que comprueba**. Lo demas
es aritmetica, pero esa aritmetica tiene que separar los dos errores y nunca
promediarlos.
"""

import ast
import json
from pathlib import Path

import pytest

from app import grouping_eval

MODULO = Path(grouping_eval.__file__)


def test_el_comprobador_no_importa_el_agrupador():
    """La regla de PLAN.md, hecha prueba.

    Medir con la misma logica que decide mide consistencia consigo misma, no
    acierto: si el agrupador tiene un error de concepto, un comprobador que lo
    reutilice repetiria el error y daria todo por bueno.
    """
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    importados: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados.update(a.name for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            importados.add(nodo.module)

    prohibidos = {"app.grouping", "app.confirm", "app.classify"}
    assert not (importados & prohibidos), f"el comprobador importa {importados & prohibidos}"


def test_acuerdo_perfecto():
    verdad = {"a": "v1", "b": "v1", "c": "v2"}
    sistema = {"a": "c1", "b": "c1", "c": "c2"}
    t = grouping_eval.comparar(verdad, sistema)

    assert t.falsos_positivos == 0
    assert t.falsos_negativos == 0
    assert t.verdaderos_positivos == 1


def test_el_error_grave_se_cuenta_aparte():
    """El sistema junto dos que no iban juntos."""
    verdad = {"a": "v1", "b": "v2"}
    sistema = {"a": "c1", "b": "c1"}
    t = grouping_eval.comparar(verdad, sistema)

    assert t.falsos_positivos == 1
    assert t.falsos_negativos == 0
    assert t.tasa_falsos_positivos == 1.0
    # La otra tasa no se contamina: son medidas distintas de errores distintos.
    assert t.tasa_falsos_negativos == 0.0


def test_el_error_molesto_se_cuenta_aparte():
    """Iban juntos y el sistema los separo."""
    verdad = {"a": "v1", "b": "v1"}
    sistema = {"a": "c1", "b": "c2"}
    t = grouping_eval.comparar(verdad, sistema)

    assert t.falsos_negativos == 1
    assert t.falsos_positivos == 0
    assert t.tasa_falsos_negativos == 1.0
    assert t.tasa_falsos_positivos == 0.0


def test_los_dos_errores_no_se_promedian_nunca():
    """Un sistema que junta todo y otro que no junta nada son muy distintos.

    Un promedio los daria parecidos, y uno de los dos esconde problemas.
    """
    verdad = {"a": "v1", "b": "v1", "c": "v2", "d": "v2"}

    junta_todo = dict.fromkeys("abcd", "c1")
    separa_todo = {k: f"c{i}" for i, k in enumerate("abcd")}

    t_junta = grouping_eval.comparar(verdad, junta_todo)
    t_separa = grouping_eval.comparar(verdad, separa_todo)

    # El que junta todo comete el error grave; el que separa todo, el molesto.
    assert t_junta.falsos_positivos > 0 and t_junta.falsos_negativos == 0
    assert t_separa.falsos_negativos > 0 and t_separa.falsos_positivos == 0


def test_solo_se_juzgan_los_que_estan_en_las_dos_partes():
    """Contar los que la verdad no menciona inflaria el resultado."""
    verdad = {"a": "v1", "b": "v1"}
    sistema = {"a": "c1", "b": "c1", "z": "c9"}
    t = grouping_eval.comparar(verdad, sistema)

    assert t.pares_totales == 1


def test_un_reporte_sin_caso_cuenta_como_grupo_propio(session):

    from sqlalchemy import func

    from app.models import Report

    r = Report(
        channel="telegram",
        external_user_id="1",
        status="received",
        location=func.ST_SetSRID(func.ST_MakePoint(-89.2, 13.6), 4326),
    )
    session.add(r)
    session.commit()

    sistema = grouping_eval.agrupacion_del_sistema(session, [str(r.id)])
    assert sistema[str(r.id)].startswith("solo-")


def test_carga_el_archivo_de_verdad(tmp_path):
    ruta = tmp_path / "verdad.json"
    ruta.write_text(json.dumps([["a", "b"], ["c"]]), encoding="utf-8")

    verdad = grouping_eval.cargar_verdad(ruta)
    assert verdad["a"] == verdad["b"]
    assert verdad["c"] != verdad["a"]


def test_archivo_mal_formado_falla_claro(tmp_path):
    ruta = tmp_path / "malo.json"
    ruta.write_text('{"no": "es una lista"}', encoding="utf-8")

    with pytest.raises(ValueError, match="lista de listas"):
        grouping_eval.cargar_verdad(ruta)


def test_el_informe_avisa_con_pocas_muestras():
    t = grouping_eval.comparar({"a": "v1", "b": "v1"}, {"a": "c1", "b": "c1"})
    texto = grouping_eval.formato(t, muestras=2)

    assert "doscientos" in texto
    assert "indicativas" in texto
    # Y deja claro cual de los dos errores manda.
    assert "GRAVE" in texto
