"""add support OPA import checkpoints

Revision ID: 20260816_0063
Revises: 20260816_0062
Create Date: 2026-08-16 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260816_0063"
down_revision = "20260816_0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("support_opa_import_runs", sa.Column("provider", sa.String(length=40), nullable=False, server_default="opa"))
    op.add_column("support_opa_import_runs", sa.Column("entity", sa.String(length=80), nullable=False, server_default="attendance"))
    op.add_column("support_opa_import_runs", sa.Column("mode", sa.String(length=40), nullable=False, server_default="manual"))
    op.add_column("support_opa_import_runs", sa.Column("page_limit", sa.Integer(), nullable=False, server_default="100"))
    op.add_column("support_opa_import_runs", sa.Column("pages_processed", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("support_opa_import_runs", sa.Column("next_skip", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("support_opa_import_runs", sa.Column("checkpoint_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.add_column("support_opa_import_runs", sa.Column("last_error", sa.String(length=500), nullable=True))
    op.add_column("support_opa_import_runs", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_support_opa_import_runs_provider"), "support_opa_import_runs", ["provider"])
    op.create_index(op.f("ix_support_opa_import_runs_entity"), "support_opa_import_runs", ["entity"])
    op.create_index(op.f("ix_support_opa_import_runs_mode"), "support_opa_import_runs", ["mode"])


def downgrade() -> None:
    op.drop_index(op.f("ix_support_opa_import_runs_mode"), table_name="support_opa_import_runs")
    op.drop_index(op.f("ix_support_opa_import_runs_entity"), table_name="support_opa_import_runs")
    op.drop_index(op.f("ix_support_opa_import_runs_provider"), table_name="support_opa_import_runs")
    op.drop_column("support_opa_import_runs", "duration_ms")
    op.drop_column("support_opa_import_runs", "last_error")
    op.drop_column("support_opa_import_runs", "checkpoint_json")
    op.drop_column("support_opa_import_runs", "next_skip")
    op.drop_column("support_opa_import_runs", "pages_processed")
    op.drop_column("support_opa_import_runs", "page_limit")
    op.drop_column("support_opa_import_runs", "mode")
    op.drop_column("support_opa_import_runs", "entity")
    op.drop_column("support_opa_import_runs", "provider")
