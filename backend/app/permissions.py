"""Quien puede hacer que.

**Google dice quien es, no si puede entrar.** La autenticacion dice que el
correo es de quien dice ser; la autorizacion la decide esta tabla.

Los permisos se declaran por nombre y no por rol en cada comprobacion. La
diferencia importa: `if rol != "demo"` esparcido por el codigo es una regla que
vive en veinte sitios y se olvida en el veintiuno. `requiere(BORRAR)` vive en
uno.
"""

from __future__ import annotations

from enum import StrEnum

from app.config import settings


class Role(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    # Usuario de prueba, abierto al publico. El tablero es la mitad del
    # proyecto y uno que nadie puede ver no se puede mostrar.
    DEMO = "demo"


class Permission(StrEnum):
    VER = "ver"
    # Asignar cuadrillas, agrupar, separar, cambiar estado, cerrar.
    DESPACHAR = "despachar"
    # Borrar de verdad. Va aparte de todo lo demas a proposito.
    BORRAR = "borrar"
    # Autorizar correos, cambiar roles, desactivar cuentas. Es dar o quitar
    # acceso a todo lo demas, asi que va solo con administracion.
    GESTIONAR_USUARIOS = "gestionar_usuarios"


# **El usuario de prueba solo mira, salvo que se encienda `demo_can_dispatch`.**
# Su contraseña va en el README publico y el tablero es produccion: con despacho,
# cualquiera podria cerrar un caso real y el bot le avisaria al ciudadano que se
# resolvio sin que nadie fuera. Desarrollo y las E2E lo encienden para recorrer
# el ciclo con el invitado. Borrar no lo puede nunca, ni con el interruptor.
#
# Es un rol aparte de `operator` justo para esto: restringir al invitado sin
# tocar a los operadores ni migrar nada.
PERMISOS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(
        {Permission.VER, Permission.DESPACHAR, Permission.BORRAR, Permission.GESTIONAR_USUARIOS}
    ),
    Role.OPERATOR: frozenset({Permission.VER, Permission.DESPACHAR}),
    Role.DEMO: frozenset({Permission.VER}),
}


def permisos_de(role: str) -> frozenset[Permission]:
    """Los permisos efectivos del rol, con el interruptor del invitado aplicado.

    Unico sitio que decide: `puede()` y el perfil que recibe el tablero salen
    de aqui, asi la interfaz nunca ofrece un boton que la API va a rechazar.
    """
    try:
        rol = Role(role)
    except ValueError:
        # Un rol que no existe no puede nada. Falla cerrado: si alguien mete un
        # rol nuevo en la base y olvida declararlo aqui, no hereda permisos.
        return frozenset()
    base = PERMISOS[rol]
    if rol is Role.DEMO and settings.demo_can_dispatch:
        return base | {Permission.DESPACHAR}
    return base


def puede(role: str, permiso: Permission) -> bool:
    return permiso in permisos_de(role)
