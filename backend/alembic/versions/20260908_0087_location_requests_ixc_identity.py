"""location_requests - guarda os IDs reais do IXC (cliente/login) da busca

Revision ID: 20260908_0087
Revises: 20260908_0086
Create Date: 2026-09-08 02:00:00

Pedido do usuário: os IDs reais de `cliente`/`radusuarios` que a busca ao vivo no IXC
(`ixc_lookup.py`) já traz eram usados só para exibição/autopreenchimento e descartados depois -
sem ficar salvos, não dá pra correlacionar a solicitação com o cadastro do IXC depois, nem
pesquisar no mapa de referência por login. Migration puramente aditiva.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260908_0087"
down_revision = "20260908_0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("location_requests", sa.Column("ixc_cliente_id", sa.Integer(), nullable=True))
    op.add_column("location_requests", sa.Column("ixc_login_id", sa.Integer(), nullable=True))
    op.add_column("location_requests", sa.Column("ixc_login", sa.String(length=120), nullable=True))
    op.create_index("ix_location_requests_ixc_cliente_id", "location_requests", ["ixc_cliente_id"])
    op.create_index("ix_location_requests_ixc_login_id", "location_requests", ["ixc_login_id"])
    op.create_index("ix_location_requests_ixc_login", "location_requests", ["ixc_login"])


def downgrade() -> None:
    op.drop_index("ix_location_requests_ixc_login", table_name="location_requests")
    op.drop_index("ix_location_requests_ixc_login_id", table_name="location_requests")
    op.drop_index("ix_location_requests_ixc_cliente_id", table_name="location_requests")
    op.drop_column("location_requests", "ixc_login")
    op.drop_column("location_requests", "ixc_login_id")
    op.drop_column("location_requests", "ixc_cliente_id")
