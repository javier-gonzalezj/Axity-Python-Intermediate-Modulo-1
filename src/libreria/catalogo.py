"""Reglas del catálogo: operaciones sobre los libros sin entrada/salida."""

import logging

from libreria.excepciones import LibroInvalidoError
from libreria.modelos import Libreria, Libro

log = logging.getLogger(__name__)


def agregar_libro(data: Libreria, libro: Libro) -> Libreria:
    """Agrega un nuevo libro al catálogo, verificando que el ISBN no exista ya.

    La validación de la estructura ya la hizo el modelo Libro al crearse.
    """
    isbn_existentes = {existente.isbn for existente in data["libros"]}
    if libro.isbn in isbn_existentes:
        raise LibroInvalidoError(f"Ya existe un libro con ISBN {libro.isbn}")

    data["libros"].append(libro)
    log.info("Libro agregado: %s (ISBN %s)", libro.titulo, libro.isbn)

    return data


def filtrar_libros(
    data: Libreria,
    autor: str | None = None,
    genero: str | None = None,
    en_stock: bool | None = None,
    precio_max: float | None = None,
    año_min: int | None = None,
) -> list[Libro]:
    """Filtra el catálogo de libros según los criterios indicados.

    Cualquier parámetro que se deje en None se ignora (no filtra por ese campo).
    """
    log.debug(
        "Filtros: autor=%r genero=%r en_stock=%r precio_max=%r año_min=%r",
        autor,
        genero,
        en_stock,
        precio_max,
        año_min,
    )
    resultado = data["libros"]

    if autor is not None:
        resultado = [libro for libro in resultado if autor.lower() in libro.autor.nombre.lower()]

    if genero is not None:
        resultado = [
            libro for libro in resultado if any(genero.lower() in g.lower() for g in libro.genero)
        ]

    if en_stock is not None:
        resultado = [libro for libro in resultado if libro.en_stock == en_stock]

    if precio_max is not None:
        resultado = [libro for libro in resultado if libro.precio <= precio_max]

    if año_min is not None:
        resultado = [libro for libro in resultado if libro.año_publicacion >= año_min]

    log.debug("Filtrado: %d de %d libros", len(resultado), len(data["libros"]))

    return resultado
