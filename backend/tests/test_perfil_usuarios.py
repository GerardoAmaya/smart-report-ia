"""Mi perfil y la gestion de usuarios.

Dos cosas que se prueban por separado porque fallan distinto: la foto y el
nombre de cada quien (y que el invitado publico no pueda pintar su cuenta), y
quien da y quita acceso al tablero, con las reglas que evitan dejarlo sin dueño.
"""

import io
import uuid
from datetime import timedelta

import pytest
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import select

from app import auth, retention, storage
from app.config import settings
from app.main import app
from app.models import User
from app.permissions import Role
from tests.imagenes import foto_sintetica

PASSWORD = "contraseña-de-prueba-perfil"


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    monkeypatch.setattr(settings, "demo_password", SecretStr(PASSWORD))
    monkeypatch.setattr(settings, "demo_email", "demo@smart-report.local")
    yield
    app.dependency_overrides.clear()


def _usuario(session, correo: str, rol: Role, activo: bool = True) -> User:
    u = User(email=correo, role=rol.value, is_active=activo, display_name=correo.split("@")[0])
    session.add(u)
    session.commit()
    return u


@pytest.fixture
def admin(session):
    return _usuario(session, "jefa@ejemplo.sv", Role.ADMIN)


@pytest.fixture
def operador(session):
    return _usuario(session, "ana@ejemplo.sv", Role.OPERATOR)


def entrar_como(usuario: User) -> None:
    """Misma costura que test_auth: se sustituye la dependencia, no la cookie."""
    app.dependency_overrides[auth.current_user] = lambda: usuario


def _jpeg(ancho=900, alto=600) -> bytes:
    return foto_sintetica(ancho=ancho, alto=alto, semilla=7, objetivo_bytes=None)


# --- Mi perfil: foto ---


def test_subir_foto_la_recorta_a_256_y_la_enseña_firmada(client, session, operador):
    entrar_como(operador)

    r = client.post("/auth/yo/foto", files={"archivo": ("cara.jpg", _jpeg(), "image/jpeg")})

    assert r.status_code == 200, r.text
    session.refresh(operador)
    assert operador.avatar_key.startswith(f"avatares/{operador.id}/")
    with Image.open(io.BytesIO(storage.get(operador.avatar_key))) as img:
        assert img.size == (256, 256)
        assert img.format == "JPEG"
    # Firmada: el bucket no es publico y un avatar no es motivo para abrirlo.
    assert "Signature" in r.json()["avatar_url"] or "X-Amz-Signature" in r.json()["avatar_url"]
    storage.delete(operador.avatar_key)


def test_la_foto_subida_manda_sobre_la_de_google_y_quitarla_vuelve_a_google(
    client, session, operador
):
    operador.google_picture_url = "https://lh3.googleusercontent.com/a/foto"
    session.commit()
    entrar_como(operador)

    assert client.get("/auth/yo").json()["avatar_url"] == operador.google_picture_url

    client.post("/auth/yo/foto", files={"archivo": ("cara.jpg", _jpeg(), "image/jpeg")})
    session.refresh(operador)
    clave = operador.avatar_key
    assert client.get("/auth/yo").json()["avatar_url"] != operador.google_picture_url

    r = client.delete("/auth/yo/foto")

    assert r.status_code == 200
    assert r.json()["avatar_url"] == "https://lh3.googleusercontent.com/a/foto"
    assert r.json()["avatar_propio"] is False
    # Quitada de verdad: no queda en el bucket una foto que la persona retiro.
    assert storage.exists(clave) is False


def test_cambiar_de_foto_borra_la_anterior(client, session, operador):
    entrar_como(operador)
    client.post("/auth/yo/foto", files={"archivo": ("a.jpg", _jpeg(), "image/jpeg")})
    session.refresh(operador)
    primera = operador.avatar_key

    client.post("/auth/yo/foto", files={"archivo": ("b.jpg", _jpeg(500, 800), "image/jpeg")})
    session.refresh(operador)

    assert operador.avatar_key != primera
    assert storage.exists(primera) is False
    storage.delete(operador.avatar_key)


def test_un_archivo_que_no_es_imagen_no_se_guarda(client, session, operador):
    entrar_como(operador)
    r = client.post(
        "/auth/yo/foto", files={"archivo": ("x.jpg", b"\xff\xd8\xff basura", "image/jpeg")}
    )
    assert r.status_code == 400
    session.refresh(operador)
    assert operador.avatar_key is None


