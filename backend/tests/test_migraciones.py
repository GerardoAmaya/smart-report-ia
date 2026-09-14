"""Las migraciones bajan de verdad.

Una migracion que no baja se descubre el dia que hay que revertir en
produccion, que es el peor dia para descubrirlo.

Esta prueba existe por un fallo concreto: la bajada de `0001` hacia
`DROP EXTENSION postgis`, y la imagen oficial de PostGIS trae ademas
`postgis_topology` y `postgis_tiger_geocoder`, que dependen de el. Fallaba solo
en CI —la base de desarrollo la crea la imagen con las cinco extensiones y la
de pruebas con `CREATE DATABASE` trae solo una— asi que **la ida y vuelta se
estaba comprobando contra la base que no se parece a produccion**.
"""

import pytest
from sqlalchemy import text

from app.db import engine

# Las que instala la imagen oficial de PostGIS y esta migracion no creo.
DEPENDIENTES = ("postgis_topology", "postgis_tiger_geocoder")


def extensiones(conn) -> set[str]:
    return set(conn.execute(text("SELECT extname FROM pg_extension")).scalars().all())


def test_bajar_postgis_no_falla_con_extensiones_dependientes():
    """Con `postgis_topology` puesto, la bajada tiene que dejarlo estar.

    Se monta la situacion de produccion en la base de pruebas: se instala la
    extension dependiente y se ejecuta lo mismo que hace la migracion.
    """
    with engine.connect() as conn:
        conn.execute(text("COMMIT"))
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis_topology"))
            conn.execute(text("COMMIT"))
        except Exception:
            pytest.skip("esta imagen no trae postgis_topology")

        antes = extensiones(conn)
        assert "postgis_topology" in antes

        # Exactamente lo que ejecuta la bajada de 0001.
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    DROP EXTENSION IF EXISTS postgis;
                EXCEPTION WHEN dependent_objects_still_exist THEN
                    RAISE NOTICE 'postgis se deja puesto';
                END $$;
                """
            )
        )
        conn.execute(text("COMMIT"))

        despues = extensiones(conn)
        # No se llevo por delante lo que no creo.
        assert "postgis" in despues
        assert "postgis_topology" in despues

        conn.execute(text("DROP EXTENSION IF EXISTS postgis_topology"))
        conn.execute(text("COMMIT"))


def test_bajar_postgis_si_lo_quita_cuando_esta_solo():
    """En una base limpia baja de verdad: no es un no-op disfrazado.

    Hace falta una base **de verdad vacia**, no la de pruebas: sus tablas usan
    columnas `geography`, que tambien dependen de `postgis`, asi que ahi el DROP
    fallaria por un motivo distinto y la prueba pasaria sin comprobar nada.
    """
    import sqlalchemy

    # El sufijo _test importa: el guardia de borrados masivos solo deja pasar
    # un DROP cuando la conexion apunta a una base de pruebas.
    nombre = "smart_report_dropcheck_test"
    # render_as_string y no str(): `str(url)` enmascara la contraseña con ***,
    # y con eso la conexion falla con "password authentication failed", que
    # manda a buscar el problema donde no esta.
    url = engine.url.render_as_string(hide_password=False)
    base = url.rsplit("/", 1)[0]

    admin = sqlalchemy.create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{nombre}"'))
        conn.execute(text(f'CREATE DATABASE "{nombre}"'))
    admin.dispose()

    limpia = sqlalchemy.create_engine(f"{base}/{nombre}", isolation_level="AUTOCOMMIT")
    try:
        with limpia.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            assert "postgis" in extensiones(conn)

            # Exactamente lo que ejecuta la bajada de 0001.
            conn.execute(
                text(
                    """
                    DO $$
                    BEGIN
                        DROP EXTENSION IF EXISTS postgis;
                    EXCEPTION WHEN dependent_objects_still_exist THEN
                        RAISE NOTICE 'postgis se deja puesto';
                    END $$;
                    """
                )
            )
            assert "postgis" not in extensiones(conn), "sin dependientes tiene que bajar"
    finally:
        limpia.dispose()
        admin = sqlalchemy.create_engine(url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{nombre}"'))
        admin.dispose()
