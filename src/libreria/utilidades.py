import functools
import logging
import os
import random
import tempfile
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

log = logging.getLogger(__name__)


def reintentar[**P, R](
    intentos: int = 3,
    espera_inicial: float = 0.5,
    factor: float = 2.0,
    espera_maxima: float = 10.0,
    excepciones: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Reintenta la función decorada con backoff exponencial y jitter.

    Solo reintenta si la excepción es de alguno de los tipos en `excepciones`.
    Tras el último intento fallido, la excepción se propaga sin cambios.
    """
    if intentos < 1:
        raise ValueError("intentos debe ser al menos 1")

    def decorador(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def envoltura(*args: P.args, **kwargs: P.kwargs) -> R:
            for intento in range(1, intentos + 1):
                try:
                    return func(*args, **kwargs)
                except excepciones as e:
                    if intento == intentos:
                        log.error("%s falló tras %d intentos", func.__name__, intentos)
                        raise
                    espera = min(espera_inicial * factor ** (intento - 1), espera_maxima)
                    espera = random.uniform(0, espera)
                    log.warning(
                        "%s falló (%s). Intento %d/%d, reintentando en %.2fs",
                        func.__name__,
                        e,
                        intento,
                        intentos,
                        espera,
                    )
                    time.sleep(espera)
            # Nunca se llega aquí: el último intento siempre retorna o relanza.
            # Este raise existe para que mypy no reporte "Missing return statement".
            raise AssertionError("reintentar: el bucle terminó sin retornar")

        return envoltura

    return decorador


@reintentar(intentos=3, espera_inicial=0.2, excepciones=(PermissionError,))
def _reemplazar(origen: str | Path, destino: str | Path) -> None:
    """Reemplaza `destino` por `origen`.

    En Windows, os.replace puede fallar con PermissionError si otro proceso
    (antivirus, editor, indexador) tiene el archivo abierto un instante.
    """
    os.replace(origen, destino)


@contextmanager
def cronometro(etiqueta: str = "Bloque") -> Generator[None]:
    """Context manager de temporizacion: Imprime cuanto tiempo
    tardo en ejecutarse el bloque with aunque falle.
    """
    inicio = time.perf_counter()
    try:
        yield
    finally:
        duracion = time.perf_counter() - inicio
        log.debug("%s: %.4fs", etiqueta, duracion)


@contextmanager
def escritura_atomica(ruta: str | Path, encoding: str = "utf-8") -> Generator[TextIO]:
    """Escribe en un archivo temporal y reemplaza `ruta` solo si todo salió bien.

    Si ocurre un error durante la escritura, el archivo original queda intacto.
    """
    ruta = Path(ruta)
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            yield f
        _reemplazar(tmp, ruta)
    except BaseException:
        os.remove(tmp)
        raise
