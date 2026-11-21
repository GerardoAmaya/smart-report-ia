"""Quien puede entrar al tablero, gestionado desde el propio tablero.

Antes autorizar a alguien pedia `ADMIN_EMAIL` y correr los seeders en el
servidor. Ahora lo hace un administrador aqui, con las mismas reglas: **Google
dice quien es; esta tabla dice si puede.** Autorizar un correo no crea ninguna
cuenta de Google ni manda nada: solo deja pasar a ese correo cuando entre.

Tres reglas que no se negocian, porque romperlas deja el sistema sin dueño:
nadie se desactiva ni se baja el rol a si mismo, no se puede quedar sin ningun
administrador activo, y el invitado publico no se gestiona aqui.
"""

from __future__ import annotations

import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select

from app.auth import requiere
from app.db import SesionBD
from app.models import User
from app.permissions import Permission, Role
from app.routes_auth import avatar_url

router = APIRouter(prefix="/board/usuarios", tags=["usuarios"])

Gestiona = Annotated[User, Depends(requiere(Permission.GESTIONAR_USUARIOS))]

# Los roles que se pueden dar desde aqui. El invitado no: es una cuenta que crea
# el sistema y cuyo acceso decide su contraseña, no esta lista.
ROLES_ASIGNABLES = {Role.OPERATOR.value, Role.ADMIN.value}

# Suficiente para no autorizar un error de dedo; quien decide si el correo
# existe es Google, cuando la persona entre.
CORREO = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


def _fila(usuario: User) -> dict:
    return {
        "id": str(usuario.id),
        "email": usuario.email,
        "display_name": usuario.display_name,
        "role": usuario.role,
        "is_active": usuario.is_active,
        "last_login_at": usuario.last_login_at.isoformat() if usuario.last_login_at else None,
        "avatar_url": avatar_url(usuario),
    }


def _admins_activos(session) -> int:
    """Cuantos administradores activos hay, **bloqueando sus filas**.

    Con las reglas de arriba, quien actua es un admin activo distinto del
    afectado, asi que en secuencia siempre quedan dos. El hueco es la
    concurrencia: dos admins desactivandose el uno al otro a la vez veian
    "quedan dos" cada uno y dejaban cero. Con FOR UPDATE la segunda peticion
    espera a la primera y vuelve a contar con su cambio ya aplicado.
    """
    filas = session.execute(
        select(User.id)
        .where(User.role == Role.ADMIN.value, User.is_active.is_(True))
        .with_for_update()
    ).all()
    return len(filas)


@router.get("")
def listar(_: Gestiona, session: SesionBD) -> dict:
    usuarios = (
        session.execute(select(User).where(User.role != Role.DEMO.value).order_by(User.created_at))
        .scalars()
        .all()
    )
    return {"usuarios": [_fila(u) for u in usuarios]}


@router.post("", status_code=status.HTTP_201_CREATED)
def autorizar(
    _: Gestiona,
    session: SesionBD,
    email: Annotated[str, Body()],
    role: Annotated[str, Body()],
) -> dict:
    correo = email.strip().lower()
    if not CORREO.match(correo) or len(correo) > 320:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Ese correo no es válido.")
    if role not in ROLES_ASIGNABLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "El rol tiene que ser despacho o administración."
        )
    existe = session.execute(select(User).where(User.email == correo)).scalar_one_or_none()
    if existe is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese correo ya está autorizado.")

    nuevo = User(email=correo, role=role, is_active=True)
    session.add(nuevo)
    session.commit()
    return _fila(nuevo)


@router.patch("/{usuario_id}")
def cambiar(
    usuario_id: UUID,
    quien: Gestiona,
    session: SesionBD,
    role: Annotated[str | None, Body()] = None,
    is_active: Annotated[bool | None, Body()] = None,
) -> dict:
    objetivo = session.get(User, usuario_id)
    if objetivo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese usuario no existe.")
    if objetivo.role == Role.DEMO.value:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "La cuenta de prueba no se gestiona desde aquí."
        )
    if role is not None and role not in ROLES_ASIGNABLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "El rol tiene que ser despacho o administración."
        )

    es_uno_mismo = objetivo.id == quien.id
    if es_uno_mismo and is_active is False:
        raise HTTPException(status.HTTP_409_CONFLICT, "No puedes desactivar tu propia cuenta.")
    if es_uno_mismo and role is not None and role != objetivo.role:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No puedes quitarte el rol de administrador a ti mismo.",
        )

    # Quedarse sin administradores activos no tiene vuelta atras desde el
    # tablero: nadie podria volver a autorizar a nadie.
    deja_de_ser_admin = (
        objetivo.role == Role.ADMIN.value
        and objetivo.is_active
        and ((role is not None and role != Role.ADMIN.value) or is_active is False)
    )
    if deja_de_ser_admin and _admins_activos(session) <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Tiene que quedar al menos un administrador activo."
        )

    if role is not None:
        objetivo.role = role
    if is_active is not None:
        # Desactivar basta para cerrar sus sesiones: `current_user` mira la
        # tabla en cada peticion, asi que la siguiente ya le responde 403.
        objetivo.is_active = is_active
    session.commit()
    return _fila(objetivo)
