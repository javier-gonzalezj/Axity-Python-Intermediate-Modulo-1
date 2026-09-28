"""Persistencia en SQLite con SQLAlchemy: Usuario / Pedido / PedidoItem.

Tablas:
    libros        catálogo (lo que hoy vive en libreria.json)
    usuarios      clientes de la librería
    pedidos       un pedido pertenece a un usuario            (1 usuario -> N pedidos)
    pedido_items  cada línea del pedido: libro + cantidad     (1 pedido  -> N items)

    usuarios 1 ──< pedidos 1 ──< pedido_items >── 1 libros

El esquema de la base lo administra Alembic (carpeta `migraciones/`). Las clases
*DB de este módulo son la "fuente de verdad": si cambias una, genera una
migración con `alembic revision --autogenerate -m "..."`.

Hacia afuera, las funciones reciben y devuelven los modelos pydantic del
proyecto (Libro, Usuario, Pedido), así el resto del programa no depende de
SQLAlchemy.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    JSON,
    CheckConstraint,
    Engine,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
    create_engine,
    event,
    func,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from libreria.excepciones import LibreriaError, LibroInvalidoError
from libreria.modelos import Autor, Libreria, Libro

log = logging.getLogger(__name__)

URL_BD = "sqlite:///data/libreria.db"


# ---------------------------------------------------------------------------
# Excepciones nuevas
# ---------------------------------------------------------------------------
class UsuarioNoEncontradoError(LibreriaError):
    """El usuario indicado no existe."""


class PedidoNoEncontradoError(LibreriaError):
    """El pedido indicado no existe."""


class StockInsuficienteError(LibreriaError):
    """No hay suficientes ejemplares para surtir el pedido."""


class LibroNoEncontradoError(LibroInvalidoError):
    """El libro indicado no existe en la base."""


class RegistroEnUsoError(LibreriaError):
    """No se puede borrar un registro porque otros dependen de él (p. ej. tiene pedidos)."""


class TransicionEstatusError(LibreriaError):
    """El pedido no puede pasar de su estatus actual al solicitado."""


# Estatus al que puede pasar un pedido desde cada estatus
TRANSICIONES: dict[str, set[str]] = {
    "pendiente": {"pagado", "cancelado"},
    "pagado": {"enviado", "cancelado"},
    "enviado": set(),  # ya salió: no se puede cancelar
    "cancelado": set(),
}


# ---------------------------------------------------------------------------
# Tablas (modelos de SQLAlchemy)
# ---------------------------------------------------------------------------
# Nombres fijos para índices y restricciones. Alembic los necesita para poder
# modificarlos o borrarlos después (sobre todo en SQLite, con batch mode).
CONVENCION_NOMBRES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCION_NOMBRES)


class LibroDB(Base):
    __tablename__ = "libros"
    __table_args__ = (
        CheckConstraint("año_publicacion BETWEEN 0 AND 2100", name="año_valido"),
        CheckConstraint("precio >= 0", name="precio_positivo"),
        CheckConstraint("cantidad_disponible >= 0", name="cantidad_positiva"),
    )

    isbn: Mapped[str] = mapped_column(String(20), primary_key=True)
    titulo: Mapped[str] = mapped_column(String(200))
    autor_nombre: Mapped[str] = mapped_column(String(100))
    autor_nacionalidad: Mapped[str] = mapped_column(String(50), default="")
    generos: Mapped[list[str]] = mapped_column(JSON)  # lista guardada como JSON
    año_publicacion: Mapped[int] = mapped_column(Integer)
    precio: Mapped[float] = mapped_column(Float)
    cantidad_disponible: Mapped[int] = mapped_column(Integer)
    editorial: Mapped[str] = mapped_column(String(100))


class UsuarioDB(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    telefono: Mapped[str | None] = mapped_column(String(20))  # agregado en la migración 0002

    pedidos: Mapped[list["PedidoDB"]] = relationship(back_populates="usuario")


class PedidoDB(Base):
    __tablename__ = "pedidos"
    __table_args__ = (
        CheckConstraint(
            "estatus IN ('pendiente', 'pagado', 'enviado', 'cancelado')", name="estatus_valido"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    fecha: Mapped[datetime] = mapped_column(default=datetime.now)
    estatus: Mapped[str] = mapped_column(String(20), default="pendiente")

    usuario: Mapped[UsuarioDB] = relationship(back_populates="pedidos")
    # delete-orphan: una línea no existe sin su pedido
    items: Mapped[list["PedidoItemDB"]] = relationship(
        back_populates="pedido", cascade="all, delete-orphan"
    )


class PedidoItemDB(Base):
    __tablename__ = "pedido_items"
    __table_args__ = (
        UniqueConstraint("pedido_id", "isbn"),  # un libro aparece una vez por pedido
        CheckConstraint("cantidad > 0", name="cantidad_positiva"),
        CheckConstraint("precio_unitario >= 0", name="precio_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedidos.id", ondelete="CASCADE"), index=True)
    isbn: Mapped[str] = mapped_column(ForeignKey("libros.isbn"))
    cantidad: Mapped[int] = mapped_column(Integer)
    precio_unitario: Mapped[float] = mapped_column(Float)  # precio AL MOMENTO de la compra

    pedido: Mapped[PedidoDB] = relationship(back_populates="items")
    libro: Mapped[LibroDB] = relationship()


# ---------------------------------------------------------------------------
# Modelos pydantic (lo que ve el resto del programa)
# ---------------------------------------------------------------------------
class Usuario(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: int | None = None  # None mientras no se guarde en la base
    nombre: str = Field(min_length=1)
    email: str = Field(min_length=3)
    telefono: str | None = None


class PedidoItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    isbn: str
    titulo: str
    cantidad: int = Field(gt=0)
    precio_unitario: float = Field(ge=0)

    @property
    def subtotal(self) -> float:
        return round(self.cantidad * self.precio_unitario, 2)


class Pedido(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    usuario_id: int
    fecha: datetime
    estatus: str
    items: list[PedidoItem]

    @property
    def total(self) -> float:
        return round(sum(item.subtotal for item in self.items), 2)


# ---------------------------------------------------------------------------
# Motor (conexión)
# ---------------------------------------------------------------------------
def crear_motor(url: str = URL_BD, echo: bool = False) -> Engine:
    """Crea el motor de SQLAlchemy. Con echo=True imprime el SQL que genera."""
    motor = create_engine(url, echo=echo)

    if motor.dialect.name == "sqlite":

        @event.listens_for(motor, "connect")
        def _activar_llaves_foraneas(conexion: Any, _registro: Any) -> None:
            # En SQLite vienen apagadas y hay que encenderlas en cada conexión
            cursor = conexion.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.close()

    return motor


def crear_esquema(motor: Engine) -> None:
    """Crea las tablas directamente, SIN Alembic.

    Solo para pruebas con bases temporales (sqlite:// en memoria). La base real
    se crea y actualiza con `alembic upgrade head`.
    """
    Base.metadata.create_all(motor)


# ---------------------------------------------------------------------------
# Conversiones entre tablas y modelos pydantic
# ---------------------------------------------------------------------------
def _a_libro(fila: LibroDB) -> Libro:
    return Libro(
        isbn=fila.isbn,
        titulo=fila.titulo,
        autor=Autor(nombre=fila.autor_nombre, nacionalidad=fila.autor_nacionalidad),
        genero=list(fila.generos),
        año_publicacion=fila.año_publicacion,
        precio=fila.precio,
        en_stock=fila.cantidad_disponible > 0,  # se deriva, no se guarda
        cantidad_disponible=fila.cantidad_disponible,
        editorial=fila.editorial,
    )


def _a_libro_db(libro: Libro) -> LibroDB:
    return LibroDB(
        isbn=libro.isbn,
        titulo=libro.titulo,
        autor_nombre=libro.autor.nombre,
        autor_nacionalidad=libro.autor.nacionalidad,
        generos=libro.genero,
        año_publicacion=libro.año_publicacion,
        precio=libro.precio,
        cantidad_disponible=libro.cantidad_disponible,
        editorial=libro.editorial,
    )


def _a_usuario(fila: UsuarioDB) -> Usuario:
    return Usuario(id=fila.id, nombre=fila.nombre, email=fila.email, telefono=fila.telefono)


def _a_pedido(fila: PedidoDB) -> Pedido:
    return Pedido(
        id=fila.id,
        usuario_id=fila.usuario_id,
        fecha=fila.fecha,
        estatus=fila.estatus,
        items=[
            PedidoItem(
                isbn=item.isbn,
                titulo=item.libro.titulo,
                cantidad=item.cantidad,
                precio_unitario=item.precio_unitario,
            )
            for item in sorted(fila.items, key=lambda i: i.libro.titulo)
        ],
    )


# ---------------------------------------------------------------------------
# Libros
# ---------------------------------------------------------------------------
def guardar_libro(sesion: Session, libro: Libro) -> None:
    if sesion.get(LibroDB, libro.isbn) is not None:
        raise LibroInvalidoError(f"Ya existe un libro con ISBN {libro.isbn}")

    sesion.add(_a_libro_db(libro))
    sesion.commit()


def importar_catalogo(sesion: Session, data: Libreria) -> int:
    """Migra los libros que ya cargó almacenamiento.cargar_datos() a la base.

    Los ISBN que ya existen se saltan. Devuelve cuántos libros se agregaron.
    """
    existentes = set(sesion.scalars(select(LibroDB.isbn)))
    nuevos = [libro for libro in data["libros"] if libro.isbn not in existentes]

    sesion.add_all(_a_libro_db(libro) for libro in nuevos)
    sesion.commit()

    log.info("Catálogo importado: %d libros nuevos", len(nuevos))
    return len(nuevos)


def obtener_libro(sesion: Session, isbn: str) -> Libro | None:
    fila = sesion.get(LibroDB, isbn)
    return _a_libro(fila) if fila else None


def listar_libros(sesion: Session) -> list[Libro]:
    filas = sesion.scalars(select(LibroDB).order_by(LibroDB.titulo))
    return [_a_libro(fila) for fila in filas]


def actualizar_libro(
    sesion: Session,
    isbn: str,
    *,
    precio: float | None = None,
    cantidad_disponible: int | None = None,
    titulo: str | None = None,
    editorial: str | None = None,
) -> Libro:
    """Cambia los campos indicados; los que se dejan en None no se tocan.

    Los datos nuevos pasan por el modelo Libro antes de guardarse, así se
    aplican las mismas reglas (precio >= 0, título no vacío, etc.).
    """
    fila = sesion.get(LibroDB, isbn)
    if fila is None:
        raise LibroNoEncontradoError(f"No existe el libro {isbn}")

    cambios: dict[str, Any] = {
        "precio": precio,
        "cantidad_disponible": cantidad_disponible,
        "titulo": titulo,
        "editorial": editorial,
    }
    cambios = {campo: valor for campo, valor in cambios.items() if valor is not None}
    if "cantidad_disponible" in cambios:
        cambios["en_stock"] = cambios["cantidad_disponible"] > 0

    actualizado = Libro.desde_dict({**_a_libro(fila).a_dict(), **cambios})  # valida

    fila.precio = actualizado.precio
    fila.cantidad_disponible = actualizado.cantidad_disponible
    fila.titulo = actualizado.titulo
    fila.editorial = actualizado.editorial
    sesion.commit()
    log.info("Libro %s actualizado: %s", isbn, cambios)
    return actualizado


def eliminar_libro(sesion: Session, isbn: str) -> None:
    """Borra un libro del catálogo, solo si nunca se ha vendido."""
    fila = sesion.get(LibroDB, isbn)
    if fila is None:
        raise LibroNoEncontradoError(f"No existe el libro {isbn}")

    vendido = sesion.scalar(select(PedidoItemDB.id).where(PedidoItemDB.isbn == isbn).limit(1))
    if vendido is not None:
        raise RegistroEnUsoError(
            f"'{fila.titulo}' aparece en pedidos; no se puede borrar. "
            "Deja su cantidad en 0 para retirarlo de la venta."
        )

    sesion.delete(fila)
    sesion.commit()
    log.info("Libro %s eliminado", isbn)


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
def crear_usuario(sesion: Session, nombre: str, email: str, telefono: str | None = None) -> Usuario:
    usuario = Usuario(nombre=nombre, email=email, telefono=telefono)  # valida primero
    fila = UsuarioDB(nombre=usuario.nombre, email=usuario.email, telefono=usuario.telefono)
    sesion.add(fila)
    try:
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        raise LibreriaError(f"Ya existe un usuario con email {usuario.email}") from None

    return _a_usuario(fila)  # después del commit, fila.id ya tiene valor


def obtener_usuario(sesion: Session, usuario_id: int) -> Usuario | None:
    fila = sesion.get(UsuarioDB, usuario_id)
    return _a_usuario(fila) if fila else None


def buscar_usuario_por_email(sesion: Session, email: str) -> Usuario | None:
    fila = sesion.scalar(select(UsuarioDB).where(UsuarioDB.email == email.strip()))
    return _a_usuario(fila) if fila else None


def listar_usuarios(sesion: Session) -> list[Usuario]:
    filas = sesion.scalars(select(UsuarioDB).order_by(UsuarioDB.nombre))
    return [_a_usuario(fila) for fila in filas]


def actualizar_usuario(
    sesion: Session,
    usuario_id: int,
    *,
    nombre: str | None = None,
    email: str | None = None,
    telefono: str | None = None,
) -> Usuario:
    """Cambia los campos indicados; los que se dejan en None no se tocan."""
    fila = sesion.get(UsuarioDB, usuario_id)
    if fila is None:
        raise UsuarioNoEncontradoError(f"No existe el usuario {usuario_id}")

    actualizado = Usuario(  # valida los datos nuevos con las reglas del modelo
        id=fila.id,
        nombre=nombre if nombre is not None else fila.nombre,
        email=email if email is not None else fila.email,
        telefono=telefono if telefono is not None else fila.telefono,
    )
    fila.nombre = actualizado.nombre
    fila.email = actualizado.email
    fila.telefono = actualizado.telefono
    try:
        sesion.commit()
    except IntegrityError:
        sesion.rollback()
        raise LibreriaError(f"Ya existe un usuario con email {actualizado.email}") from None

    log.info("Usuario %s actualizado", usuario_id)
    return actualizado


def eliminar_usuario(sesion: Session, usuario_id: int) -> None:
    """Borra un usuario, solo si no tiene pedidos (para no perder el historial de ventas)."""
    fila = sesion.get(UsuarioDB, usuario_id)
    if fila is None:
        raise UsuarioNoEncontradoError(f"No existe el usuario {usuario_id}")
    if fila.pedidos:
        raise RegistroEnUsoError(
            f"{fila.nombre} tiene {len(fila.pedidos)} pedido(s); no se puede borrar"
        )

    sesion.delete(fila)
    sesion.commit()
    log.info("Usuario %s eliminado", usuario_id)


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------
def crear_pedido(sesion: Session, usuario_id: int, lineas: dict[str, int]) -> Pedido:
    """Crea un pedido a partir de {isbn: cantidad}.

    Todo ocurre en UNA transacción: si un solo libro falla (no existe o no hay
    stock), se hace rollback y ni el pedido ni el inventario cambian.
    """
    if not lineas:
        raise LibreriaError("El pedido no tiene libros")

    try:
        if sesion.get(UsuarioDB, usuario_id) is None:
            raise UsuarioNoEncontradoError(f"No existe el usuario {usuario_id}")

        pedido = PedidoDB(usuario_id=usuario_id)
        for isbn, cantidad in lineas.items():
            if cantidad <= 0:
                raise LibreriaError(f"Cantidad inválida para {isbn}: {cantidad}")

            libro = sesion.get(LibroDB, isbn)
            if libro is None:
                raise LibroInvalidoError(f"No existe el libro {isbn}")
            if libro.cantidad_disponible < cantidad:
                raise StockInsuficienteError(
                    f"'{libro.titulo}': pediste {cantidad}, hay {libro.cantidad_disponible}"
                )

            libro.cantidad_disponible -= cantidad
            pedido.items.append(
                PedidoItemDB(libro=libro, cantidad=cantidad, precio_unitario=libro.precio)
            )

        sesion.add(pedido)
        sesion.commit()
    except Exception:
        sesion.rollback()  # deshace los cambios de stock que ya se habían hecho
        raise

    log.info("Pedido %s creado para usuario %s", pedido.id, usuario_id)
    return _a_pedido(pedido)


def obtener_pedido(sesion: Session, pedido_id: int) -> Pedido | None:
    fila = sesion.get(PedidoDB, pedido_id)
    return _a_pedido(fila) if fila else None


def pedidos_de_usuario(sesion: Session, usuario_id: int) -> list[Pedido]:
    filas = sesion.scalars(
        select(PedidoDB).where(PedidoDB.usuario_id == usuario_id).order_by(PedidoDB.fecha)
    )
    return [_a_pedido(fila) for fila in filas]


def listar_pedidos(sesion: Session, estatus: str | None = None) -> list[Pedido]:
    """Todos los pedidos, o solo los de un estatus."""
    consulta = select(PedidoDB).order_by(PedidoDB.fecha)
    if estatus is not None:
        consulta = consulta.where(PedidoDB.estatus == estatus)
    return [_a_pedido(fila) for fila in sesion.scalars(consulta)]


def cambiar_estatus(sesion: Session, pedido_id: int, nuevo: str) -> Pedido:
    """Avanza el pedido: pendiente -> pagado -> enviado.

    Para cancelar usa cancelar_pedido(), que además regresa el stock.
    """
    if nuevo == "cancelado":
        cancelar_pedido(sesion, pedido_id)
    else:
        pedido = sesion.get(PedidoDB, pedido_id)
        if pedido is None:
            raise PedidoNoEncontradoError(f"No existe el pedido {pedido_id}")
        if nuevo not in TRANSICIONES.get(pedido.estatus, set()):
            raise TransicionEstatusError(
                f"El pedido {pedido_id} no puede pasar de '{pedido.estatus}' a '{nuevo}'"
            )
        pedido.estatus = nuevo
        sesion.commit()
        log.info("Pedido %s ahora está %s", pedido_id, nuevo)

    resultado = obtener_pedido(sesion, pedido_id)
    assert resultado is not None
    return resultado


def cancelar_pedido(sesion: Session, pedido_id: int) -> None:
    """Marca el pedido como cancelado y regresa los libros al inventario (soft delete).

    Cancelar un pedido ya cancelado no hace nada; uno enviado no se puede cancelar.
    """
    pedido = sesion.get(PedidoDB, pedido_id)
    if pedido is None:
        raise PedidoNoEncontradoError(f"No existe el pedido {pedido_id}")
    if pedido.estatus == "cancelado":
        return
    if "cancelado" not in TRANSICIONES[pedido.estatus]:
        raise TransicionEstatusError(
            f"El pedido {pedido_id} ya está '{pedido.estatus}'; no se puede cancelar"
        )

    for item in pedido.items:
        item.libro.cantidad_disponible += item.cantidad
    pedido.estatus = "cancelado"
    sesion.commit()
    log.info("Pedido %s cancelado", pedido_id)


# ---------------------------------------------------------------------------
# Reportes
# ---------------------------------------------------------------------------
def total_por_usuario(sesion: Session) -> list[tuple[str, int, float]]:
    """(nombre, número de pedidos, total gastado), sin contar cancelados."""
    total = func.round(func.sum(PedidoItemDB.cantidad * PedidoItemDB.precio_unitario), 2)
    consulta = (
        select(UsuarioDB.nombre, func.count(func.distinct(PedidoDB.id)), total)
        .join(PedidoDB, PedidoDB.usuario_id == UsuarioDB.id)
        .join(PedidoItemDB, PedidoItemDB.pedido_id == PedidoDB.id)
        .where(PedidoDB.estatus != "cancelado")
        .group_by(UsuarioDB.id)
        .order_by(total.desc())
    )
    return [(nombre, pedidos, gasto) for nombre, pedidos, gasto in sesion.execute(consulta)]


def libros_mas_vendidos(sesion: Session, limite: int = 5) -> list[tuple[str, int]]:
    vendidos = func.sum(PedidoItemDB.cantidad)
    consulta = (
        select(LibroDB.titulo, vendidos)
        .join(PedidoItemDB, PedidoItemDB.isbn == LibroDB.isbn)
        .join(PedidoDB, PedidoDB.id == PedidoItemDB.pedido_id)
        .where(PedidoDB.estatus != "cancelado")
        .group_by(LibroDB.isbn)
        .order_by(vendidos.desc())
        .limit(limite)
    )
    return [(titulo, cantidad) for titulo, cantidad in sesion.execute(consulta)]


# ---------------------------------------------------------------------------
# Uso directo: poetry run python -m libreria.basedatos
# ---------------------------------------------------------------------------
def main() -> None:
    """Importa data/libreria.json a data/libreria.db (después de `alembic upgrade head`)."""
    from libreria.almacenamiento import cargar_datos

    if not Path("data/libreria.db").exists():
        print("No existe data/libreria.db. Primero ejecuta: poetry run alembic upgrade head")
        return

    with Session(crear_motor()) as sesion:
        nuevos = importar_catalogo(sesion, cargar_datos("data/libreria.json"))
    print(f"Libros importados: {nuevos}")


if __name__ == "__main__":
    main()
