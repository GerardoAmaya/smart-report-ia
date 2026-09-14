"""Un Telegram falso para las pruebas extremo a extremo.

Existe para que el recorrido completo se pueda probar **sin una cuenta de
Telegram ni fotos reales**: implementa lo minimo que el trabajador usa —`getMe`,
`getFile`, la descarga del archivo y `sendMessage`— y devuelve una foto
generada.

No es una simulacion del sistema: el codigo que corre es el mismo de produccion,
incluido el cliente de Telegram. Lo unico que cambia es a que servidor le habla,
que es una variable de entorno.
"""

from __future__ import annotations

import io
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

PUERTO = int(sys.argv[1]) if len(sys.argv) > 1 else 8099

# Lo que se le mandaria a la persona. Las pruebas lo consultan para comprobar
# que el aviso de vuelta salio de verdad.
ENVIADOS: list[dict] = []


def _foto(semilla: int = 0) -> bytes:
    img = Image.new("RGB", (721, 1280))
    pix = img.load()
    for y in range(0, 1280, 8):
        for x in range(0, 721, 8):
            c = ((x + y + semilla) % 200 + 40, (x * 3 + semilla) % 200 + 40, (y * 2) % 200 + 40)
            for dy in range(8):
                for dx in range(8):
                    if x + dx < 721 and y + dy < 1280:
                        pix[x + dx, y + dy] = c
    salida = io.BytesIO()
    img.save(salida, format="JPEG", quality=85)
    return salida.getvalue()


FOTO = _foto()


def _interpretar(crudo: str) -> dict:
    """Saca de la peticion a quien va, que dice y que botones lleva.

    PTB manda JSON o formulario segun el caso; se prueban los dos y se devuelve
    lo que se entienda. Los botones se extraen aparte porque son lo unico que
    una prueba necesita para pulsar como pulsa una persona.
    """
    datos: dict = {}
    try:
        datos = json.loads(crudo)
    except json.JSONDecodeError:
        from urllib.parse import parse_qs

        datos = {k: v[0] for k, v in parse_qs(crudo).items()}

    markup = datos.get("reply_markup")
    if isinstance(markup, str):
        try:
            markup = json.loads(markup)
        except json.JSONDecodeError:
            markup = None

    botones: list[dict] = []
    if isinstance(markup, dict):
        for fila in markup.get("inline_keyboard", []):
            for b in fila:
                if b.get("callback_data"):
                    botones.append({"texto": b.get("text"), "data": b["callback_data"]})

    return {
        "chat_id": str(datos.get("chat_id", "")),
        "texto": datos.get("text", ""),
        "botones": botones,
    }


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silencio: el ruido tapa el fallo real
        pass

    def _json(self, resultado, codigo=200):
        cuerpo = json.dumps({"ok": True, "result": resultado}).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        self._responder()

    def do_POST(self):
        self._responder()

    def _responder(self):
        ruta = self.path.split("?")[0]

        # Descarga del archivo: /file/bot<token>/<ruta>
        if "/file/bot" in ruta:
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(FOTO)))
            self.end_headers()
            self.wfile.write(FOTO)
            return

        metodo = ruta.rsplit("/", 1)[-1]

        if metodo == "getMe":
            return self._json({"id": 1, "is_bot": True, "first_name": "Falso", "username": "falso_bot"})

        if metodo == "getFile":
            return self._json(
                {"file_id": "x", "file_unique_id": "u", "file_size": len(FOTO), "file_path": "photos/f.jpg"}
            )

        if metodo == "sendMessage":
            largo = int(self.headers.get("Content-Length") or 0)
            crudo = self.rfile.read(largo).decode() if largo else ""
            ENVIADOS.append(_interpretar(crudo))
            return self._json(
                {"message_id": len(ENVIADOS), "date": 0, "chat": {"id": 1, "type": "private"}}
            )

        if metodo == "_enviados":
            # Consulta de las pruebas, no de Telegram. Deja leer lo que el bot
            # le mando a cada persona, que es como una prueba puede pulsar un
            # boton sin inventarse su contenido.
            return self._json(ENVIADOS)

        if metodo == "_limpiar":
            ENVIADOS.clear()
            return self._json({"limpiado": True})

        return self._json({})


if __name__ == "__main__":
    print(f"telegram falso escuchando en :{PUERTO}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PUERTO), Manejador).serve_forever()
