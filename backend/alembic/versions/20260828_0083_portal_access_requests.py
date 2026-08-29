"""portal_access_requests - Fase 2D (solicitacao de acesso)

Revision ID: 20260828_0083
Revises: 20260828_0082
Create Date: 2026-08-28 00:00:00

Migration puramente ADITIVA: cria uma tabela nova, não toca em nenhuma tabela existente, nenhuma
métrica e nenhum dado já gravado.

Ver docs/portal-ciclo-vida-conta-colaborador.md seção 8 (modelo de dados sugerido) e seção 6
(Fase 2D - solicitação de acesso).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260828_0083"
down_revision = "20260828_0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portal_access_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("cpf", sa.String(length=20), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=False),
        sa.Column("email", sa.String(length=180), nullable=False),
        sa.Column("suggested_collaborator_id", sa.Integer(), sa.ForeignKey("collaborators.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("reviewed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_portal_access_requests_cpf", "portal_access_requests", ["cpf"])
    op.create_index("ix_portal_access_requests_email", "portal_access_requests", ["email"])
    op.create_index("ix_portal_access_requests_suggested_collaborator_id", "portal_access_requests", ["suggested_collaborator_id"])
    op.create_index("ix_portal_access_requests_status", "portal_access_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_portal_access_requests_status", table_name="portal_access_requests")
    op.drop_index("ix_portal_access_requests_suggested_collaborator_id", table_name="portal_access_requests")
    op.drop_index("ix_portal_access_requests_email", table_name="portal_access_requests")
    op.drop_index("ix_portal_access_requests_cpf", table_name="portal_access_requests")
    op.drop_table("portal_access_requests")
