"""cria calculation_run_locks

Revision ID: 20260917_0104
Revises: 20260917_0103
Create Date: 2026-09-17 00:00:00

P0-4 da auditoria técnica de 2026-09-15 (`docs/auditoria-tecnica-geral-2026-09-15.md`):
`/calculation-runs/calculate` (e o recálculo automático em `recalculate_current_period`) não
tinham nenhuma proteção contra duas execuções do mesmo ciclo (mesmo mês/ano/regional) em
paralelo - sem lock, sem `UniqueConstraint`. A garantia atômica vem do `UniqueConstraint` em
`lock_key`, não de nenhum mecanismo em memória - funciona entre processos/threads diferentes,
igual ao restante do banco.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260917_0104"
down_revision = "20260917_0103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calculation_run_locks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lock_key", sa.String(length=64), nullable=False),
        sa.Column("reference_month", sa.Integer(), nullable=False),
        sa.Column("reference_year", sa.Integer(), nullable=False),
        sa.Column("regional", sa.String(length=120), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["locked_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lock_key", name="uq_calculation_run_locks_lock_key"),
    )


def downgrade() -> None:
    op.drop_table("calculation_run_locks")
