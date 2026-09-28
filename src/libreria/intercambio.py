"""Intercambio de libros con archivos externos (importar y exportar).

Aquí van los archivos que no son el catálogo principal: exportar una selección
de libros a JSON e importar libros nuevos desde CSV. El catálogo de la librería
se maneja en almacenamiento.py.
"""

import csv
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from libreria.catalogo import agregar_libro
from libreria.excepciones import (
    ArchivoCSVInvalidoError,
    ArchivoNoEncontradoError,
    CodificacionArchivoError,
    LibroInvalidoError,
    PermisoArchivoError,
)
from libreria.modelos import Libreria, Libro
from libreria.utilidades import escritura_atomica

log = logging.getLogger(__name__)

# ── Exportación ──────────────────────────────────────────────────────────────


def exportar_json(libros: list[Libro], ruta: str | Path) -> Path:
    """Guarda una lista de libros en un archivo JSON y devuelve la ruta final.

    Los libros se guardan bajo la clave "libros", con la misma forma que en el
    catálogo, para poder leerlos después con Libro.desde_dict.
    """
    ruta = Path(ruta).with_suffix(".json")
    ruta.parent.mkdir(parents=True, exist_ok=True)

    # Serialización: cada Libro se vuelve dict, igual que en guardar_datos
    contenido: dict[str, Any] = {
        "exportado": datetime.now().isoformat(timespec="seconds"),
        "total": len(libros),
        "libros": [libro.a_dict() for libro in sorted(libros)],
    }

    try:
        with escritura_atomica(ruta) as f:
            json.dump(contenido, f, ensure_ascii=False, indent=2)
    except PermissionError:
        raise PermisoArchivoError(f"Sin permisos para escribir el archivo: {ruta}") from None

    log.info("Exportados %d libros a %s", len(libros), ruta)

    return ruta


# ── Importación desde CSV ────────────────────────────────────────────────────

COLUMNAS_OBLIGATORIAS = frozenset(
    {
        "isbn",
        "titulo",
        "autor",
        "genero",
        "año_publicacion",
        "precio",
        "cantidad_disponible",
        "editorial",
    }
)
# Opcionales: "nacionalidad_autor" (vacía por defecto) y "en_stock"
# (si no viene, se calcula con cantidad_disponible > 0, igual que en capturar_libro).

SEPARADOR_GENEROS = ";"
VALORES_SI = frozenset({"sí", "si", "s", "true", "1"})
VALORES_NO = frozenset({"no", "n", "false", "0"})


@dataclass
class ResultadoImportacion:
    """Qué pasó al importar: libros agregados y filas rechazadas con su motivo."""

    agregados: list[Libro] = field(default_factory=list)
    rechazados: list[str] = field(default_factory=list)


def _a_entero(fila: dict[str, str], columna: str) -> int:
    valor = fila[columna].strip()
    try:
        return int(valor)
    except ValueError:
        raise ValueError(f"'{columna}' debe ser un número entero (se leyó {valor!r})") from None


def _a_decimal(fila: dict[str, str], columna: str) -> float:
    valor = fila[columna].strip()
    try:
        return float(valor)
    except ValueError:
        raise ValueError(f"'{columna}' debe ser un número (se leyó {valor!r})") from None


def _a_booleano(texto: str) -> bool:
    valor = texto.strip().lower()
    if valor in VALORES_SI:
        return True
    if valor in VALORES_NO:
        return False
    raise ValueError(f"'en_stock' debe ser sí/no (se leyó {texto!r})")


