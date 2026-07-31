"""collaborator structure fields

Revision ID: 20260730_0039
Revises: 20260730_0038
Create Date: 2026-07-30 23:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260730_0039"
down_revision = "20260730_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("collaborators", sa.Column("cpf", sa.String(length=20), nullable=True))
    op.add_column("collaborators", sa.Column("employee_type", sa.String(length=40), nullable=True))
    op.add_column("collaborators", sa.Column("team_type", sa.String(length=40), nullable=True))
    op.add_column("collaborators", sa.Column("supervisor_user_id", sa.Integer(), nullable=True))
    op.add_column("collaborators", sa.Column("regional_manager_user_id", sa.Integer(), nullable=True))
    op.add_column("collaborators", sa.Column("structure_status", sa.String(length=40), nullable=False, server_default="pending_review"))
    op.add_column("collaborators", sa.Column("structure_notes", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_collaborators_supervisor_user_id_users",
        "collaborators",
        "users",
        ["supervisor_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_collaborators_regional_manager_user_id_users",
        "collaborators",
        "users",
        ["regional_manager_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_collaborators_cpf", "collaborators", ["cpf"])
    op.create_index("ix_collaborators_employee_type", "collaborators", ["employee_type"])
    op.create_index("ix_collaborators_team_type", "collaborators", ["team_type"])
    op.create_index("ix_collaborators_supervisor_user_id", "collaborators", ["supervisor_user_id"])
    op.create_index("ix_collaborators_regional_manager_user_id", "collaborators", ["regional_manager_user_id"])
    op.create_index("ix_collaborators_structure_status", "collaborators", ["structure_status"])


def downgrade() -> None:
    op.drop_index("ix_collaborators_structure_status", table_name="collaborators")
    op.drop_index("ix_collaborators_regional_manager_user_id", table_name="collaborators")
    op.drop_index("ix_collaborators_supervisor_user_id", table_name="collaborators")
    op.drop_index("ix_collaborators_team_type", table_name="collaborators")
    op.drop_index("ix_collaborators_employee_type", table_name="collaborators")
    op.drop_index("ix_collaborators_cpf", table_name="collaborators")
    op.drop_constraint("fk_collaborators_regional_manager_user_id_users", "collaborators", type_="foreignkey")
    op.drop_constraint("fk_collaborators_supervisor_user_id_users", "collaborators", type_="foreignkey")
    op.drop_column("collaborators", "structure_notes")
    op.drop_column("collaborators", "structure_status")
    op.drop_column("collaborators", "regional_manager_user_id")
    op.drop_column("collaborators", "supervisor_user_id")
    op.drop_column("collaborators", "team_type")
    op.drop_column("collaborators", "employee_type")
    op.drop_column("collaborators", "cpf")

