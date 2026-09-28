"""Entorno de Alembic: conecta las migraciones con los modelos de basedatos.py."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool

from libreria.basedatos import Base

config = context.config

# Las pruebas pasan su propia conexión (una base en memoria) en
# config.attributes["connection"]; en ese caso no se toca el logging.
conexion_externa: Connection | None = config.attributes.get("connection")

if config.config_file_name is not None and conexion_externa is None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Los modelos contra los que --autogenerate compara la base
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse (alembic upgrade head --sql)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _ejecutar(conexion: Connection) -> None:
    context.configure(
        connection=conexion,
        target_metadata=target_metadata,
        # SQLite casi no soporta ALTER TABLE: batch mode recrea la tabla
        # (crea una nueva, copia los datos y reemplaza la vieja)
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica las migraciones conectándose a la base."""
    if conexion_externa is not None:
        _ejecutar(conexion_externa)
        return

    motor = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with motor.connect() as conexion:
        _ejecutar(conexion)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
