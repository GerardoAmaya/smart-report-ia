"""El flujo de cambios del tablero.

Lo que se comprueba aqui no es que lleguen los avisos —eso se ve a simple
vista— sino que el flujo **siga vivo cuando no pasa nada**. Un tablero en vivo
que se muere en silencio cada veinte segundos parece funcionar: el navegador
reconecta solo, y lo unico que se pierde son los cambios que ocurren en el
hueco, que es justo lo que nadie va a notar hasta que importe.
"""

import asyncio
import json

import psycopg

from app import stream
from app.config import settings


class PeticionFalsa:
    """Lo unico que `_eventos` le pide a la peticion."""

    def __init__(self) -> None:
        self.cortada = False

    async def is_disconnected(self) -> bool:
        return self.cortada


async def _avisar() -> None:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    conn = await psycopg.AsyncConnection.connect(url, autocommit=True)
    try:
        await conn.execute(
            "SELECT pg_notify(%s, %s)",
            (stream.CANAL, json.dumps({"tabla": "cases", "id": "prueba"})),
        )
    finally:
        await conn.close()


def _leer(cuantos: int, tras_el_primero=None) -> list[str]:
    """Saca `cuantos` trozos del flujo, corriendo el bucle de eventos a mano."""

    async def correr() -> list[str]:
        generador = stream._eventos(PeticionFalsa())
        trozos: list[str] = []
        try:
            for indice in range(cuantos):
                trozos.append(await asyncio.wait_for(generador.__anext__(), timeout=10))
                if indice == 0 and tras_el_primero is not None:
                    await tras_el_primero()
        finally:
            await generador.aclose()
        return trozos

    return asyncio.run(correr())


def test_el_latido_no_mata_el_flujo(monkeypatch):
    """El bug: el primer latido dejaba el flujo muerto.

    La espera se hacia con `asyncio.wait_for` sobre el generador de avisos de
    psycopg. Al vencer el plazo, `wait_for` **cancela** lo que estaba
    esperando, y eso cierra el generador: el siguiente intento de leer levanta
    `StopAsyncIteration`, que el `except Exception` registraba como "el flujo de
    cambios se corto". Cada veinte segundos, con cada tablero abierto.
    """
    monkeypatch.setattr(stream, "LATIDO_SEGUNDOS", 0.3)

    trozos = _leer(4)

    assert trozos[0].startswith("event: abierto")
    # Tres latidos seguidos sin que el flujo se caiga.
    assert trozos[1:] == [": latido\n\n"] * 3


def test_un_aviso_llega_despues_de_un_latido(monkeypatch):
    """Y lo que importa de verdad: que tras callar, siga escuchando.

    Un flujo que aguanta los latidos pero ya no oye a Postgres seria peor que
    el fallo original, porque no se nota ni en los registros.
    """
    monkeypatch.setattr(stream, "LATIDO_SEGUNDOS", 0.3)

    async def avisar_tarde() -> None:
        # Despues del primer latido, para que el aviso entre en una espera ya
        # vencida una vez.
        await asyncio.sleep(0.5)
        await _avisar()

    trozos = _leer(5, tras_el_primero=avisar_tarde)

    cambios = [t for t in trozos if t.startswith("event: cambio")]
    assert cambios, f"ningun cambio en {trozos}"
    assert json.loads(cambios[0].split("data: ", 1)[1])["tabla"] == "cases"
