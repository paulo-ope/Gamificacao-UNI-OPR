"""rastreio de meses totalmente importados do OPA Suite (backfill de madrugada)

Revision ID: 20260827_0080
Revises: 20260826_0079
Create Date: 2026-08-27 00:00:00

Migration puramente ADITIVA: cria uma tabela nova, nao toca em nenhuma tabela
existente, nenhuma metrica e nenhum dado ja gravado.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260827_0080"
down_revision = "20260826_0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_opa_import_months",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("year_month", sa.String(length=7), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="missing"),
        sa.Column("attendance_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_run_id", sa.Integer(), sa.ForeignKey("support_opa_import_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_unique_constraint("uq_support_opa_import_months_year_month", "support_opa_import_months", ["year_month"])
    op.create_index("ix_support_opa_import_months_year_month", "support_opa_import_months", ["year_month"])
    op.create_index("ix_support_opa_import_months_status", "support_opa_import_months", ["status"])


def downgrade() -> None:
    op.drop_index("ix_support_opa_import_months_status", table_name="support_opa_import_months")
    op.drop_index("ix_support_opa_import_months_year_month", table_name="support_opa_import_months")
    op.drop_table("support_opa_import_months")
