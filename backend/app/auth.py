"""Entrada al tablero.

Dos formas: **Google** para el uso normal —asi no hay que guardar ninguna
credencial— y **contraseña** para un usuario de prueba abierto al publico,
porque el tablero es la mitad del proyecto y uno que nadie puede ver no se puede
mostrar.

**Google dice quien es, no si puede entrar.** El intercambio con Google termina
con un correo verificado; entrar o no lo decide la tabla `users`. Un correo que
no este ahi se rechaza aunque Google jure que existe.

La sesion va en una cookie firmada, no en un token en el navegador: `HttpOnly`
la deja fuera del alcance de cualquier script en la pagina, que es la via por la
que se roban las sesiones.
"""

from __future__ import annotations

import hmac
import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SesionBD
from app.models import User
from app.permissions import Permission, Role, puede

log = logging.getLogger("smart_report.auth")

CLAVE_DE_SESION = "user_email"


# --- Quien esta entrando ---


def current_user(request: Request, session: SesionBD) -> User:
    """El usuario de la sesion, comprobado **contra la base en cada peticion**.

    No se confia en lo que diga la cookie mas alla del correo. Si a alguien se
    le quita el acceso o se le baja el rol, deja de poder en la siguiente
    peticion y no cuando expire su sesion doce horas despues.
    """
    correo = request.session.get(CLAVE_DE_SESION)
    if not correo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "hay que entrar primero")

    usuario = session.execute(
        select(User).where(User.email == correo.lower(), User.is_active.is_(True))
    ).scalar_one_or_none()

    if usuario is None:
        # Estaba permitido y ya no. Se limpia la cookie para que el navegador
        # no siga mandando una sesion muerta.
        request.session.clear()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "esta cuenta ya no tiene acceso")

    return usuario


def requiere(permiso: Permission):
    """Dependencia que exige un permiso concreto.

    Por permiso y no por rol: `if rol != "demo"` esparcido por el codigo es una
    regla que vive en veinte sitios y se olvida en el veintiuno.
    """

    def comprobar(usuario: Annotated[User, Depends(current_user)]) -> User:
        if not puede(usuario.role, permiso):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"tu cuenta no puede {permiso.value}",
            )
        return usuario

    return comprobar


# --- Entrar ---


def autorizado(session: Session, correo: str) -> User | None:
    """El usuario si esta permitido, None si no. No crea nada."""
    return session.execute(
        select(User).where(User.email == correo.strip().lower(), User.is_active.is_(True))
    ).scalar_one_or_none()


def abrir_sesion(request: Request, session: Session, usuario: User) -> None:
    request.session[CLAVE_DE_SESION] = usuario.email
    usuario.last_login_at = func.now()
    session.commit()
    log.info("entro %s como %s", usuario.email, usuario.role)


def cerrar_sesion(request: Request) -> None:
    request.session.clear()


def password_de_prueba_valida(recibida: str) -> bool:
    """Compara la contraseña del usuario de prueba en tiempo constante.

    Sin contraseña configurada se rechaza todo. Si el fallo abriera, el dia que
    alguien olvide la variable el tablero quedaria abierto al mundo.
    """
    esperada = settings.demo_password.get_secret_value()
    if not esperada or not recibida:
        return False
    # En bytes y no en cadenas: `compare_digest` sobre str solo admite ASCII y
    # lanza TypeError con cualquier otra cosa. Una contraseña con ñ o tilde
    # —bastante probable aqui— devolvia un 500 en vez de dejar entrar.
    return hmac.compare_digest(recibida.encode("utf-8"), esperada.encode("utf-8"))


def asegurar_usuario_de_prueba(session: Session) -> User | None:
    """Crea o actualiza el usuario de prueba si hay contraseña configurada.

    Sin contraseña no existe: un usuario de prueba sin credencial es una fila
    que confunde y no sirve para nada.
    """
    if not settings.demo_password.get_secret_value():
        return None

    correo = settings.demo_email.strip().lower()
    usuario = session.execute(select(User).where(User.email == correo)).scalar_one_or_none()

    if usuario is None:
        usuario = User(
            email=correo,
            role=Role.DEMO.value,
            display_name="Usuario de prueba",
            is_active=True,
        )
        session.add(usuario)
        session.commit()
    elif usuario.role != Role.DEMO.value:
        # No se deja que el usuario publico escale de rol por un cambio de
        # configuracion: su rol es parte de lo que lo hace seguro.
        usuario.role = Role.DEMO.value
        session.commit()

    return usuario


def marca_de_tiempo() -> datetime:
    return datetime.now(UTC)
