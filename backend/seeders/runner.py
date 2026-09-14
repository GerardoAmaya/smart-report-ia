"""Corredor de seeders.

Los ejecuta en orden por nombre de archivo. Cada seeder tiene que ser
idempotente: esto se corre en cada despliegue y correrlo dos veces no puede
duplicar nada ni pisar lo que un operador haya cambiado a mano.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from sqlalchemy.orm import Session

SEEDERS_DIR = Path(__file__).resolve().parent


def discover() -> list[Path]:
    """Archivos NNNN_nombre.py, en orden. El numero es el orden, no un adorno."""
    return sorted(p for p in SEEDERS_DIR.glob("[0-9][0-9][0-9][0-9]_*.py"))


def _load(path: Path):
    # Los nombres empiezan con digitos, asi que no son importables por nombre.
    spec = importlib.util.spec_from_file_location(f"seeders.{path.stem}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"no se pudo cargar el seeder {path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_all(session: Session) -> list[str]:
    """Corre todos los seeders en una transaccion por seeder.

    Una transaccion por seeder y no una global: si el tercero falla, los dos
    primeros quedan aplicados y el arreglo es corregir el tercero, no repetir
    todo.
    """
    aplicados: list[str] = []
    for path in discover():
        module = _load(path)
        seed = getattr(module, "seed", None)
        if seed is None:
            raise RuntimeError(f"{path.name} no define seed(session)")
        seed(session)
        session.commit()
        aplicados.append(path.stem)
    return aplicados


def main() -> int:
    from app.db import engine

    with Session(engine) as session:
        aplicados = run_all(session)
    for nombre in aplicados:
        print(f"seeder aplicado: {nombre}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
