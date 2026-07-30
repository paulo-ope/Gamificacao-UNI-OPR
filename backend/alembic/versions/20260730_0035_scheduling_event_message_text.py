"""scheduling: capture operator message/historico text on events

Revision ID: 20260730_0035
Revises: 20260729_0034
Create Date: 2026-07-30

O sync original descartava o texto da mensagem (`su_oss_chamado_mensagem.mensagem`) e a nota
automática do IXC (`historico`) ao extrair cada evento - só id/data/operador/técnico entravam.
Adiciona as duas colunas pro log completo da O.S. mostrar o que o colaborador realmente escreveu,
mesmo quando não houve mudança formal de status (pedido do dono do produto, 2026-07-29).
"""

from alembic import op
import sqlalchemy as sa


revision = "20260730_0035"
down_revision = "20260729_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scheduling_events", sa.Column("mensagem", sa.Text(), nullable=True))
    op.add_column("scheduling_events", sa.Column("historico", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("scheduling_events", "historico")
    op.drop_column("scheduling_events", "mensagem")
