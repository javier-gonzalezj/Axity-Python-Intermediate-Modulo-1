"""Presentación en consola: todo lo que imprime información para el usuario."""

import math
from itertools import batched

from libreria.modelos import Libreria, Libro


def _mostrar_libro(libro: Libro) -> None:
    """Imprime los datos de un solo libro."""
    disponibilidad = "✅ Disponible" if libro.en_stock else "❌ Agotado"
    print(f"\n{libro.titulo} ({libro.año_publicacion})")
    print(f"  Autor: {libro.autor.nombre} ({libro.autor.nacionalidad})")
    print(f"  Género: {', '.join(libro.genero)}")
    print(f"  Precio: ${libro.precio:.2f}")
    print(f"  {disponibilidad} — {libro.cantidad_disponible} unidades")


def mostrar_libreria(data: Libreria, por_pagina: int = 5) -> None:
    """
    Imprime la información de la librería y su catálogo ordenado,
    paginado de `por_pagina` en `por_pagina`.
    """

    print(f"📚 {data['nombre']}")
    print(
        f"📍 {data['direccion']['calle']}, "
        f"{data['direccion']['colonia']}, "
        f"{data['direccion']['ciudad']}"
    )
    print(f"📞 {data['telefono']}")
    print(f"🕒 {data['horario']}")
    print("-" * 40)

    libros = sorted(data["libros"])  # usa Libro.__lt__: año, título, ISBN
    total_paginas = math.ceil(len(libros) / por_pagina)

    for num, pagina in enumerate(batched(libros, por_pagina, strict=False), start=1):
        print(f"\n── Página {num} de {total_paginas} ──")
        for libro in pagina:
            _mostrar_libro(libro)

        if num < total_paginas:
            respuesta = input("\nEnter para ver más, 'q' para terminar: ").strip().lower()
            if respuesta == "q":
                break

    print("\n" + "=" * 40)
    print(f"Total de libros: {len(libros)}")
    valor_total = sum(libro.precio * libro.cantidad_disponible for libro in libros)
    print(f"Valor total del inventario: ${valor_total:.2f}")


def mostrar_libros(libros: list[Libro]) -> None:
    """Imprime una lista de libros ordenada (útil para mostrar resultados filtrados)."""
    if not libros:
        print("No se encontraron libros con esos criterios.")
        return

    for libro in sorted(libros):
        _mostrar_libro(libro)
