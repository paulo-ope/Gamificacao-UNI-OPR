"""add first-access onboarding fields to users

Revision ID: 20260828_0081
Revises: 20260827_0080
Create Date: 2026-08-28 00:00:00

Fase 1 do primeiro acesso obrigatório do colaborador no Portal (pedido do usuário em
2026-08-28): antes de ver ranking, O.S., auditoria ou qualquer dado financeiro/operacional
individual, o colaborador precisa confirmar CPF/telefone/e-mail e trocar a senha uma vez.

Três colunas aditivas em `users`:
- `must_change_password` (bool, default false): sinalizador de reset administrativo (Fase 2 -
  painel admin ainda não existe nesta entrega).
- `first_access_completed_at` (datetime nullable): sinal canônico de "já completou o onboarding
  alguma vez". `NULL` = pendente.
- `password_changed_at` (datetime nullable): quando a senha foi trocada pela última vez -
  informativo, não usado pelo bloqueio.

RISCO CRÍTICO NEUTRALIZADO NESTA MIGRATION: se `first_access_completed_at` ficasse `NULL` para
quem já usa o portal hoje, TODO colaborador ativo seria bloqueado retroativamente na primeira
requisição depois do deploy - regressão grave e não pedida (ver seção 3.1 do
`manual_desenvolvimento_senior.md`, "melhoria arquitetural não justifica regressão funcional").
O backfill abaixo marca `first_access_completed_at = created_at` para toda linha já existente no
momento da migration - só usuário CRIADO DEPOIS deste deploy, com vínculo a colaborador, nasce
pendente (a lógica que decide isso vive em `create_user`, api/routes/users.py, não aqui).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260828_0081"
down_revision = "20260827_0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("first_access_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE users SET first_access_completed_at = created_at WHERE first_access_completed_at IS NULL")


def downgrade() -> None:
    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "first_access_completed_at")
    op.drop_column("users", "must_change_password")
