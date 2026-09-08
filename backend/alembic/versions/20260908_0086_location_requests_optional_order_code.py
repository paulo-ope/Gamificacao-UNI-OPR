"""location_requests - código da O.S. opcional + protocolo OPA

Revision ID: 20260908_0086
Revises: 20260908_0085
Create Date: 2026-09-08 01:00:00

Ajuste de modelagem (feedback do usuário logo após a primeira entrega): o link de localização
costuma ser enviado ANTES de existir O.S. no IXC - o atendente ainda está coletando a posição do
cliente para abrir o atendimento. `order_code` deixa de ser obrigatório; `opa_protocol` (protocolo
do atendimento no OPA Suite) entra como identificador alternativo nesse momento inicial. O código
da O.S. pode ser anexado depois, quando existir (ver `service.attach_order_code`).

Migration aditiva/relaxante: solta uma constraint NOT NULL e adiciona uma coluna nova - não perde
dado de nenhuma linha já existente.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260908_0086"
down_revision = "20260908_0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("location_requests", "order_code", existing_type=sa.String(length=60), nullable=True)
    op.add_column("location_requests", sa.Column("opa_protocol", sa.String(length=60), nullable=True))
    op.create_index("ix_location_requests_opa_protocol", "location_requests", ["opa_protocol"])


def downgrade() -> None:
    op.drop_index("ix_location_requests_opa_protocol", table_name="location_requests")
    op.drop_column("location_requests", "opa_protocol")
    op.alter_column("location_requests", "order_code", existing_type=sa.String(length=60), nullable=False)
