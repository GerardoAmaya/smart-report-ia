"""Comprobador de la agrupacion.

**No importa `app.grouping` y no debe hacerlo nunca.** Medir con la misma logica
que decide mide consistencia consigo misma, no acierto: si el agrupador tiene un
error de concepto, un comprobador que lo reutilice repetira el error y dara todo
por bueno. Aca solo se leen dos cosas —como quedaron agrupados los reportes y
como deberian haber quedado— y se cuentan las diferencias. Hay una prueba que
falla si alguien agrega el import.

**Las dos tasas van por separado, nunca promediadas.** La asimetria es el centro
de esta fase:

- **Falsos positivos** — junto dos problemas distintos. La cuadrilla arregla uno,
  cierra los dos, y el otro queda escondido detras de un ticket resuelto. Nadie
  se entera nunca. **Este es el error grave y es contra el que se calibra.**
- **Falsos negativos** — separo dos reportes del mismo problema. Se manda a dos
  cuadrillas al mismo sitio. Es trabajo duplicado: molesto, visible, y se
  arregla solo cuando alguien lo nota.

Un promedio de las dos escondería exactamente lo que hay que mirar.

La comparacion es **por pares**: para cada par de reportes, la verdad dice si van
juntos y el sistema dice si los junto. Contar casos enteros premiaria partir todo
en pedacitos.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Report


@dataclass(frozen=True)
class Tasas:
    pares_totales: int
    # La verdad dice juntos, el sistema tambien.
    verdaderos_positivos: int
    # El sistema los junto y no iban juntos. EL ERROR GRAVE.
    falsos_positivos: int
    # Iban juntos y el sistema los separo. El error molesto.
    falsos_negativos: int
    pares_juntos_en_verdad: int
    pares_juntos_por_el_sistema: int

    @property
    def tasa_falsos_positivos(self) -> float:
        """De lo que el sistema junto, cuanto no debia juntarse."""
        if self.pares_juntos_por_el_sistema == 0:
            return 0.0
        return self.falsos_positivos / self.pares_juntos_por_el_sistema

    @property
    def tasa_falsos_negativos(self) -> float:
        """De lo que debia juntarse, cuanto se quedo separado."""
        if self.pares_juntos_en_verdad == 0:
            return 0.0
        return self.falsos_negativos / self.pares_juntos_en_verdad


def cargar_verdad(ruta: Path) -> dict[str, str]:
    """Lee la agrupacion hecha a mano.

    Formato: una lista de listas, cada una con los identificadores de reporte
    que son el mismo problema. Los que no aparezcan se consideran solos.

        [["id1", "id2", "id3"], ["id4", "id5"]]
    """
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    if not isinstance(datos, list):
        raise ValueError("el archivo tiene que ser una lista de listas")

    etiqueta_de: dict[str, str] = {}
    for i, grupo in enumerate(datos):
        for report_id in grupo:
            etiqueta_de[str(report_id)] = f"verdad-{i}"
    return etiqueta_de


def agrupacion_del_sistema(session: Session, ids: list[str]) -> dict[str, str]:
    """Como quedaron agrupados, leido de la base y nada mas.

    Un reporte sin caso cuenta como grupo propio: esta solo, que es una
    respuesta tan valida como cualquier otra.
    """
    filas = session.execute(select(Report.id, Report.case_id).where(Report.id.in_(ids))).all()
    return {str(rid): (str(cid) if cid else f"solo-{rid}") for rid, cid in filas}


def comparar(verdad: dict[str, str], sistema: dict[str, str]) -> Tasas:
    """Cuenta las diferencias par a par.

    Solo se miran los reportes que estan en las dos partes: los que la verdad no
    menciona no se pueden juzgar, y contarlos como aciertos inflaria el
    resultado.
    """
    ids = sorted(set(verdad) & set(sistema))

    vp = fp = fn = 0
    juntos_verdad = juntos_sistema = 0

    for a, b in combinations(ids, 2):
        misma_verdad = verdad[a] == verdad[b]
        mismo_sistema = sistema[a] == sistema[b]

        juntos_verdad += int(misma_verdad)
        juntos_sistema += int(mismo_sistema)

        if misma_verdad and mismo_sistema:
            vp += 1
        elif mismo_sistema and not misma_verdad:
            fp += 1
        elif misma_verdad and not mismo_sistema:
            fn += 1

    return Tasas(
        pares_totales=len(ids) * (len(ids) - 1) // 2,
        verdaderos_positivos=vp,
        falsos_positivos=fp,
        falsos_negativos=fn,
        pares_juntos_en_verdad=juntos_verdad,
        pares_juntos_por_el_sistema=juntos_sistema,
    )


def formato(tasas: Tasas, muestras: int) -> str:
    lineas: list[str] = []
    ancho = 66
    lineas.append("=" * ancho)
    lineas.append("AGRUPACION, COMPARADA CONTRA LA VERDAD HECHA A MANO")
    lineas.append("=" * ancho)
    lineas.append(f"  reportes comparados       {muestras:>8}")
    lineas.append(f"  pares evaluados           {tasas.pares_totales:>8}")
    lineas.append("")
    lineas.append("  EL ERROR GRAVE — juntar dos problemas distintos")
    lineas.append("  Esconde uno detras de un ticket resuelto. Nadie se entera.")
    lineas.append(
        f"    agrupaciones incorrectas  {tasas.falsos_positivos:>8}"
        f"   ({tasas.tasa_falsos_positivos:.1%} de lo que junto)"
    )
    lineas.append("")
    lineas.append("  El error molesto — separar reportes del mismo problema")
    lineas.append("  Manda dos cuadrillas al mismo sitio. Se ve y se corrige.")
    lineas.append(
        f"    agrupaciones perdidas     {tasas.falsos_negativos:>8}"
        f"   ({tasas.tasa_falsos_negativos:.1%} de lo que debia juntar)"
    )
    lineas.append("")
    lineas.append(f"  aciertos de union         {tasas.verdaderos_positivos:>8}")

    if muestras < 30:
        lineas.append("")
        lineas.append(f"  AVISO: {muestras} reportes. PLAN.md pide doscientos.")
        lineas.append("  Con esta muestra las tasas son indicativas, no una medida.")

    lineas.append("")
    lineas.append("  El umbral se calibra contra el error grave, no contra el promedio.")
    return "\n".join(lineas)


def main() -> int:
    import sys

    from app.db import SessionLocal

    if len(sys.argv) < 2:
        print("uso: python -m app.grouping_eval <archivo-de-verdad.json>")
        print()
        print("Formato: lista de listas con los ids de reporte de cada problema.")
        print('  [["id1", "id2"], ["id3"]]')
        return 1

    verdad = cargar_verdad(Path(sys.argv[1]))
    with SessionLocal() as session:
        sistema = agrupacion_del_sistema(session, list(verdad))

    comunes = set(verdad) & set(sistema)
    if not comunes:
        print("Ninguno de esos reportes esta en la base.")
        return 1

    print(formato(comparar(verdad, sistema), len(comunes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
