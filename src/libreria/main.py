import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Final

from libreria.almacenamiento import cargar_datos, guardar_datos
from libreria.buscador import descargar_portada, nombre_archivo_portada
from libreria.captura import capturar_filtros, capturar_libro
from libreria.catalogo import agregar_libro
from libreria.excepciones import LibreriaError
from libreria.intercambio import exportar_json, importar_csv
from libreria.modelos import Libreria, Libro
from libreria.registro import configurar_logging
from libreria.utilidades import cronometro
from libreria.vista import mostrar_libreria, mostrar_libros

log = logging.getLogger(__name__)

LIBROS_POR_PAGINA: Final = 3

MENU: Final = """
═════════════ MENU ═════════════
  1. Filtrar libros
  2. Cargar archivo CSV
  3. Agregar un libro
  4. Ver catalogo completo
  0. Salir
════════════════════════════════"""


def _opcion_importar_csv(data: Libreria, ruta_json: Path) -> None:
    """2. Agrega al catálogo los libros de un archivo CSV y guarda."""
    # "Copiar como ruta" en Windows agrega comillas; se quitan
    texto_ruta = input("\nRuta del archivo CSV: ").strip().strip('"')
    respaldo = list(data["libros"])  # copia de la lista, por si falla el guardado

    try:
        resultado = importar_csv(data, texto_ruta)
    except LibreriaError as e:
        log.exception("Error al importar el archivo CSV")
        print(f"❌ No se pudo importar: {e}")
        return

    if resultado.rechazados:
        print(f"\n⚠️  {len(resultado.rechazados)} fila(s) rechazada(s):")
        for motivo in resultado.rechazados:
            print("   - " + motivo.replace("\n", "\n     "))

    if not resultado.agregados:
        print("\nNo se agregó ningún libro.")
    elif _guardar(ruta_json, data, respaldo):
        print(f"\n✅ {len(resultado.agregados)} libro(s) agregado(s).")


def _guardar(ruta_json: Path, data: Libreria, respaldo: list[Libro]) -> bool:
    """Guarda el catálogo. Si falla, deshace los cambios en memoria.

    `respaldo` es la lista de libros tal como estaba antes de modificarla.
    Devuelve True si se guardó.
    """
    try:
        with cronometro("Guardar catalogo"):
            guardar_datos(ruta_json, data)
    except LibreriaError as e:
        log.exception("Error al guardar el catálogo")
        data["libros"] = respaldo  # memoria y disco vuelven a coincidir
        print(f"❌ No se pudo guardar el catálogo, se descartaron los cambios: {e}")
        return False
    return True


def _opcion_filtrar(data: Libreria, carpeta_exportaciones: Path) -> None:
    """1. Filtra el catálogo y ofrece exportar el resultado a JSON."""
    resultados = capturar_filtros(data)
    print(f"\n🔍 {len(resultados)} resultado(s) encontrado(s):")
    mostrar_libros(resultados)

    if not resultados:
        return

    respuesta = input("\n¿Deseas exportar el resultado a JSON? (s/n): ").strip().lower()
    if respuesta != "s":
        return

    nombre_defecto = f"filtro_{datetime.now():%Y%m%d_%H%M%S}"
    nombre = input(f"Nombre del archivo [{nombre_defecto}]: ").strip()
    try:
        ruta_final = exportar_json(resultados, carpeta_exportaciones / (nombre or nombre_defecto))
    except LibreriaError as e:
        log.exception("Error al exportar el archivo JSON")
        print(f"❌ No se pudo exportar: {e}")
        return
    print(f"\n✅ Resultado exportado a: {ruta_final}")


def _opcion_agregar_libro(data: Libreria, ruta_json: Path, carpeta_portadas: Path) -> None:
    """3. Captura un libro por consola, lo agrega, guarda y descarga su portada."""
    respaldo = list(data["libros"])
    try:
        datos_libro, id_portada = capturar_libro(data)
        nuevo_libro = Libro.desde_dict(datos_libro)
        agregar_libro(data, nuevo_libro)
    except LibreriaError as e:
        log.exception("Error al agregar un libro")
        print(f"❌ No se pudo agregar el libro: {e}")
        return

    if not _guardar(ruta_json, data, respaldo):
        return
    print(f"\n✅ '{nuevo_libro.titulo}' agregado correctamente.")

    if id_portada is not None:
        _descargar_portada(id_portada, carpeta_portadas / nombre_archivo_portada(nuevo_libro.isbn))


def _descargar_portada(id_portada: int, destino: Path) -> None:
    """Descarga la portada. Si falla solo avisa: el libro ya quedó guardado."""
    print("🖼️  Descargando portada...")
    try:
        with cronometro("Descargar portada"):
            ruta = descargar_portada(id_portada, destino)
    except LibreriaError as e:
        log.exception("Error al descargar la portada")
        print(f"⚠️  El libro se guardó, pero no su portada: {e}")
        return
    print(f"✅ Portada guardada en: {ruta}")


def main() -> None:
    os.system("cls" if os.name == "nt" else "clear")

    raiz_proyecto = Path(__file__).parent.parent.parent
    ruta_json = raiz_proyecto / "data" / "libreria.json"
    carpeta_exportaciones = ruta_json.parent / "exportaciones"
    carpeta_portadas = ruta_json.parent / "portadas"

    configurar_logging(raiz_proyecto / "logs")
    log.info("Inicio del programa")

    print("\nSCRIPT DE MANEJO DE CATALOGO DE LIBROS (MODULO 7)\n")

    try:
        with cronometro("Cargar catálogo"):
            data = cargar_datos(ruta_json)
    except LibreriaError as e:
        log.exception("Error al cargar el catálogo")
        print(f"❌ Error al cargar la librería: {e}")
        return

    mostrar_libreria(data, por_pagina=LIBROS_POR_PAGINA)

    while True:
        print(MENU)
        opcion = input("Elige una opción: ").strip()
        log.debug("Opción elegida: %r", opcion)

        match opcion:
            case "1":
                _opcion_filtrar(data, carpeta_exportaciones)
            case "2":
                _opcion_importar_csv(data, ruta_json)
            case "3":
                _opcion_agregar_libro(data, ruta_json, carpeta_portadas)
            case "4":
                mostrar_libreria(data, por_pagina=LIBROS_POR_PAGINA)
            case "0":
                break
            case _:
                print("⚠️  Opción no válida, elige un número del menú.")

    log.info("Fin del programa")
    print("\n¡HASTA LUEGO!\n")


if __name__ == "__main__":
    main()
