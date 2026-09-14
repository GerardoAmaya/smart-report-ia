"""Entrada al tablero y permisos.

La verificacion de la fase 5 lo pide con estas palabras: el usuario de prueba
puede asignar, agrupar y cerrar, pero **no puede borrar** — comprobado con una
prueba, no a ojo. Eso es este archivo.
"""

import uuid

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from app import auth
from app.config import settings
from app.models import Case, Report, User
from app.permissions import Permission, Role, puede

# Con ñ a proposito: `compare_digest` sobre cadenas solo admite ASCII y
# reventaba con un 500. Una contraseña con ñ o tilde es lo normal aqui.
PASSWORD = "contraseña-de-prueba-larga"


@pytest.fixture(autouse=True)
def demo_configurado(monkeypatch):
    monkeypatch.setattr(settings, "demo_password", SecretStr(PASSWORD))
    monkeypatch.setattr(settings, "demo_email", "demo@smart-report.local")


@pytest.fixture
def admin(session):
    u = User(email="jefa@ejemplo.sv", role=Role.ADMIN.value, is_active=True)
    session.add(u)
    session.commit()
    return u


@pytest.fixture
def caso(session):
    c = Case(category="vialidad", severity="media", status="open", report_count=1)
    session.add(c)
    session.flush()
    r = Report(
        channel="telegram",
        external_user_id="1",
        status="received",
        case_id=c.id,
        grouping_status="grouped",
        location=func.ST_SetSRID(func.ST_MakePoint(-89.2, 13.7), 4326),
    )
    session.add(r)
    session.commit()
    return c


def entrar_de_prueba(client) -> None:
    r = client.post("/auth/demo", json={"password": PASSWORD})
    assert r.status_code == 200, r.text


def entrar_como(client, session, usuario: User) -> None:
    """Abre sesion sin pasar por Google, que no se puede en una prueba."""
    with client as c:
        c.post("/auth/demo", json={"password": PASSWORD})
    # Se reemplaza el correo de la sesion por el del usuario pedido.
    client.cookies.clear()
    import base64
    import json as _json

    from itsdangerous import TimestampSigner

    firmante = TimestampSigner(str(settings.session_secret.get_secret_value() or "x"))
    datos = base64.b64encode(_json.dumps({auth.CLAVE_DE_SESION: usuario.email}).encode())
    client.cookies.set("session", firmante.sign(datos).decode())


# --- LO QUE DEFINE LA FASE ---


def test_el_usuario_de_prueba_no_puede_borrar(client, session, caso):
    """La regla que PLAN.md pide comprobada con una prueba.

    Va a entrar gente a tocar todo, que para eso esta: que asigne, agrupe,
    separe y cierre; que no vacie la base.
    """
    entrar_de_prueba(client)

    r = client.delete(f"/board/cases/{caso.id}")

    assert r.status_code == 403
    assert "borrar" in r.json()["detail"]
    # Y el caso sigue vivo: no basta con que devuelva 403.
    session.refresh(caso)
    assert caso.status == "open"


def test_el_usuario_de_prueba_si_puede_despachar(client, session, caso):
    entrar_de_prueba(client)

    r = client.post(f"/board/cases/{caso.id}/status?nuevo=assigned")

    assert r.status_code == 200
    session.refresh(caso)
    assert caso.status == "assigned"


def test_el_usuario_de_prueba_si_puede_separar(client, session, caso):
    entrar_de_prueba(client)
    reporte = session.execute(select(Report).where(Report.case_id == caso.id)).scalar_one()

    r = client.post(f"/board/reports/{reporte.id}/ungroup")

    assert r.status_code == 200
    session.refresh(reporte)
    assert reporte.case_id != caso.id


def test_el_administrador_si_puede_borrar(client, session, admin, caso):
    entrar_como(client, session, admin)

    r = client.delete(f"/board/cases/{caso.id}")

    assert r.status_code == 200
    session.refresh(caso)
    assert caso.status == "discarded"


# --- Sin entrar no se ve nada ---


def test_sin_sesion_no_se_lee_el_tablero(client):
    assert client.get("/board/cases").status_code == 401
    assert client.get("/board/cases/map").status_code == 401
    assert client.get(f"/board/cases/{uuid.uuid4()}").status_code == 401