def _fila_a_dict(fila: dict[str, str]) -> dict[str, Any]:
    """Parseo: convierte una fila del CSV (todo es texto) en un dict con la forma de Libro.

    Es la operación inversa a la serialización: reconstruye el Autor anidado a
    partir de dos columnas y la lista de géneros a partir de un solo texto.
    Lanza ValueError si un número o un sí/no no se puede convertir.
    """
    cantidad = _a_entero(fila, "cantidad_disponible")
    en_stock_texto = (fila.get("en_stock") or "").strip()

    return {
        "isbn": fila["isbn"],
        "titulo": fila["titulo"],
        "autor": {
            "nombre": fila["autor"],
            "nacionalidad": fila.get("nacionalidad_autor") or "",
        },
        "genero": [g.strip() for g in fila["genero"].split(SEPARADOR_GENEROS) if g.strip()],
        "año_publicacion": _a_entero(fila, "año_publicacion"),
        "precio": _a_decimal(fila, "precio"),
        "en_stock": _a_booleano(en_stock_texto) if en_stock_texto else cantidad > 0,
        "cantidad_disponible": cantidad,
        "editorial": fila["editorial"],
    }


def leer_libros_csv(ruta: str | Path) -> tuple[list[Libro], list[str]]:
    """Lee un CSV y devuelve (libros válidos, errores por fila).

    Un error en una fila no detiene la lectura: la fila se reporta y se sigue
    con la siguiente. Los problemas con el archivo completo (no existe, sin
    permisos, codificación, faltan columnas) sí lanzan una excepción.
    """
    ruta = Path(ruta)
    libros: list[Libro] = []
    errores: list[str] = []

    try:
        # utf-8-sig lee igual archivos UTF-8 normales y los "CSV UTF-8" de Excel (con BOM)
        with ruta.open(encoding="utf-8-sig", newline="") as f:
            lector = csv.DictReader(f)
            if lector.fieldnames is None:
                raise ArchivoCSVInvalidoError(f"El archivo {ruta} está vacío")

            # Tolera encabezados con espacios o mayúsculas: " Titulo " → "titulo"
            lector.fieldnames = [columna.strip().lower() for columna in lector.fieldnames]
            faltantes = COLUMNAS_OBLIGATORIAS - set(lector.fieldnames)
            if faltantes:
                raise ArchivoCSVInvalidoError(
                    f"Al archivo {ruta} le faltan columnas: {', '.join(sorted(faltantes))}"
                )

            for fila in lector:
                linea = lector.line_num
                # DictReader usa la clave None para columnas de más y el valor None
                # para columnas de menos
                if None in fila or None in fila.values():
                    errores.append(f"Línea {linea}: número de columnas incorrecto")
                    continue
                try:
                    libros.append(Libro.desde_dict(_fila_a_dict(fila)))
                except (ValueError, LibroInvalidoError) as e:
                    errores.append(f"Línea {linea}: {e}")

    except FileNotFoundError:
        raise ArchivoNoEncontradoError(f"No se encontró el archivo: {ruta}") from None
    except PermissionError:
        raise PermisoArchivoError(f"Sin permisos para leer el archivo: {ruta}") from None
    except UnicodeDecodeError:
        raise CodificacionArchivoError(
            f"El archivo {ruta} no está en UTF-8. En Excel usa 'Guardar como' → 'CSV UTF-8'."
        ) from None
    except csv.Error as e:
        raise ArchivoCSVInvalidoError(f"El archivo {ruta} no es un CSV válido: {e}") from None

    return libros, errores


def importar_csv(data: Libreria, ruta: str | Path) -> ResultadoImportacion:
    """Agrega al catálogo los libros de un CSV y devuelve el resumen.

    Solo modifica `data` en memoria; guardar el catálogo le corresponde a quien
    llama (main.py), igual que al agregar un libro a mano.
    """
    libros, errores = leer_libros_csv(ruta)
    resultado = ResultadoImportacion(rechazados=errores)

    for libro in libros:
        try:
            agregar_libro(data, libro)  # rechaza ISBN repetidos, también dentro del mismo CSV
        except LibroInvalidoError as e:
            resultado.rechazados.append(f"'{libro.titulo}': {e}")
        else:
            resultado.agregados.append(libro)

    log.info(
        "Importación desde %s: %d agregados, %d rechazados",
        ruta,
        len(resultado.agregados),
        len(resultado.rechazados),
    )
    for motivo in resultado.rechazados:
        log.debug("Rechazado: %s", motivo)

    return resultado
