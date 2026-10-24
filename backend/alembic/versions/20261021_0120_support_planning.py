"""cria support_plan_items e support_plan_updates (aba Especialista/Analista do Suporte Interno)

Revision ID: 20261021_0120
Revises: 20261020_0119
Create Date: 2026-10-21 00:00:00

Pedido do usuário (2026-10-21): aba onde o Especialista e o Analista lançam os projetos e as
tarefas que precisam fazer e acompanham o andamento; tudo o que é lançado fica visível para todos
os que acessam o Suporte Interno.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261021_0120"
down_revision = "20261020_0119"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_plan_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="task"),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("support_plan_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="planned"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("assignee_ids", sa.JSON(), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_support_plan_items_kind", "support_plan_items", ["kind"])
    op.create_index("ix_support_plan_items_parent_id", "support_plan_items", ["parent_id"])
    op.create_index("ix_support_plan_items_status", "support_plan_items", ["status"])
    op.create_index("ix_support_plan_items_due_date", "support_plan_items", ["due_date"])
    op.create_index("ix_support_plan_items_archived", "support_plan_items", ["archived"])

    op.create_table(
        "support_plan_updates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("support_plan_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status_from", sa.String(length=20), nullable=True),
        sa.Column("status_to", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_support_plan_updates_item_id", "support_plan_updates", ["item_id"])


def downgrade() -> None:
    op.drop_index("ix_support_plan_updates_item_id", table_name="support_plan_updates")
    op.drop_table("support_plan_updates")
    op.drop_index("ix_support_plan_items_archived", table_name="support_plan_items")
    op.drop_index("ix_support_plan_items_due_date", table_name="support_plan_items")
    op.drop_index("ix_support_plan_items_status", table_name="support_plan_items")
    op.drop_index("ix_support_plan_items_parent_id", table_name="support_plan_items")
    op.drop_index("ix_support_plan_items_kind", table_name="support_plan_items")
    op.drop_table("support_plan_items")