def test_sin_foto_ni_google_no_hay_avatar(client, operador):
    entrar_como(operador)
    perfil = client.get("/auth/yo").json()
    assert perfil["avatar_url"] is None
    assert perfil["avatar_propio"] is False
    assert "last_login_at" in perfil


# --- Mi perfil: nombre ---


def test_cambiar_el_nombre(client, session, operador):
    entrar_como(operador)
    r = client.patch("/auth/yo", json={"display_name": "  Ana   Martínez "})
    assert r.status_code == 200
    session.refresh(operador)
    assert operador.display_name == "Ana Martínez"


@pytest.mark.parametrize("nombre", ["", "   ", "x" * 65, "<b>Ana</b>"])
def test_un_nombre_invalido_se_rechaza(client, session, operador, nombre):
    entrar_como(operador)
    r = client.patch("/auth/yo", json={"display_name": nombre})
    assert r.status_code == 422
    session.refresh(operador)
    assert operador.display_name == "ana"


# --- El invitado no pinta su cuenta ---


def test_el_invitado_no_cambia_ni_nombre_ni_foto(client):
    """Es una cuenta que comparte todo el publico: seria grafiti."""
    assert client.post("/auth/demo", json={"password": PASSWORD}).status_code == 200

    assert client.patch("/auth/yo", json={"display_name": "hola"}).status_code == 403
    r = client.post("/auth/yo/foto", files={"archivo": ("c.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 403
    assert client.delete("/auth/yo/foto").status_code == 403


# --- La retencion no se lleva lo que no es suyo ---


def test_el_barrido_de_huerfanos_no_borra_avatares(client, session, operador, monkeypatch):
    monkeypatch.setattr(settings, "orphan_grace_hours", 0)
    entrar_como(operador)
    client.post("/auth/yo/foto", files={"archivo": ("c.jpg", _jpeg(), "image/jpeg")})
    session.refresh(operador)

    retention.purge_orphans(session)

    assert storage.exists(operador.avatar_key) is True
    storage.delete(operador.avatar_key)


def test_el_barrido_de_huerfanos_no_borra_los_respaldos(session, monkeypatch):
    """Paso: el barrido tomaba cada respaldo de la base por huerfano.

    Nada en las tablas de fotos apunta a `respaldos/`, asi que con 24 horas de
    gracia borraba el de ayer cada dia: la ventana de catorce dias era de uno.
    """
    monkeypatch.setattr(settings, "orphan_grace_hours", 0)
    clave = f"respaldos/prueba-{uuid.uuid4()}.dump"
    storage.put(clave, b"volcado", "application/octet-stream")
    try:
        assert clave not in retention.orphans(session)
        retention.purge_orphans(session)
        assert storage.exists(clave) is True
    finally:
        storage.delete(clave)


def test_un_avatar_sin_dueño_tampoco_lo_toca_el_barrido_de_fotos(session, monkeypatch):
    """El barrido es de fotos de reporte y de arreglo, por la forma de su clave."""
    monkeypatch.setattr(settings, "orphan_grace_hours", 0)
    clave = f"avatares/{uuid.uuid4()}/suelto.jpg"
    storage.put(clave, _jpeg(), "image/jpeg")
    try:
        assert clave not in retention.orphans(session)
    finally:
        storage.delete(clave)


# --- Gestion de usuarios: quien puede ---


def test_solo_administracion_gestiona_usuarios(client, operador):
    entrar_como(operador)
    assert client.get("/board/usuarios").status_code == 403
    assert (
        client.post("/board/usuarios", json={"email": "x@y.sv", "role": "operator"}).status_code
        == 403
    )


def test_el_invitado_no_gestiona_usuarios(client):
    assert client.post("/auth/demo", json={"password": PASSWORD}).status_code == 200
    assert client.get("/board/usuarios").status_code == 403


def test_sin_sesion_no_se_gestiona_nada(client):
    assert client.get("/board/usuarios").status_code == 401


# --- Gestion de usuarios: lo que hace ---


def test_la_lista_no_incluye_al_invitado(client, session, admin, operador):
    _usuario(session, "demo@smart-report.local", Role.DEMO)
    entrar_como(admin)

    correos = {u["email"] for u in client.get("/board/usuarios").json()["usuarios"]}

    assert correos == {"jefa@ejemplo.sv", "ana@ejemplo.sv"}


def test_autorizar_un_correo(client, session, admin):
    entrar_como(admin)

    r = client.post("/board/usuarios", json={"email": "  Luis@Ejemplo.SV ", "role": "operator"})

    assert r.status_code == 201
    nuevo = session.execute(select(User).where(User.email == "luis@ejemplo.sv")).scalar_one()
    assert nuevo.role == "operator" and nuevo.is_active


def test_autorizar_un_correo_que_ya_esta_da_409(client, admin, operador):
    entrar_como(admin)
    r = client.post("/board/usuarios", json={"email": "ANA@ejemplo.sv", "role": "admin"})
    assert r.status_code == 409


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"email": "no-es-correo", "role": "operator"},
        {"email": "a@b.sv", "role": "demo"},
        {"email": "a@b.sv", "role": "dueño"},
    ],
)
def test_autorizar_valida_correo_y_rol(client, admin, cuerpo):
    entrar_como(admin)
    assert client.post("/board/usuarios", json=cuerpo).status_code == 422


