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


# **El usuario de prueba no puede borrar.** Va a entrar gente a tocar todo, que
# para eso esta: que asigne, agrupe, separe y cierre; que no vacie la base. Es
# una condicion en el rol y ahorra restaurar un respaldo.
#
# `demo` y `operator` tienen hoy los mismos permisos. Se mantienen separados
# para poder restringir al de prueba mas adelante sin tocar a los operadores ni
# migrar nada.
PERMISOS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset({Permission.VER, Permission.DESPACHAR, Permission.BORRAR}),
    Role.OPERATOR: frozenset({Permission.VER, Permission.DESPACHAR}),
    Role.DEMO: frozenset({Permission.VER, Permission.DESPACHAR}),
}


def puede(role: str, permiso: Permission) -> bool:
    try:
        return permiso in PERMISOS[Role(role)]
    except ValueError:
        # Un rol que no existe no puede nada. Falla cerrado: si alguien mete un
        # rol nuevo en la base y olvida declararlo aqui, no hereda permisos.
        return False
