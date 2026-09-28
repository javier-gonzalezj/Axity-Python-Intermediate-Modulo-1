"""Captura de datos por consola: aquí viven los input() del programa."""

import logging
from typing import Any

from libreria.buscador import DatosISBN, buscar_por_isbn
from libreria.catalogo import filtrar_libros
from libreria.excepciones import ServicioExternoError
from libreria.modelos import Libreria, Libro

log = logging.getLogger(__name__)


def _pedir_texto(etiqueta: str, sugerencia: str = "") -> str:
    """Pide un texto por consola. Si hay sugerencia, se muestra entre corchetes
    y basta con presionar Enter para aceptarla.
    """
    if sugerencia:
        return input(f"{etiqueta} [{sugerencia}]: ").strip() or sugerencia
    return input(f"{etiqueta}: ").strip()


def _buscar_sugerencias(isbn: str) -> DatosISBN:
    """Consulta el ISBN en Open Library. Si no hay datos, devuelve sugerencias vacías."""
    print("  🔎 Buscando el ISBN en Open Library...")
    try:
        datos = buscar_por_isbn(isbn)
    except ServicioExternoError as e:
        # log.warning también sale en consola (ver registro.py)
        log.warning("%s. Continúa con la captura manual.", e)
        return DatosISBN()

    if datos is None:
        print("  ℹ️  No se encontró en Open Library; captura los datos manualmente.")
        return DatosISBN()

    print(f"  ✅ Encontrado: {datos.titulo} — {datos.autor}")
    print("     Presiona Enter para aceptar el valor entre [corchetes] o escribe otro.")
    return datos


def capturar_libro(data: Libreria) -> tuple[dict[str, Any], int | None]:
    """Solicita al usuario los datos de un nuevo libro por consola.

    Devuelve el diccionario del libro y el id de su portada en Open Library
    (None si no se encontró). La portada no forma parte del modelo Libro.
    """
    print("\n📖 Nuevo libro")
    print("-" * 40)

    isbn_existente = {libro.isbn for libro in data["libros"]}
    while True:
        isbn = input("ISBN: ").strip()
        if isbn in isbn_existente:
            print("  ⚠️  Ya existe un libro con ese ISBN. Intenta con otro.")
            continue
        if not isbn:
            print("  ⚠️  El ISBN no puede estar vacío.")
            continue
        break

    sugerencia = _buscar_sugerencias(isbn)

    titulo = _pedir_texto("Título", sugerencia.titulo)
    nombre_autor = _pedir_texto("Nombre del autor", sugerencia.autor)
    nacionalidad_autor = input("Nacionalidad del autor: ").strip()

    generos_texto = _pedir_texto("Género(s) (separados por coma)", ", ".join(sugerencia.generos))
    generos = [g.strip() for g in generos_texto.split(",") if g.strip()]

    año_sugerido = str(sugerencia.año_publicacion or "")
    while True:
        try:
            año = int(_pedir_texto("Año de publicación", año_sugerido))
            break
        except ValueError:
            print("  ⚠️  Ingresa un número válido para el año.")

    while True:
        try:
            precio = float(input("Precio: ").strip())
            if precio < 0:
                print("  ⚠️  El precio no puede ser negativo.")
                continue
            break
        except ValueError:
            print("  ⚠️  Ingresa un número válido para el precio.")

    while True:
        try:
            cantidad = int(input("Cantidad disponible: ").strip())
            if cantidad < 0:
                print("  ⚠️  La cantidad no puede ser negativa.")
                continue
            break
        except ValueError:
            print("  ⚠️  Ingresa un número entero válido.")

    editorial = _pedir_texto("Editorial", sugerencia.editorial)

    libro: dict[str, Any] = {
        "isbn": isbn,
        "titulo": titulo,
        "autor": {"nombre": nombre_autor, "nacionalidad": nacionalidad_autor},
        "genero": generos,
        "año_publicacion": año,
        "precio": precio,
        "en_stock": cantidad > 0,
        "cantidad_disponible": cantidad,
        "editorial": editorial,
    }
    return libro, sugerencia.id_portada


def capturar_filtros(data: Libreria) -> list[Libro]:
    """Pregunta al usuario qué filtros quiere aplicar y devuelve el resultado."""

    print("\n🔍 Filtrar libros")
    print("(deja el campo vacío para no filtrar por ese criterio)")
    print("-" * 40)

    autor = input("Autor: ").strip() or None

    genero = input("Género: ").strip() or None

    en_stock_texto = input("¿Solo en stock? (s/n, vacío = no filtrar): ").strip().lower()
    en_stock: bool | None
    if en_stock_texto == "s":
        en_stock = True
    elif en_stock_texto == "n":
        en_stock = False
    else:
        en_stock = None

    precio_max_texto = input("Precio máximo: ").strip()
    precio_max: float | None = None
    if precio_max_texto:
        try:
            precio_max = float(precio_max_texto)
        except ValueError:
            print("  ⚠️  Precio inválido, se ignora este filtro.")

    año_min_texto = input("Año de publicación mínimo: ").strip()
    año_min: int | None = None
    if año_min_texto:
        try:
            año_min = int(año_min_texto)
        except ValueError:
            print("  ⚠️  Año inválido, se ignora este filtro.")

    return filtrar_libros(
        data,
        autor=autor,
        genero=genero,
        en_stock=en_stock,
        precio_max=precio_max,
        año_min=año_min,
    )
