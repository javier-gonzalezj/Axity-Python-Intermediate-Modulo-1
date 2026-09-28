"""Lectura y escritura del catálogo en el archivo JSON (persistencia)."""

import json
import logging
from pathlib import Path
from typing import Any, cast

from libreria.excepciones import (
    ArchivoJSONInvalidoError,
    ArchivoNoEncontradoError,
    CodificacionArchivoError,
    PermisoArchivoError,
)
from libreria.modelos import Libreria, Libro
from libreria.utilidades import escritura_atomica

log = logging.getLogger(__name__)


def cargar_datos(ruta: str | Path) -> Libreria:
    """Carga los datos de la librería desde un archivo JSON.

    Los libros se convierten a objetos Libro (validados); el resto de los datos
    de la librería se queda como diccionario.
    """
    try:
        with open(ruta, encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
    except FileNotFoundError:
        raise ArchivoNoEncontradoError(f"No se encontró el archivo: {ruta}") from None
    except PermissionError:
        raise PermisoArchivoError(f"Sin permisos para leer el archivo: {ruta}") from None
    except UnicodeDecodeError:
        raise CodificacionArchivoError(
            f"El archivo {ruta} no está codificado en UTF-8. "
            "Vuelve a guardarlo con esa codificación."
        ) from None
    except json.JSONDecodeError as e:
        raise ArchivoJSONInvalidoError(
            f"El archivo {ruta} no contiene JSON válido (línea {e.lineno}, columna {e.colno})"
        ) from None

    if not isinstance(data.get("libros"), list):
        raise ArchivoJSONInvalidoError(f"El archivo {ruta} no tiene una lista 'libros'")

    # Conversión a entidad: cada dict del JSON se vuelve un Libro validado
    data["libros"] = [Libro.desde_dict(libro) for libro in data["libros"]]
    # cast no convierte nada: solo le asegura a mypy que, tras validar los libros,
    # el diccionario ya tiene la forma de Libreria.

    log.info("Catálogo cargado desde %s: %d libros", ruta, len(data["libros"]))

    return cast(Libreria, data)


def guardar_datos(ruta: str | Path, data: Libreria) -> None:
    """Guarda los datos de la librería en el archivo JSON."""
    ruta = Path(ruta)

    # Serialización: cada Libro se vuelve dict. Se crea una copia para no
    # modificar `data`, que el programa sigue usando con objetos Libro.
    data_json: dict[str, Any] = {**data, "libros": [libro.a_dict() for libro in data["libros"]]}

    try:
        with escritura_atomica(ruta) as f:
            json.dump(data_json, f, ensure_ascii=False, indent=2)
    except PermissionError:
        raise PermisoArchivoError(f"Sin permisos para escribir el archivo: {ruta}") from None
    except FileNotFoundError:
        raise ArchivoNoEncontradoError(f"No existe la carpeta de destino: {ruta.parent}") from None

    log.info("Catálogo guardado en %s: %d libros", ruta, len(data["libros"]))