def test_cambiar_rol_y_desactivar_a_otro(client, session, admin, operador):
    entrar_como(admin)

    r = client.patch(f"/board/usuarios/{operador.id}", json={"role": "admin"})
    assert r.status_code == 200
    r = client.patch(f"/board/usuarios/{operador.id}", json={"is_active": False})
    assert r.status_code == 200

    session.refresh(operador)
    assert operador.role == "admin" and operador.is_active is False


def test_nadie_se_desactiva_a_si_mismo(client, session, admin):
    _usuario(session, "otra@ejemplo.sv", Role.ADMIN)
    entrar_como(admin)
    r = client.patch(f"/board/usuarios/{admin.id}", json={"is_active": False})
    assert r.status_code == 409
    session.refresh(admin)
    assert admin.is_active is True


def test_nadie_se_quita_el_rol_a_si_mismo(client, session, admin):
    _usuario(session, "otra@ejemplo.sv", Role.ADMIN)
    entrar_como(admin)
    r = client.patch(f"/board/usuarios/{admin.id}", json={"role": "operator"})
    assert r.status_code == 409
    assert "ti mismo" in r.json()["detail"]


def test_no_se_queda_sin_ningun_administrador_activo(client, session, admin):
    """Dos admins desactivandose el uno al otro a la vez dejaban cero.

    En secuencia no se puede reproducir —el segundo ya no pasaria por
    `current_user`—, asi que se hace lo que ve la segunda peticion de esa
    carrera: actua alguien a quien acaban de desactivar, y la regla, que cuenta
    con las filas bloqueadas, ve que solo queda uno.
    """
    otra = _usuario(session, "otra@ejemplo.sv", Role.ADMIN)
    entrar_como(admin)
    assert client.patch(f"/board/usuarios/{otra.id}", json={"is_active": False}).status_code == 200

    entrar_como(otra)
    r = client.patch(f"/board/usuarios/{admin.id}", json={"is_active": False})

    assert r.status_code == 409
    assert "al menos un administrador" in r.json()["detail"]
    session.refresh(admin)
    assert admin.is_active is True


def test_el_invitado_no_se_toca_desde_la_gestion(client, session, admin):
    demo = _usuario(session, "demo@smart-report.local", Role.DEMO)
    entrar_como(admin)
    r = client.patch(f"/board/usuarios/{demo.id}", json={"role": "admin"})
    assert r.status_code == 403
    session.refresh(demo)
    assert demo.role == "demo"


def test_un_desactivado_ya_no_entra_en_la_siguiente_peticion(client, session, admin, operador):
    """Desactivar cierra sus sesiones: `current_user` mira la tabla cada vez."""
    entrar_como(admin)
    client.patch(f"/board/usuarios/{operador.id}", json={"is_active": False})
    app.dependency_overrides.clear()

    class Peticion:
        session = {auth.CLAVE_DE_SESION: operador.email}

    with pytest.raises(Exception) as fallo:
        auth.current_user(Peticion(), session)
    assert getattr(fallo.value, "status_code", None) == 403


def test_la_ultima_entrada_viaja_en_la_lista(client, session, admin):
    from datetime import UTC, datetime

    admin.last_login_at = datetime.now(UTC) - timedelta(hours=2)
    session.commit()
    entrar_como(admin)
    fila = client.get("/board/usuarios").json()["usuarios"][0]
    assert fila["last_login_at"] is not None
    assert {"id", "email", "display_name", "role", "is_active", "avatar_url"} <= fila.keys()
