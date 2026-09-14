"""Exactitud de la clasificacion, medida con lo que ya se confirmo.

No hace falta etiquetar nada aparte ni gastar un centavo mas: **cada
confirmacion en el bot es una etiqueta**. Cuando alguien toca "si, es correcto",
`final_category` queda igual a `proposed_category`; cuando corrige, queda
distinta. Esa diferencia es acierto medido sobre uso real, que es mejor dato que
un conjunto etiquetado en un escritorio.

Lo que no da gratis es el **balance** del conjunto: si nadie reporta luminarias,
no habra filas de alumbrado por mucho que se espere. Para eso siguen haciendo
falta las doscientas de PLAN.md, y este mismo codigo las mide cuando existan.

**El comprobador no usa el codigo que comprueba.** Aca no se llama a `classify`
ni se re-clasifica nada: se leen dos columnas y se cuentan. Medir con la logica
que decide mide consistencia consigo misma, no acierto.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Classification
from app.taxonomy import Category

# Debajo de esto una tasa por categoria es ruido, no medida.
MINIMO_POR_CATEGORIA = 5


@dataclass
class Resultado:
    total: int = 0
    aciertos: int = 0
    # confusion[real][propuesta] = cuantas veces
    confusion: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    por_modelo: dict[str, tuple[int, int]] = field(default_factory=dict)
    costo_total: Decimal = Decimal(0)

    @property
    def exactitud(self) -> float:
        return self.aciertos / self.total if self.total else 0.0

    def exactitud_de(self, categoria: str) -> tuple[int, int]:
        """(aciertos, total) para las que de verdad eran esa categoria."""
        fila = self.confusion.get(categoria)
        if not fila:
            return 0, 0
        return fila.get(categoria, 0), sum(fila.values())


def labeled(session: Session) -> list[Classification]:
    """Las clasificaciones que alguien confirmo o corrigio."""
    return list(
        session.execute(
            select(Classification).where(
                Classification.confirmed_at.is_not(None),
                Classification.proposed_category.is_not(None),
                Classification.final_category.is_not(None),
            )
        )
        .scalars()
        .all()
    )


def evaluate(session: Session, model: str | None = None) -> Resultado:
    filas = labeled(session)
    if model:
        filas = [f for f in filas if f.model == model]

    resultado = Resultado()
    aciertos_modelo: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    for fila in filas:
        real = fila.final_category
        propuesta = fila.proposed_category
        acerto = real == propuesta

        resultado.total += 1
        resultado.aciertos += int(acerto)
        resultado.confusion[real][propuesta] += 1
        if fila.cost_usd:
            resultado.costo_total += fila.cost_usd

        if fila.model:
            aciertos_modelo[fila.model][0] += int(acerto)
            aciertos_modelo[fila.model][1] += 1

    resultado.por_modelo = {m: (a, t) for m, (a, t) in aciertos_modelo.items()}
    return resultado


def formato(resultado: Resultado) -> str:
    """El informe. Dice cuando no hay datos suficientes en vez de inventar."""
    lineas: list[str] = []
    ancho = 64
    lineas.append("=" * ancho)
    lineas.append("EXACTITUD DE CLASIFICACION")
    lineas.append("=" * ancho)

    if resultado.total == 0:
        lineas.append("")
        lineas.append("  Todavia nadie confirmo ninguna clasificacion.")
        lineas.append("  Cada confirmacion en el bot genera una etiqueta, sin costo.")
        return "\n".join(lineas)

    lineas.append(f"  etiquetas (confirmaciones)  {resultado.total:>6}")
    lineas.append(f"  exactitud global            {resultado.exactitud:>6.1%}")
    if resultado.costo_total:
        lineas.append(f"  costo de clasificarlas      USD {resultado.costo_total:.4f}")

    if resultado.por_modelo:
        lineas.append("")
        lineas.append("  Por modelo:")
        for modelo, (aciertos, total) in sorted(resultado.por_modelo.items()):
            tasa = aciertos / total if total else 0
            aviso = "  (pocas)" if total < MINIMO_POR_CATEGORIA else ""
            lineas.append(f"    {modelo:<22} {tasa:>6.1%}  n={total}{aviso}")

    lineas.append("")
    lineas.append("  Por categoria (de las que de verdad eran esa):")
    hay_suficiente = False
    for categoria in Category:
        aciertos, total = resultado.exactitud_de(categoria.value)
        if total == 0:
            continue
        tasa = aciertos / total
        if total >= MINIMO_POR_CATEGORIA:
            hay_suficiente = True
            aviso = ""
        else:
            aviso = "  (pocas para concluir)"
        lineas.append(f"    {categoria.value:<22} {tasa:>6.1%}  n={total}{aviso}")

    if not hay_suficiente:
        lineas.append("")
        lineas.append(f"  Ninguna categoria llega a {MINIMO_POR_CATEGORIA} muestras.")
        lineas.append("  Las tasas de arriba son indicativas, no una medida.")

    # La matriz importa mas que el promedio: interesa cuales se confunden entre
    # si, no cuantas acerto en total.
    confundidas = [
        (real, propuesta, cuantas)
        for real, fila in resultado.confusion.items()
        for propuesta, cuantas in fila.items()
        if real != propuesta
    ]
    lineas.append("")
    if confundidas:
        lineas.append("  Confusiones (era -> propuso):")
        for real, propuesta, cuantas in sorted(confundidas, key=lambda x: -x[2]):
            lineas.append(f"    {real:<22} -> {propuesta:<22} {cuantas:>3}")
    else:
        lineas.append("  Sin confusiones todavia.")

    return "\n".join(lineas)


def main() -> int:
    from app.db import SessionLocal

    with SessionLocal() as session:
        print(formato(evaluate(session)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