def test_sin_sesion_no_se_cambia_nada(client, caso):
    assert client.post(f"/board/cases/{caso.id}/status?nuevo=closed").status_code == 401
    assert client.delete(f"/board/cases/{caso.id}").status_code == 401


# --- La contraseña ---


def test_contraseña_equivocada_no_entra(client):
    r = client.post("/auth/demo", json={"password": "otra cosa"})
    assert r.status_code == 401
    assert client.get("/board/cases").status_code == 401


def test_sin_contraseña_configurada_no_entra_nadie(client, monkeypatch):
    """El fallo cierra, no abre.

    Si abriera, el dia que alguien olvide la variable el tablero quedaria
    abierto al mundo.
    """
    monkeypatch.setattr(settings, "demo_password", SecretStr(""))
    assert client.post("/auth/demo", json={"password": ""}).status_code == 401
    assert client.post("/auth/demo", json={"password": "loquesea"}).status_code == 401


def test_la_comparacion_no_filtra_por_tiempo():
    """`compare_digest` y no `==`: una comparacion que corta en el primer byte
    distinto filtra la contraseña midiendo el tiempo."""
    import inspect

    fuente = inspect.getsource(auth.password_de_prueba_valida)
    assert "compare_digest" in fuente


# --- Google dice quien es, no si puede entrar ---


def test_un_correo_que_no_esta_en_la_tabla_no_entra(session):
    assert auth.autorizado(session, "cualquiera@gmail.com") is None


def test_un_usuario_desactivado_no_entra(session, admin):
    admin.is_active = False
    session.commit()
    assert auth.autorizado(session, admin.email) is None


def test_el_correo_se_compara_en_minusculas(session, admin):
    assert auth.autorizado(session, "  JEFA@Ejemplo.SV  ") is not None


def test_quitar_el_acceso_corta_la_sesion_en_la_siguiente_peticion(client, session, admin, caso):
    """No se espera a que expire la cookie.

    Si a alguien se le quita el acceso, deja de poder ahora y no doce horas
    despues.
    """
    entrar_como(client, session, admin)
    assert client.get("/board/cases").status_code == 200

    admin.is_active = False
    session.commit()

    assert client.get("/board/cases").status_code == 403


# --- El usuario de prueba no escala ---


def test_el_usuario_de_prueba_no_puede_cambiar_de_rol(client, session):
    entrar_de_prueba(client)
    demo = session.execute(select(User).where(User.email == settings.demo_email)).scalar_one()

    demo.role = Role.ADMIN.value
    session.commit()

    # Al volver a entrar, se le devuelve su rol: es parte de lo que lo hace
    # seguro, no una preferencia.
    auth.asegurar_usuario_de_prueba(session)
    session.refresh(demo)
    assert demo.role == Role.DEMO.value


def test_los_permisos_por_rol_son_los_declarados():
    assert puede(Role.ADMIN.value, Permission.BORRAR)
    assert not puede(Role.OPERATOR.value, Permission.BORRAR)
    assert not puede(Role.DEMO.value, Permission.BORRAR)
    assert puede(Role.DEMO.value, Permission.DESPACHAR)
    # Un rol que no existe no hereda nada.
    assert not puede("superusuario", Permission.VER)


def test_yo_dice_que_puedo(client):
    entrar_de_prueba(client)
    cuerpo = client.get("/auth/yo").json()

    assert cuerpo["role"] == Role.DEMO.value
    assert "borrar" not in cuerpo["permissions"]
    assert "despachar" in cuerpo["permissions"]


def test_salir_cierra_la_sesion(client):
    entrar_de_prueba(client)
    assert client.get("/board/cases").status_code == 200

    client.post("/auth/salir")
    assert client.get("/board/cases").status_code == 401


def test_una_contraseña_con_acentos_funciona(client, monkeypatch):
    """El bug que encontro esta suite.

    `hmac.compare_digest` sobre `str` solo admite ASCII: con una ñ lanzaba
    TypeError y la entrada devolvia 500 en vez de dejar pasar.
    """
    monkeypatch.setattr(settings, "demo_password", SecretStr("mañana-será-mejor"))

    assert client.post("/auth/demo", json={"password": "mañana-será-mejor"}).status_code == 200
    client.post("/auth/salir")
    assert client.post("/auth/demo", json={"password": "manana-sera-mejor"}).status_code == 401
