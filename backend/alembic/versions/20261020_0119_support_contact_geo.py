"""cria support_contact_geo (cidade/bairro/regional do cliente de cada atendimento do OPA)

Revision ID: 20261020_0119
Revises: 20261019_0118
Create Date: 2026-10-20 00:00:00

Pedido do usuário (2026-10-20): aba "Radar de Contatos" no Suporte Interno, para saber de onde o
cliente que entrou em contato pelo OPA está falando (cidade, bairro) e achar problema massivo. Uma
linha por cliente do OPA, resolvida uma vez a partir do cadastro do IXC.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261020_0119"
down_revision = "20261019_0118"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_contact_geo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opa_customer_id", sa.String(length=100), nullable=False),
        sa.Column("ixc_customer_id", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ok"),
        sa.Column("regional", sa.String(length=80), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("neighborhood", sa.String(length=160), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("opa_customer_id", name="uq_support_contact_geo_opa_customer"),
    )
    op.create_index("ix_support_contact_geo_opa_customer_id", "support_contact_geo", ["opa_customer_id"])
    op.create_index("ix_support_contact_geo_ixc_customer_id", "support_contact_geo", ["ixc_customer_id"])
    op.create_index("ix_support_contact_geo_regional", "support_contact_geo", ["regional"])
    op.create_index("ix_support_contact_geo_city", "support_contact_geo", ["city"])


def downgrade() -> None:
    op.drop_index("ix_support_contact_geo_city", table_name="support_contact_geo")
    op.drop_index("ix_support_contact_geo_regional", table_name="support_contact_geo")
    op.drop_index("ix_support_contact_geo_ixc_customer_id", table_name="support_contact_geo")
    op.drop_index("ix_support_contact_geo_opa_customer_id", table_name="support_contact_geo")
    op.drop_table("support_contact_geo")
