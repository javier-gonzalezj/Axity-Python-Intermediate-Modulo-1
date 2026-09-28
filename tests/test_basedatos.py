"""Pruebas de pedidos y reportes de basedatos.py.

La fixture `sesion` (en conftest.py) da a cada prueba una base SQLite en
memoria nueva, con el catálogo de libreria.json ya importado.
"""

import pytest
from sqlalchemy.orm import Session

from libreria import basedatos as bd
from libreria.almacenamiento import cargar_datos
from libreria.excepciones import LibreriaError, LibroInvalidoError
from tests.conftest import CATALOGO

CIEN_AÑOS = "978-607-07-1234-5"  # 12 ejemplares, $349.90
NOVENTA_OCHENTA_Y_CUATRO = "978-607-11-9876-3"  # 1984: 0 ejemplares
RAYUELA = "978-84-9793-563-2"  # 5 ejemplares, $399.50


def stock(sesion: Session, isbn: str) -> int:
    libro = bd.obtener_libro(sesion, isbn)
    assert libro is not None
    return libro.cantidad_disponible


def test_importar_catalogo_no_duplica(sesion: Session) -> None:
    total = len(bd.listar_libros(sesion))
    assert total > 0
    assert bd.importar_catalogo(sesion, cargar_datos(CATALOGO)) == 0
    assert len(bd.listar_libros(sesion)) == total


def test_libro_ida_y_vuelta_conserva_datos(sesion: Session) -> None:
    original = next(libro for libro in cargar_datos(CATALOGO)["libros"] if libro.isbn == CIEN_AÑOS)
    assert bd.obtener_libro(sesion, CIEN_AÑOS) == original


def test_email_repetido(sesion: Session) -> None:
    bd.crear_usuario(sesion, "Ana", "ana@mail.com")
    with pytest.raises(LibreriaError, match="email"):
        bd.crear_usuario(sesion, "Otra Ana", "ana@mail.com")


def test_crear_pedido_calcula_total_y_descuenta_stock(sesion: Session) -> None:
    ana = bd.crear_usuario(sesion, "Ana", "ana@mail.com", telefono="55-1234-5678")
    assert ana.id is not None

    pedido = bd.crear_pedido(sesion, ana.id, {CIEN_AÑOS: 2, RAYUELA: 1})

    assert pedido.estatus == "pendiente"
    assert len(pedido.items) == 2
    assert pedido.total == pytest.approx(2 * 349.90 + 399.50)
    assert stock(sesion, CIEN_AÑOS) == 10
    assert stock(sesion, RAYUELA) == 4


def test_pedido_sin_stock_no_cambia_nada(sesion: Session) -> None:
    luis = bd.crear_usuario(sesion, "Luis", "luis@mail.com")
    assert luis.id is not None

    with pytest.raises(bd.StockInsuficienteError):
        bd.crear_pedido(sesion, luis.id, {RAYUELA: 1, NOVENTA_OCHENTA_Y_CUATRO: 1})

    assert stock(sesion, RAYUELA) == 5  # el rollback regresó el descuento
    assert bd.pedidos_de_usuario(sesion, luis.id) == []


def test_pedido_con_errores(sesion: Session) -> None:
    ana = bd.crear_usuario(sesion, "Ana", "ana@mail.com")
    assert ana.id is not None

    with pytest.raises(bd.UsuarioNoEncontradoError):
        bd.crear_pedido(sesion, 999, {CIEN_AÑOS: 1})
    with pytest.raises(LibroInvalidoError):
        bd.crear_pedido(sesion, ana.id, {"no-existe": 1})
    with pytest.raises(LibreriaError):
        bd.crear_pedido(sesion, ana.id, {})


def test_precio_del_pedido_no_cambia_si_cambia_el_catalogo(sesion: Session) -> None:
    ana = bd.crear_usuario(sesion, "Ana", "ana@mail.com")
    assert ana.id is not None
    pedido = bd.crear_pedido(sesion, ana.id, {RAYUELA: 1})

    libro_db = sesion.get(bd.LibroDB, RAYUELA)
    assert libro_db is not None
    libro_db.precio = 999.0
    sesion.commit()

    guardado = bd.obtener_pedido(sesion, pedido.id)
    assert guardado is not None
    assert guardado.total == pytest.approx(399.50)


def test_cancelar_regresa_stock_y_sale_de_reportes(sesion: Session) -> None:
    ana = bd.crear_usuario(sesion, "Ana", "ana@mail.com")
    luis = bd.crear_usuario(sesion, "Luis", "luis@mail.com")
    assert ana.id is not None and luis.id is not None

    pedido_ana = bd.crear_pedido(sesion, ana.id, {CIEN_AÑOS: 2, RAYUELA: 1})
    bd.crear_pedido(sesion, luis.id, {CIEN_AÑOS: 1})

    assert bd.total_por_usuario(sesion) == [
        ("Ana", 1, pytest.approx(1099.30)),
        ("Luis", 1, pytest.approx(349.90)),
    ]
    assert bd.libros_mas_vendidos(sesion)[0] == ("Cien años de soledad", 3)

    bd.cancelar_pedido(sesion, pedido_ana.id)
    bd.cancelar_pedido(sesion, pedido_ana.id)  # cancelar dos veces no regresa stock doble

    assert stock(sesion, CIEN_AÑOS) == 11
    assert stock(sesion, RAYUELA) == 5
    assert bd.total_por_usuario(sesion) == [("Luis", 1, pytest.approx(349.90))]
