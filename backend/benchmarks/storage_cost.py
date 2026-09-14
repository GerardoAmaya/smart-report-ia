"""Verificacion de la fase 2: cien fotos subidas y servidas, con su costo.

Dos mediciones distintas, y separarlas importa:

**El rendimiento** —cuanto tarda generar una miniatura, subir, servir— se mide
con cien fotos sinteticas. Ahi el contenido no cambia el resultado.

**El costo por foto** sale de las fotos **reales** que haya en la base, nunca de
las sinteticas. Se intento al reves y el numero salio un 28,5 por ciento bajo:
las sinteticas se calibraron por tamano del original, pero su miniatura pesaba
2,6 veces menos que la de una foto de verdad, porque el detalle real no
comprime a 320px como una textura generada. Un costo medido sobre fotos
inventadas no es el costo.

Con pocas fotos reales el numero es provisional, y se dice cuantas son.
"""

from __future__ import annotations

import statistics
import time
import urllib.request
import uuid

from sqlalchemy import select

from app import images, storage
from app.db import SessionLocal
from app.models import ReportPhoto

# Las sinteticas calibradas viven con las pruebas porque es ahi donde se
# comprueba que sigan pareciendose a una foto real; aca solo se usan.
from tests.imagenes import foto_sintetica

CUANTAS = 100

# Precios publicados de Cloudflare R2, clase estandar.
R2_USD_POR_GB_MES = 0.015
R2_USD_POR_MILLON_CLASE_A = 4.50  # escrituras
R2_USD_POR_MILLON_CLASE_B = 0.36  # lecturas
R2_GRATIS_GB = 10

# Veces que se mira una foto en su vida: la cola, el detalle, el cierre.
LECTURAS_POR_FOTO = 20


def medir_rendimiento() -> dict[str, list[float]]:
    """Cien fotos sinteticas: cuanto tarda el camino completo."""
    print(f"Subiendo y sirviendo {CUANTAS} fotos sinteticas…\n")

    claves: list[tuple[str, str]] = []
    ms_miniatura: list[float] = []
    ms_subida: list[float] = []

    for i in range(CUANTAS):
        datos = foto_sintetica(semilla=1000 + i)
        rid, pid = uuid.uuid4(), uuid.uuid4()

        t0 = time.perf_counter()
        mini = images.thumbnail(datos)
        ms_miniatura.append((time.perf_counter() - t0) * 1000)

        t0 = time.perf_counter()
        k = storage.build_key(rid, pid, kind="original", ext="jpg")
        km = storage.build_key(rid, pid, kind="thumb", ext="jpg")
        storage.put(k, datos, "image/jpeg")
        storage.put(km, mini, "image/jpeg")
        ms_subida.append((time.perf_counter() - t0) * 1000)

        claves.append((k, km))
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{CUANTAS}")

    ms_servir: list[float] = []
    servidas = 0
    for k, _ in claves:
        url = storage.presigned_url(k, expires_seconds=300)
        t0 = time.perf_counter()
        with urllib.request.urlopen(url) as r:
            cuerpo = r.read()
        ms_servir.append((time.perf_counter() - t0) * 1000)
        servidas += 1 if cuerpo else 0

    for k, km in claves:
        storage.delete(k)
        storage.delete(km)

    return {
        "miniatura": ms_miniatura,
        "subida": ms_subida,
        "servir": ms_servir,
        "servidas": [servidas],
    }


def medir_costo() -> tuple[int, float, float] | None:
    """Bytes por foto a partir de las fotos reales guardadas."""
    with SessionLocal() as session:
        filas = list(
            session.execute(
                select(ReportPhoto.bytes, ReportPhoto.thumbnail_bytes).where(
                    ReportPhoto.status == "stored",
                    ReportPhoto.bytes.is_not(None),
                    ReportPhoto.thumbnail_bytes.is_not(None),
                )
            ).all()
        )

    if not filas:
        return None

    originales = [f[0] for f in filas]
    miniaturas = [f[1] for f in filas]
    return len(filas), statistics.mean(originales), statistics.mean(miniaturas)


def main() -> int:
    tiempos = medir_rendimiento()

    print(f"\n{'=' * 64}")
    print("RENDIMIENTO  (100 fotos sinteticas)")
    print(f"{'=' * 64}")
    for nombre, clave in (
        ("miniatura", "miniatura"),
        ("subida (2 objetos)", "subida"),
        ("servir prefirmada", "servir"),
    ):
        s = sorted(tiempos[clave])
        print(
            f"  {nombre:<20} mediana {statistics.median(s):>7.1f} ms"
            f"   p95 {s[int(len(s) * 0.95)]:>7.1f} ms"
        )
    print(f"  servidas correctamente  {tiempos['servidas'][0]}/{CUANTAS}")

    costo = medir_costo()
    print(f"\n{'=' * 64}")
    print("COSTO POR FOTO  (fotos reales, Cloudflare R2)")
    print(f"{'=' * 64}")

    if costo is None:
        print("  Todavia no hay fotos reales guardadas.")
        print("  El costo NO se estima con sinteticas: se midio que salen 28,5% bajo.")
        return 0

    n, media_orig, media_mini = costo
    por_foto = media_orig + media_mini

    print(f"  muestras reales          {n:>12}")
    print(f"  original, media          {media_orig:>12,.0f} bytes")
    print(
        f"  miniatura, media         {media_mini:>12,.0f} bytes"
        f"   ({media_mini / media_orig:.1%} del original)"
    )
    print(f"  por foto                 {por_foto:>12,.0f} bytes")

    gb = por_foto / 1024**3
    almacenamiento = gb * R2_USD_POR_GB_MES
    escrituras = 2 / 1_000_000 * R2_USD_POR_MILLON_CLASE_A
    lecturas = LECTURAS_POR_FOTO / 1_000_000 * R2_USD_POR_MILLON_CLASE_B

    print()
    print(f"  almacenamiento     USD {almacenamiento:.8f} por mes")
    print(f"  escrituras (2)     USD {escrituras:.8f} una vez")
    print(f"  lecturas ({LECTURAS_POR_FOTO})      USD {lecturas:.8f} estimado")
    print("  egreso             USD 0.00000000  R2 no cobra egreso")
    print(f"  {'-' * 60}")
    print(f"  primer mes         USD {almacenamiento + escrituras + lecturas:.8f}")
    print(f"  meses siguientes   USD {almacenamiento:.8f}")

    caben = int(R2_GRATIS_GB * 1024**3 / por_foto)
    print(f"\n  Las {R2_GRATIS_GB} GB gratuitas de R2 cubren {caben:,} fotos.")
    print(f"  A 50 reportes diarios con una foto: {caben / 50 / 365:.1f} años.")

    if n < 30:
        print(f"\n  AVISO: {n} muestras. El numero es provisional y se afina solo")
        print("  a medida que entren reportes reales. Volver a correrlo entonces.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
