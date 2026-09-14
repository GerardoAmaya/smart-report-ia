"""El primer administrador.

Sale de `ADMIN_EMAIL`, nunca del codigo: es el correo personal de alguien, y un
correo en el repositorio queda en el historial de git para siempre.

Sin la variable no hace nada y lo dice. Fallar en silencio aqui dejaria un
tablero al que nadie puede entrar, y el sintoma —"Google me deja pero el sistema
no"— no apunta a la causa.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User
from app.permissions import Role


def seed(session: Session) -> None:
    correo = (settings.admin_email or "").strip().lower()
    if not correo:
        print("  ADMIN_EMAIL sin definir: no se sembro ningun administrador.")
        return

    usuario = session.execute(select(User).where(User.email == correo)).scalar_one_or_none()

    if usuario is None:
        session.add(
            User(
                email=correo,
                role=Role.ADMIN.value,
                display_name="Administrador",
                is_active=True,
            )
        )
        return

    # No se pisa el rol si ya existe: alguien pudo haberlo bajado a proposito, y
    # un seeder que lo devuelve a admin en cada despliegue deshace esa decision
    # sin avisar.
    if not usuario.is_active:
        print(f"  {correo} existe pero esta desactivado; no se reactiva solo.")
