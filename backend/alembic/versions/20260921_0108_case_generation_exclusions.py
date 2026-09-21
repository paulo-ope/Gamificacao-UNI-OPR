"""cria management_case_generation_exclusions

Revision ID: 20260921_0108
Revises: 20260921_0107
Create Date: 2026-09-21 00:00:00

Pedido do usuário (2026-09-21): parametrizar quem/quando NUNCA gera caso de gestão automático -
colaborador específico (permanente), período temporário (férias/atestado) ou regional inteira
(temporário ou permanente) - sem precisar mudar o modelo de equipe (afeta todo mundo que usa ele)
nem desativar o cadastro do colaborador (remove ele de tudo, não só da cobrança). Ver
`ManagementCaseGenerationExclusion` em models.py e `cases.active_generation_exclusion`.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260921_0108"
down_revision = "20260921_0107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "management_case_generation_exclusions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=True),
        sa.Column("regional", sa.String(length=160), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["management_operational_members.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(scope_type = 'member' AND member_id IS NOT NULL AND regional IS NULL) OR "
            "(scope_type = 'regional' AND regional IS NOT NULL AND member_id IS NULL)",
            name="ck_management_case_generation_exclusion_scope",
        ),
        sa.CheckConstraint(
            "date_from IS NULL OR date_to IS NULL OR date_from <= date_to",
            name="ck_management_case_generation_exclusion_date_range",
        ),
    )
    op.create_index(
        "ix_management_case_generation_exclusion_member", "management_case_generation_exclusions", ["member_id"]
    )
    op.create_index(
        "ix_management_case_generation_exclusion_regional", "management_case_generation_exclusions", ["regional"]
    )
    op.create_index(
        "ix_management_case_generation_exclusions_active", "management_case_generation_exclusions", ["active"]
    )


def downgrade() -> None:
    op.drop_table("management_case_generation_exclusions")
