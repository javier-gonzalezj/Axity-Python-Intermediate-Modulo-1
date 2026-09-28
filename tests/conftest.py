"""Fixtures compartidas por las pruebas.

pytest carga este archivo automáticamente: cualquier prueba que declare un
parámetro llamado `sesion` recibe lo que devuelve la fixture de abajo.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from libreria import basedatos as bd
from libreria.almacenamiento import cargar_datos

RAIZ = Path(__file__).parent.parent
CATALOGO = RAIZ / "data" / "libreria.json"


@pytest.fixture
def sesion() -> Iterator[Session]:
    """Base SQLite en memoria, nueva para cada prueba, con el catálogo importado."""
    motor = bd.crear_motor("sqlite://")  # "sqlite://" = base en memoria
    bd.crear_esquema(motor)
    with Session(motor) as s:
        bd.importar_catalogo(s, cargar_datos(CATALOGO))
        yield s
    motor.dispose()
