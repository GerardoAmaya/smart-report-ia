"""Que ningun archivo del backend lleve una credencial con forma real.

Existe por un fallo real: el token del bot estuvo en `test_logging.py`, copiado
de un log, con el nombre `TOKEN_FALSO`. El repositorio es publico, y un token de
Telegram en GitHub lo encuentran rastreadores automaticos en minutos.

Recorre la carpeta y no `git ls-files` porque dentro del contenedor solo esta
montado `backend/`, sin `.git`. El resto del repositorio lo cubre un paso de CI.
"""

import re
from pathlib import Path

# Token de bot: id numerico, dos puntos, 35 caracteres. Clave de Anthropic.
_PATRONES = {
    "token de Telegram": re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),
    "clave de Anthropic": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
}

_RAIZ = Path(__file__).resolve().parents[1]
_SE_SALTA = {".pytest_cache", ".ruff_cache", "__pycache__", ".venv", "node_modules"}
_EXTENSIONES = {".py", ".sh", ".ini", ".toml", ".cfg", ".txt", ".md", ".json", ".yml", ".yaml"}


def _archivos():
    for ruta in _RAIZ.rglob("*"):
        if any(parte in _SE_SALTA for parte in ruta.parts):
            continue
        # Los .env no van al repositorio; si alguno cae aqui, no es esta prueba
        # la que debe leerlo.
        if ruta.name.startswith(".env"):
            continue
        if ruta.is_file() and (ruta.suffix in _EXTENSIONES or ruta.name == "Dockerfile"):
            yield ruta


def test_ningun_archivo_lleva_credenciales():
    hallazgos = []
    for ruta in _archivos():
        texto = ruta.read_text(encoding="utf-8", errors="ignore")
        for nombre, patron in _PATRONES.items():
            if patron.search(texto):
                # Se nombra el archivo, nunca el valor: el mensaje de una prueba
                # fallida acaba en los registros de CI, que tambien son publicos.
                hallazgos.append(f"{ruta.relative_to(_RAIZ)}: {nombre}")
    assert not hallazgos, "Credenciales en el codigo:\n" + "\n".join(hallazgos)


def test_el_patron_reconoce_un_token():
    """Sin esto, un patron roto haria pasar la prueba de arriba siempre."""
    inventado = "123456789:" + "A" * 35
    assert _PATRONES["token de Telegram"].search(inventado)
