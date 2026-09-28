"""Agrega la columna telefono a usuarios

Ejemplo de una migración "normal": el modelo UsuarioDB cambió después de que
la base ya existía, y esta migración lleva ese cambio a las bases existentes
sin perder datos.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # nullable=True: los usuarios que ya existen quedan con telefono = NULL
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.add_column(sa.Column("telefono", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("usuarios") as batch_op:
        batch_op.drop_column("telefono")
