"""Pruebas de las migraciones de Alembic sobre una base SQLite en memoria.

Las demás pruebas crean las tablas con create_all(); estas verifican que las
migraciones de verdad construyan (y deshagan) el mismo esquema que los modelos.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, create_engine, inspect

from libreria.basedatos import Base
from tests.conftest import RAIZ

TABLAS = {"libros", "usuarios", "pedidos", "pedido_items"}


@pytest.fixture
def conexion() -> Iterator[Connection]:
    motor = create_engine("sqlite://")
    with motor.connect() as con:
        yield con
    motor.dispose()


def configuracion(conexion: Connection) -> Config:
    """La configuración de alembic.ini, pero usando la conexión en memoria."""
    config = Config(str(RAIZ / "alembic.ini"))
    config.attributes["connection"] = conexion  # env.py la usa en lugar de la URL
    return config


def version_actual(conexion: Connection) -> str | None:
    return MigrationContext.configure(conexion).get_current_revision()


def columnas(conexion: Connection, tabla: str) -> set[str]:
    return {columna["name"] for columna in inspect(conexion).get_columns(tabla)}


def test_upgrade_crea_todas_las_tablas(conexion: Connection) -> None:
    config = configuracion(conexion)
    command.upgrade(config, "head")

    assert set(inspect(conexion).get_table_names()) >= TABLAS
    assert version_actual(conexion) == ScriptDirectory.from_config(config).get_current_head()


def test_migraciones_coinciden_con_los_modelos(conexion: Connection) -> None:
    """Equivale a `alembic check`: si falla, falta una migración para algún cambio."""
    command.upgrade(configuracion(conexion), "head")

    contexto = MigrationContext.configure(conexion, opts={"render_as_batch": True})
    diferencias = compare_metadata(contexto, Base.metadata)
    assert diferencias == [], f"Los modelos y las migraciones no coinciden: {diferencias}"


def test_migracion_0002_agrega_y_quita_telefono(conexion: Connection) -> None:
    config = configuracion(conexion)

    command.upgrade(config, "0001")
    assert "telefono" not in columnas(conexion, "usuarios")

    command.upgrade(config, "0002")
    assert "telefono" in columnas(conexion, "usuarios")

    command.downgrade(config, "0001")
    assert "telefono" not in columnas(conexion, "usuarios")


def test_downgrade_hasta_el_inicio(conexion: Connection) -> None:
    config = configuracion(conexion)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    assert not TABLAS & set(inspect(conexion).get_table_names())
    assert version_actual(conexion) is None
