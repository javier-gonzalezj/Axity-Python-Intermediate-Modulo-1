"""Consulta de datos de un libro en Open Library a partir de su ISBN.

Este es el único módulo del proyecto que habla con internet. Si la consulta
falla, lanza ServicioExternoError para que quien lo llame decida qué hacer
(en captura.py: seguir con la captura manual).

Usa la API REST de Open Library, que devuelve el JSON de cada objeto por su ruta:
  /isbn/9780307474728.json  -> la *edición* (título, editorial, fecha...)
  /works/OL274505W.json     -> la *obra* (géneros; a veces los autores)
  /authors/OL4586796A.json  -> el *autor* (nombre)
La edición solo trae la "clave" del autor, no su nombre; por eso hay que hacer
una petición extra por autor.

Las portadas están en otro servidor (covers.openlibrary.org) y se descargan
por streaming con descargar_portada().
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from libreria.excepciones import ServicioExternoError
from libreria.utilidades import reintentar

log = logging.getLogger(__name__)

URL_BASE = "https://openlibrary.org"
URL_PORTADAS = "https://covers.openlibrary.org"
TIMEOUT_SEGUNDOS = 5
TIMEOUT_DESCARGA = 15  # una imagen tarda más que un JSON
TAMAÑO_TROZO = 64 * 1024  # 64 KB por trozo al descargar
MAX_GENEROS = 3
MAX_AUTORES = 3
# Open Library pide identificar la aplicación. Si agregas un correo de contacto,
# p. ej. "libreria-m7/0.1 (tu@correo.com)", te permite más peticiones por segundo.
CABECERAS = {"User-Agent": "libreria-m7/0.1 (proyecto del curso de Python)"}


class DatosISBN(BaseModel):
    """Datos que Open Library conoce de un libro.

    Todos los campos son opcionales porque la API no siempre los tiene. Son
    *sugerencias* para la captura, no un Libro completo: precio, cantidad y
    nacionalidad del autor siempre los captura el usuario.
    """

    titulo: str = ""
    autor: str = ""
    generos: list[str] = Field(default_factory=list)
    año_publicacion: int | None = None
    editorial: str = ""
    id_portada: int | None = None  # identificador de la portada en covers.openlibrary.org


def normalizar_isbn(isbn: str) -> str:
    """Quita guiones y espacios: '978-607-07-1234-5' -> '9786070712345'."""
    return re.sub(r"[\s-]", "", isbn).upper()


def _extraer_año(fecha: str) -> int | None:
    """Open Library da fechas como '1967', 'May 1967' o '1967-05-30'."""
    coincidencia = re.search(r"\b(\d{4})\b", fecha)
    return int(coincidencia.group(1)) if coincidencia else None


def _nombres(elementos: list[Any]) -> list[str]:
    """Algunas listas vienen como ["Vintage"] y otras como [{"name": "Vintage"}]."""
    resultado: list[str] = []
    for elemento in elementos:
        nombre = elemento.get("name", "") if isinstance(elemento, dict) else str(elemento)
        if nombre:
            resultado.append(nombre)
    return resultado


# Solo se reintentan los errores pasajeros de red (sin conexión, tiempo agotado).
# Un 500 o una respuesta rara no se arreglan volviendo a intentar.
@reintentar(
    intentos=2,
    espera_inicial=0.5,
    excepciones=(httpx.NetworkError, httpx.TimeoutException),
)
def _obtener_json(cliente: httpx.Client, ruta: str) -> dict[str, Any] | None:
    """Pide `ruta` al cliente y devuelve el JSON. Devuelve None si la respuesta es 404.

    En esta API un 404 no es un error: significa "no existe" (p. ej. un ISBN
    que Open Library no tiene registrado).
    """
    respuesta = cliente.get(ruta)  # la URL completa es base_url + ruta
    if respuesta.status_code == 404:
        return None
    respuesta.raise_for_status()  # otros 4xx/5xx -> httpx.HTTPStatusError
    datos: dict[str, Any] = respuesta.json()
    return datos


def _claves_autores(edicion: dict[str, Any], obra: dict[str, Any]) -> list[str]:
    """Claves de autor ('/authors/OL...A'). Se buscan primero en la edición y luego en la obra.

    Formatos: edición -> [{"key": ...}], obra -> [{"author": {"key": ...}}].
    """
    claves = [a["key"] for a in edicion.get("authors", []) if "key" in a]
    if not claves:
        claves = [
            a["author"]["key"]
            for a in obra.get("authors", [])
            if isinstance(a.get("author"), dict) and "key" in a["author"]
        ]
    return claves[:MAX_AUTORES]


def buscar_por_isbn(isbn: str, transporte: httpx.BaseTransport | None = None) -> DatosISBN | None:
    """Busca un libro por ISBN en Open Library.

    Devuelve None si el ISBN no está registrado. Lanza ServicioExternoError si
    no se pudo consultar (sin internet, servidor caído, respuesta inválida).

    `transporte` solo se usa en las pruebas, para responder sin internet
    (httpx.MockTransport). En el programa se deja en None: httpx usa la red.
    """
    isbn_limpio = normalizar_isbn(isbn)
    log.info("Consultando Open Library: ISBN %s", isbn_limpio)

    try:
        # Un solo Client para todas las peticiones: reutiliza la conexión y
        # comparte la configuración. El `with` la cierra al terminar.
        with httpx.Client(
            base_url=URL_BASE,
            headers=CABECERAS,
            timeout=TIMEOUT_SEGUNDOS,
            follow_redirects=True,  # httpx NO sigue redirecciones por defecto
            transport=transporte,
        ) as cliente:
            # 1. La edición. /isbn/... redirige a /books/OL...M.json
            edicion = _obtener_json(cliente, f"/isbn/{isbn_limpio}.json")
            if edicion is None:
                log.info("ISBN no encontrado en Open Library: %s", isbn_limpio)
                return None

            # 2. La obra (opcional): de aquí salen los géneros si la edición no los trae
            obras = edicion.get("works", [])
            obra = (_obtener_json(cliente, f"{obras[0]['key']}.json") if obras else None) or {}

            # 3. Un GET por autor para obtener su nombre
            autores: list[str] = []
            for clave in _claves_autores(edicion, obra):
                autor = _obtener_json(cliente, f"{clave}.json") or {}
                if autor.get("name"):
                    autores.append(autor["name"])
    except httpx.HTTPError as e:
        # HTTPError es la base de los errores de httpx: de red y de código 4xx/5xx
        raise ServicioExternoError(f"No se pudo consultar Open Library: {e}") from e
    except json.JSONDecodeError as e:
        # A diferencia de requests, httpx no envuelve este error: .json() lanza
        # directamente el de la biblioteca estándar.
        raise ServicioExternoError(f"Open Library respondió algo que no es JSON: {e}") from e

    generos = _nombres(edicion.get("subjects") or obra.get("subjects", []))
    datos = DatosISBN(
        titulo=edicion.get("title") or obra.get("title", ""),
        autor=", ".join(autores),
        generos=generos[:MAX_GENEROS],
        año_publicacion=_extraer_año(edicion.get("publish_date", "")),
        editorial=next(iter(_nombres(edicion.get("publishers", []))), ""),
        # "covers" es una lista de ids; Open Library usa -1 para portadas eliminadas
        id_portada=next(
            (c for c in edicion.get("covers", []) if isinstance(c, int) and c > 0), None
        ),
    )
    log.info("Encontrado en Open Library: %s", datos.titulo)
    return datos


def nombre_archivo_portada(isbn: str) -> str:
    """Nombre de archivo seguro para la portada: '978-0-307-47472-8' -> '9780307474728.jpg'.

    Solo deja letras y números, para que un ISBN mal escrito (con '/', por
    ejemplo) no pueda crear rutas raras.
    """
    return f"{re.sub(r'[^0-9A-Za-z]', '', isbn) or 'portada'}.jpg"


@reintentar(
    intentos=2,
    espera_inicial=0.5,
    excepciones=(httpx.NetworkError, httpx.TimeoutException),
)
def _descargar_a_archivo(cliente: httpx.Client, ruta: str, archivo: Path) -> int:
    """Descarga `ruta` por streaming y la escribe en `archivo`, trozo por trozo.

    Devuelve los bytes escritos. Si se reintenta, "wb" vuelve a empezar el
    archivo desde cero.
    """
    escritos = 0
    # cliente.stream() no descarga el cuerpo al hacer la petición: se lee en el for
    with cliente.stream("GET", ruta) as respuesta:
        respuesta.raise_for_status()
        with open(archivo, "wb") as f:
            for trozo in respuesta.iter_bytes(chunk_size=TAMAÑO_TROZO):
                f.write(trozo)
                escritos += len(trozo)
    return escritos


def descargar_portada(
    id_portada: int, destino: Path, transporte: httpx.BaseTransport | None = None
) -> Path:
    """Descarga la portada `id_portada` (tamaño grande) a `destino` por streaming.

    Se escribe primero en un archivo `.part` y solo se renombra a `destino` si
    la descarga terminó completa; si falla, no queda ningún archivo a medias.
    Lanza ServicioExternoError si no se pudo descargar.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.name + ".part")
    log.info("Descargando portada %d a %s", id_portada, destino)

    try:
        with httpx.Client(
            base_url=URL_PORTADAS,
            headers=CABECERAS,
            timeout=TIMEOUT_DESCARGA,
            follow_redirects=True,  # la imagen real está alojada en archive.org
            transport=transporte,
        ) as cliente:
            # /b/id/ en lugar de /b/isbn/: por ISBN, Open Library limita las consultas
            escritos = _descargar_a_archivo(cliente, f"/b/id/{id_portada}-L.jpg", temporal)
        temporal.replace(destino)  # solo llega aquí si la descarga terminó
    except httpx.HTTPError as e:
        raise ServicioExternoError(f"No se pudo descargar la portada: {e}") from e
    except OSError as e:  # disco lleno, sin permisos en la carpeta, etc.
        raise ServicioExternoError(f"No se pudo guardar la portada: {e}") from e
    finally:
        temporal.unlink(missing_ok=True)  # si falló, borra el archivo a medias

    log.info("Portada guardada: %s (%d bytes)", destino, escritos)
    return destino
