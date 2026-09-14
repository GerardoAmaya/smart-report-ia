"""Defensas del borde: autenticidad, identidad del cliente y topes de entrada.

Todo lo de aca corre antes de tocar la base. Un chequeo que se hace despues de
escribir no es un chequeo, es una auditoria.
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings


def verify_webhook_secret(received: str | None) -> bool:
    """Compara el secreto del webhook en tiempo constante.

    Dos decisiones que parecen detalles y no lo son:

    - `compare_digest` y no `==`: una comparacion que corta en el primer byte
      distinto filtra el secreto caracter por caracter midiendo el tiempo.
    - Sin secreto configurado se rechaza todo, no se acepta todo. Si el fallo
      abre la puerta, el dia que alguien olvide la variable el bot acepta
      reportes de cualquiera y nadie se entera.
    """
    expected = settings.telegram_webhook_secret.get_secret_value()
    if not expected:
        return False
    if not received:
        return False
    return hmac.compare_digest(received, expected)


def client_ip(request: Request) -> str:
    """IP del cliente, respetando solo los proxies en los que confiamos.

    X-Forwarded-For lo puede escribir cualquiera. Si se lee sin mas, basta
    mandar una cabecera distinta en cada peticion para que el limite por IP no
    limite nada. Por eso el valor se toma contando saltos desde la derecha:
    esa punta la escribe el proxy mas cercano, que es el unico que el cliente
    no controla. Con cero saltos se usa la IP del socket y se ignora la
    cabecera por completo.
    """
    hops = settings.trusted_proxy_hops
    if hops > 0:
        forwarded = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else "unknown"


def rate_limit_key(raw: str) -> str:
    """Clave opaca para el limitador.

    La IP es dato personal y el limitador solo necesita saber si dos peticiones
    vienen del mismo lado, no de donde. Se guarda un HMAC con el secreto del
    servicio: sirve para comparar y no para reconstruir.
    """
    secret = settings.telegram_webhook_secret.get_secret_value() or settings.database_url
    return hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()


class BodySizeLimitMiddleware:
    """Corta cuerpos mas grandes que el tope, sin leerlos enteros.

    Dos capas porque una sola no alcanza: Content-Length permite rechazar
    barato y cubre el caso real —Telegram siempre lo manda—, pero se puede
    mentir o no mandar (transferencia troceada). Por eso ademas se cuenta lo
    que llega de verdad.

    Al pasarse no se lanza excepcion: eso lo atraparia el manejador de errores
    de Starlette y saldria un 500 antes de que este middleware pudiera
    responder. Se marca el scope y se corta el cuerpo; la ruta consulta la
    marca con `body_was_truncated` y responde 413.
    """

    def __init__(self, app: ASGIApp, max_bytes: int | None = None) -> None:
        self.app = app
        # None y no el valor: leer settings en el constructor congela el tope
        # en el momento del import. Se nota al probarlo, pero el problema de
        # verdad es que recargar configuracion no cambiaria nada.
        self._max_bytes = max_bytes

    @property
    def max_bytes(self) -> int:
        if self._max_bytes is not None:
            return self._max_bytes
        return settings.max_webhook_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        declared = headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self.max_bytes:
            await self._too_large(send)
            return

        estado = scope.setdefault("state", {})
        estado["body_too_large"] = False
        recibido = 0

        async def contando() -> Message:
            nonlocal recibido
            message = await receive()
            if message["type"] == "http.request":
                recibido += len(message.get("body", b""))
                if recibido > self.max_bytes:
                    estado["body_too_large"] = True
                    # Cuerpo vacio y fin: el handler deja de esperar bytes y la
                    # ruta decide, en vez de que sigamos tragando.
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        await self.app(scope, contando, send)

    async def _too_large(self, send: Send) -> None:
        # Mensajes ASGI a mano: montar una Response y llamarla con un scope
        # falso funciona por accidente y se rompe cuando Starlette cambie.
        cuerpo = b'{"detail":"cuerpo demasiado grande"}'
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(cuerpo)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": cuerpo})


def body_was_truncated(request: Request) -> bool:
    """True si BodySizeLimitMiddleware corto el cuerpo por pasarse del tope."""
    return bool(getattr(request, "scope", {}).get("state", {}).get("body_too_large"))


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Cabeceras que no cuestan nada y cierran clases enteras de problema."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        # La API no devuelve nada cacheable y si algo que si lo es: respuestas
        # de /health con detalles de infraestructura. Que no queden en proxies.
        response.headers["Cache-Control"] = "no-store"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
