"""Esquema inicial: libros, usuarios, pedidos y pedido_items

Revision ID: 0001
Revises:
Create Date: 2026-09-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "libros",
        sa.Column("isbn", sa.String(length=20), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("autor_nombre", sa.String(length=100), nullable=False),
        sa.Column("autor_nacionalidad", sa.String(length=50), nullable=False),
        sa.Column("generos", sa.JSON(), nullable=False),
        sa.Column("año_publicacion", sa.Integer(), nullable=False),
        sa.Column("precio", sa.Float(), nullable=False),
        sa.Column("cantidad_disponible", sa.Integer(), nullable=False),
        sa.Column("editorial", sa.String(length=100), nullable=False),
        sa.CheckConstraint("año_publicacion BETWEEN 0 AND 2100", name=op.f("ck_libros_año_valido")),
        sa.CheckConstraint("precio >= 0", name=op.f("ck_libros_precio_positivo")),
        sa.CheckConstraint("cantidad_disponible >= 0", name=op.f("ck_libros_cantidad_positiva")),
        sa.PrimaryKeyConstraint("isbn", name=op.f("pk_libros")),
    )
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usuarios")),
        sa.UniqueConstraint("email", name=op.f("uq_usuarios_email")),
    )
    op.create_table(
        "pedidos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.DateTime(), nullable=False),
        sa.Column("estatus", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "estatus IN ('pendiente', 'pagado', 'enviado', 'cancelado')",
            name=op.f("ck_pedidos_estatus_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], name=op.f("fk_pedidos_usuario_id_usuarios")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pedidos")),
    )
    with op.batch_alter_table("pedidos") as batch_op:
        batch_op.create_index(batch_op.f("ix_pedidos_usuario_id"), ["usuario_id"])

    op.create_table(
        "pedido_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pedido_id", sa.Integer(), nullable=False),
        sa.Column("isbn", sa.String(length=20), nullable=False),
        sa.Column("cantidad", sa.Integer(), nullable=False),
        sa.Column("precio_unitario", sa.Float(), nullable=False),
        sa.CheckConstraint("cantidad > 0", name=op.f("ck_pedido_items_cantidad_positiva")),
        sa.CheckConstraint("precio_unitario >= 0", name=op.f("ck_pedido_items_precio_positivo")),
        sa.ForeignKeyConstraint(
            ["isbn"], ["libros.isbn"], name=op.f("fk_pedido_items_isbn_libros")
        ),
        sa.ForeignKeyConstraint(
            ["pedido_id"],
            ["pedidos.id"],
            name=op.f("fk_pedido_items_pedido_id_pedidos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pedido_items")),
        sa.UniqueConstraint("pedido_id", "isbn", name=op.f("uq_pedido_items_pedido_id")),
    )
    with op.batch_alter_table("pedido_items") as batch_op:
        batch_op.create_index(batch_op.f("ix_pedido_items_pedido_id"), ["pedido_id"])


def downgrade() -> None:
    # Orden inverso: primero las tablas que dependen de otras
    with op.batch_alter_table("pedido_items") as batch_op:
        batch_op.drop_index(batch_op.f("ix_pedido_items_pedido_id"))
    op.drop_table("pedido_items")

    with op.batch_alter_table("pedidos") as batch_op:
        batch_op.drop_index(batch_op.f("ix_pedidos_usuario_id"))
    op.drop_table("pedidos")

    op.drop_table("usuarios")
    op.drop_table("libros")
