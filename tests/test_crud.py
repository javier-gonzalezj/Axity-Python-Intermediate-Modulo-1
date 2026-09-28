"""Pruebas del CRUD de usuarios, libros y estatus de pedidos (base en memoria)."""

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from libreria import basedatos as bd
from libreria.excepciones import LibreriaError, LibroInvalidoError

CIEN_AÑOS = "978-607-07-1234-5"  # 12 ejemplares, $349.90
RAYUELA = "978-84-9793-563-2"  # 5 ejemplares, $399.50


def nuevo_usuario(sesion: Session, nombre: str = "Ana", email: str = "ana@mail.com") -> int:
    usuario = bd.crear_usuario(sesion, nombre, email)
    assert usuario.id is not None
    return usuario.id


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------
class TestUsuarios:
    def test_crear_y_leer(self, sesion: Session) -> None:
        ana_id = nuevo_usuario(sesion)
        nuevo_usuario(sesion, "Beto", "beto@mail.com")

        ana = bd.obtener_usuario(sesion, ana_id)
        assert ana is not None
        assert (ana.nombre, ana.email, ana.telefono) == ("Ana", "ana@mail.com", None)
        assert bd.buscar_usuario_por_email(sesion, " ana@mail.com ") == ana
        assert [u.nombre for u in bd.listar_usuarios(sesion)] == ["Ana", "Beto"]

    def test_leer_inexistente(self, sesion: Session) -> None:
        assert bd.obtener_usuario(sesion, 999) is None
        assert bd.buscar_usuario_por_email(sesion, "nadie@mail.com") is None

    def test_crear_invalido(self, sesion: Session) -> None:
        with pytest.raises(ValidationError):
            bd.crear_usuario(sesion, "", "ana@mail.com")
        assert bd.listar_usuarios(sesion) == []

    def test_actualizar_solo_campos_indicados(self, sesion: Session) -> None:
        ana_id = nuevo_usuario(sesion)

        bd.actualizar_usuario(sesion, ana_id, telefono="55-1234-5678")
        ana = bd.actualizar_usuario(sesion, ana_id, nombre="Ana López")

        assert ana.nombre == "Ana López"
        assert ana.email == "ana@mail.com"  # no cambió
        assert ana.telefono == "55-1234-5678"  # se conservó del cambio anterior
        assert bd.obtener_usuario(sesion, ana_id) == ana

    def test_actualizar_con_email_de_otro(self, sesion: Session) -> None:
        ana_id = nuevo_usuario(sesion)
        nuevo_usuario(sesion, "Beto", "beto@mail.com")

        with pytest.raises(LibreriaError, match="email"):
            bd.actualizar_usuario(sesion, ana_id, email="beto@mail.com")

        ana = bd.obtener_usuario(sesion, ana_id)
        assert ana is not None and ana.email == "ana@mail.com"  # el rollback lo dejó igual

    def test_actualizar_inexistente(self, sesion: Session) -> None:
        with pytest.raises(bd.UsuarioNoEncontradoError):
            bd.actualizar_usuario(sesion, 999, nombre="X")

    def test_eliminar(self, sesion: Session) -> None:
        ana_id = nuevo_usuario(sesion)
        bd.eliminar_usuario(sesion, ana_id)
        assert bd.obtener_usuario(sesion, ana_id) is None

        with pytest.raises(bd.UsuarioNoEncontradoError):
            bd.eliminar_usuario(sesion, ana_id)

    def test_no_se_elimina_usuario_con_pedidos(self, sesion: Session) -> None:
        ana_id = nuevo_usuario(sesion)
        bd.crear_pedido(sesion, ana_id, {RAYUELA: 1})

        with pytest.raises(bd.RegistroEnUsoError):
            bd.eliminar_usuario(sesion, ana_id)
        assert bd.obtener_usuario(sesion, ana_id) is not None


