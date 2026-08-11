"""operations team target versions: append-only history of team target rules

Revision ID: 20260811_0046
Revises: 20260811_0045
Create Date: 2026-08-11 01:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260811_0046"
down_revision = "20260811_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operations_team_target_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_model_id", sa.Integer(), sa.ForeignKey("operations_team_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_model_name", sa.String(length=120), nullable=False),
        sa.Column("period_type", sa.String(length=20), nullable=False),
        sa.Column("target_quantity", sa.Integer(), nullable=False),
        sa.Column("median_from_quantity", sa.Integer(), nullable=False),
        sa.Column("good_from_quantity", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_operations_team_target_versions_team_model_id", "operations_team_target_versions", ["team_model_id"])
    op.create_index(
        "ix_operations_team_target_versions_lookup",
        "operations_team_target_versions",
        ["team_model_name", "period_type", "valid_from"],
    )

    # Backfill: toda regra hoje existente vira 1 versão vigente desde a criação da própria regra
    # (valid_to NULL) - é o melhor "início de histórico" possível sem inventar dados: qualquer
    # mudança de meta anterior a este deploy já foi perdida (a regra viva é sempre sobrescrita),
    # mas ao menos regras nunca editadas ficam com o valid_from correto desde sempre.
    op.execute(
        """
        INSERT INTO operations_team_target_versions
            (team_model_id, team_model_name, period_type, target_quantity,
             median_from_quantity, good_from_quantity, valid_from, valid_to, created_at)
        SELECT r.team_model_id, m.name, r.period_type, r.target_quantity,
               r.median_from_quantity, r.good_from_quantity, r.created_at, NULL, CURRENT_TIMESTAMP
        FROM operations_team_target_rules r
        JOIN operations_team_models m ON m.id = r.team_model_id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_operations_team_target_versions_lookup", table_name="operations_team_target_versions")
    op.drop_index("ix_operations_team_target_versions_team_model_id", table_name="operations_team_target_versions")
    op.drop_table("operations_team_target_versions")
