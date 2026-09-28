from typing import Any, Self, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from libreria.excepciones import LibroInvalidoError


class Autor(BaseModel):
    """Autor de un libro. Se ordena alfabéticamente por nombre y luego por nacionalidad."""

    model_config = ConfigDict(
        frozen=True,  # inmutable y "hasheable": se puede meter en un set
        extra="forbid",  # rechaza campos que no estén declarados
        str_strip_whitespace=True,  # quita espacios al inicio y al final de los textos
    )

    nombre: str = Field(min_length=1)
    nacionalidad: str = ""

    def __lt__(self, otro: object) -> bool:
        if not isinstance(otro, Autor):
            return NotImplemented
        return (self.nombre, self.nacionalidad) < (otro.nombre, otro.nacionalidad)


class Libro(BaseModel):
    """Libro del catálogo.

    Se ordena por año de publicación, luego por título y al final por ISBN.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,  # también valida al hacer libro.precio = ...
    )

    isbn: str = Field(min_length=1)
    titulo: str = Field(min_length=1)
    autor: Autor
    genero: list[str]
    año_publicacion: int = Field(ge=0, le=2100)
    precio: float = Field(ge=0)
    en_stock: bool
    cantidad_disponible: int = Field(ge=0)
    editorial: str

    def __lt__(self, otro: object) -> bool:
        if not isinstance(otro, Libro):
            return NotImplemented
        return (self.año_publicacion, self.titulo, self.isbn) < (
            otro.año_publicacion,
            otro.titulo,
            otro.isbn,
        )

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> Self:
        """Crea un Libro a partir de un diccionario como los del archivo JSON."""
        try:
            return cls.model_validate(datos)
        except ValidationError as e:
            raise LibroInvalidoError(f"Libro inválido:\n{e}") from None

    def a_dict(self) -> dict[str, Any]:
        """Convierte el Libro (incluyendo su Autor) a diccionario para guardarlo en JSON."""
        return self.model_dump()


class Direccion(TypedDict):
    """Dirección de la librería, tal como aparece en el archivo JSON."""

    calle: str
    colonia: str
    ciudad: str
    cp: str


class Libreria(TypedDict):
    """Datos completos de la librería una vez cargados.

    Es un diccionario normal en tiempo de ejecución; el TypedDict solo le dice
    a mypy qué claves tiene y de qué tipo es cada una.
    """

    nombre: str
    direccion: Direccion
    telefono: str
    horario: str
    libros: list[Libro]
