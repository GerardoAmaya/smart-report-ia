"""Updates de Telegram sinteticos.

Son la forma real del payload, copiada de lo que manda Telegram. Una prueba
contra un payload inventado comprueba que el codigo se entiende a si mismo.
"""

from __future__ import annotations

_FECHA = 1757800000


def _base(update_id: int, user_id: int) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id * 10,
            "date": _FECHA,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Vecina"},
        },
    }


def update_con_foto(
    update_id: int = 1,
    user_id: int = 4242,
    caption: str | None = "hueco frente a la casa",
    file_size: int = 240_000,
) -> dict:
    payload = _base(update_id, user_id)
    payload["message"]["photo"] = [
        # Telegram manda la misma foto en varios tamanos, de menor a mayor.
        {
            "file_id": "thumb",
            "file_unique_id": "u_thumb",
            "width": 90,
            "height": 60,
            "file_size": 1_200,
        },
        {
            "file_id": "grande",
            "file_unique_id": "u_grande",
            "width": 1280,
            "height": 860,
            "file_size": file_size,
        },
    ]
    if caption is not None:
        payload["message"]["caption"] = caption
    return payload


def update_con_ubicacion(
    update_id: int = 2, user_id: int = 4242, lat: float = 13.6929, lon: float = -89.2182
) -> dict:
    payload = _base(update_id, user_id)
    payload["message"]["location"] = {"latitude": lat, "longitude": lon}
    return payload


def update_con_texto(update_id: int = 3, user_id: int = 4242, texto: str = "hola") -> dict:
    payload = _base(update_id, user_id)
    payload["message"]["text"] = texto
    return payload


def update_con_sticker(update_id: int = 4, user_id: int = 4242) -> dict:
    payload = _base(update_id, user_id)
    payload["message"]["sticker"] = {
        "file_id": "s",
        "file_unique_id": "us",
        "width": 512,
        "height": 512,
        "is_animated": False,
        "is_video": False,
        "type": "regular",
    }
    return payload


def update_con_boton(
    update_id: int = 50,
    user_id: int = 4242,
    data: str = "s:00000000-0000-0000-0000-000000000000",
    message_id: int = 900,
) -> dict:
    """Un boton pulsado llega como callback_query, no como mensaje.

    Telegram solo manda este tipo si el webhook se registro con
    allowed_updates que lo incluya; si falta, la pulsacion se descarta en
    silencio y el boton gira para siempre. Paso una vez.
    """
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb{update_id}",
            "from": {"id": user_id, "is_bot": False, "first_name": "Vecina"},
            "chat_instance": "x",
            "data": data,
            "message": {
                "message_id": message_id,
                "date": _FECHA,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": 999, "is_bot": True, "first_name": "Bot"},
                "text": "¿Es correcto?",
            },
        },
    }
