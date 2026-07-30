"""add scheduling_jobs table

Revision ID: 20260729_0032
Revises: 20260729_0031
Create Date: 2026-07-29

Job assíncrono para as métricas de agendamento (setor de agendamento) - consultar um mês inteiro no
IXC leva 1-3 minutos, tempo demais para uma rota síncrona sem estourar o timeout do proxy do Next.js
(mesmo padrão já usado por operations_backfill_jobs/operations_open_backlog_jobs).
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_0032"
down_revision = "20260729_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduling_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduling_jobs_job_type", "scheduling_jobs", ["job_type"])
    op.create_index("ix_scheduling_jobs_status", "scheduling_jobs", ["status"])
    op.create_index("ix_scheduling_jobs_requested_by", "scheduling_jobs", ["requested_by"])


def downgrade() -> None:
    op.drop_index("ix_scheduling_jobs_requested_by", table_name="scheduling_jobs")
    op.drop_index("ix_scheduling_jobs_status", table_name="scheduling_jobs")
    op.drop_index("ix_scheduling_jobs_job_type", table_name="scheduling_jobs")
    op.drop_table("scheduling_jobs")