# ---------------------------------------------------------------------------
# Libros
# ---------------------------------------------------------------------------
class TestLibros:
    def test_crear_y_leer(self, sesion: Session) -> None:
        libro = bd.obtener_libro(sesion, CIEN_AÑOS)
        assert libro is not None

        nuevo = libro.model_copy(update={"isbn": "978-0-00-000000-0", "titulo": "Libro nuevo"})
        bd.guardar_libro(sesion, nuevo)

        assert bd.obtener_libro(sesion, "978-0-00-000000-0") == nuevo
        with pytest.raises(LibroInvalidoError, match="Ya existe"):
            bd.guardar_libro(sesion, nuevo)

    def test_actualizar_precio_y_stock(self, sesion: Session) -> None:
        libro = bd.actualizar_libro(sesion, RAYUELA, precio=420.0, cantidad_disponible=0)

        assert libro.precio == 420.0
        assert libro.cantidad_disponible == 0
        assert libro.en_stock is False  # se recalcula
        assert libro.titulo == "Rayuela"  # no cambió
        assert bd.obtener_libro(sesion, RAYUELA) == libro

    def test_actualizar_con_datos_invalidos(self, sesion: Session) -> None:
        with pytest.raises(LibroInvalidoError):
            bd.actualizar_libro(sesion, RAYUELA, precio=-5)

        libro = bd.obtener_libro(sesion, RAYUELA)
        assert libro is not None and libro.precio == 399.50

    def test_actualizar_inexistente(self, sesion: Session) -> None:
        with pytest.raises(bd.LibroNoEncontradoError):
            bd.actualizar_libro(sesion, "no-existe", precio=1)

    def test_eliminar(self, sesion: Session) -> None:
        total = len(bd.listar_libros(sesion))
        bd.eliminar_libro(sesion, RAYUELA)

        assert bd.obtener_libro(sesion, RAYUELA) is None
        assert len(bd.listar_libros(sesion)) == total - 1

    def test_no_se_elimina_libro_vendido(self, sesion: Session) -> None:
        bd.crear_pedido(sesion, nuevo_usuario(sesion), {RAYUELA: 1})

        with pytest.raises(bd.RegistroEnUsoError):
            bd.eliminar_libro(sesion, RAYUELA)
        assert bd.obtener_libro(sesion, RAYUELA) is not None


# ---------------------------------------------------------------------------
# Estatus de pedidos
# ---------------------------------------------------------------------------
class TestEstatusPedido:
    def test_flujo_normal(self, sesion: Session) -> None:
        pedido = bd.crear_pedido(sesion, nuevo_usuario(sesion), {CIEN_AÑOS: 1})

        assert bd.cambiar_estatus(sesion, pedido.id, "pagado").estatus == "pagado"
        assert bd.cambiar_estatus(sesion, pedido.id, "enviado").estatus == "enviado"
        assert [p.id for p in bd.listar_pedidos(sesion, estatus="enviado")] == [pedido.id]
        assert bd.listar_pedidos(sesion, estatus="pendiente") == []

    def test_no_se_salta_pasos(self, sesion: Session) -> None:
        pedido = bd.crear_pedido(sesion, nuevo_usuario(sesion), {CIEN_AÑOS: 1})

        with pytest.raises(bd.TransicionEstatusError):
            bd.cambiar_estatus(sesion, pedido.id, "enviado")
        with pytest.raises(bd.TransicionEstatusError):
            bd.cambiar_estatus(sesion, pedido.id, "inventado")

    def test_cancelar_regresa_stock(self, sesion: Session) -> None:
        pedido = bd.crear_pedido(sesion, nuevo_usuario(sesion), {CIEN_AÑOS: 2})
        bd.cambiar_estatus(sesion, pedido.id, "pagado")

        assert bd.cambiar_estatus(sesion, pedido.id, "cancelado").estatus == "cancelado"
        libro = bd.obtener_libro(sesion, CIEN_AÑOS)
        assert libro is not None and libro.cantidad_disponible == 12

    def test_no_se_cancela_un_pedido_enviado(self, sesion: Session) -> None:
        pedido = bd.crear_pedido(sesion, nuevo_usuario(sesion), {CIEN_AÑOS: 1})
        bd.cambiar_estatus(sesion, pedido.id, "pagado")
        bd.cambiar_estatus(sesion, pedido.id, "enviado")

        with pytest.raises(bd.TransicionEstatusError):
            bd.cancelar_pedido(sesion, pedido.id)
        libro = bd.obtener_libro(sesion, CIEN_AÑOS)
        assert libro is not None and libro.cantidad_disponible == 11

    def test_pedido_inexistente(self, sesion: Session) -> None:
        with pytest.raises(bd.PedidoNoEncontradoError):
            bd.cambiar_estatus(sesion, 999, "pagado")
        assert bd.obtener_pedido(sesion, 999) is None
