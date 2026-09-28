"""Configuración del logging del programa.

Solo main.py llama a configurar_logging(); el resto de los módulos únicamente
crean su logger con logging.getLogger(__name__) y escriben mensajes.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMATO_ARCHIVO = "%(asctime)s %(levelname)-8s %(name)s:%(lineno)d  %(message)s"
FORMATO_CONSOLA = "⚠️  %(message)s"


def configurar_logging(carpeta: Path, nivel_archivo: int = logging.DEBUG) -> Path:
    """Envía el detalle completo a un archivo y solo las advertencias a la consola.

    Devuelve la ruta del archivo de log.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_log = carpeta / "libreria.log"

    # Archivo: todo el detalle. Rota al llegar a 1 MB y guarda 3 respaldos.
    archivo = RotatingFileHandler(ruta_log, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    archivo.setLevel(nivel_archivo)
    archivo.setFormatter(logging.Formatter(FORMATO_ARCHIVO, datefmt="%Y-%m-%d %H:%M:%S"))

    # Consola: solo WARNING. Los errores ya se los muestra main.py al usuario
    # con print("❌ ..."), así que el filtro evita que salgan repetidos.
    consola = logging.StreamHandler()
    consola.setLevel(logging.WARNING)
    consola.addFilter(lambda registro: registro.levelno < logging.ERROR)
    consola.setFormatter(logging.Formatter(FORMATO_CONSOLA))

    raiz = logging.getLogger()
    raiz.setLevel(logging.DEBUG)  # el logger deja pasar todo; cada handler filtra
    raiz.addHandler(archivo)
    raiz.addHandler(consola)

    return ruta_log
