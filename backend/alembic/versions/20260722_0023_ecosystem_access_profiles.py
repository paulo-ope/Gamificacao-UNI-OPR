"""add ecosystem access profiles

Revision ID: 20260722_0023
Revises: 20260722_0022
Create Date: 2026-07-22 09:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260722_0023"
down_revision = "20260722_0022"
branch_labels = None
depends_on = None


ROLE_PERMISSIONS: dict[str, list[str]] = {
    "collaborator": [
        "portal:read_self",
        "portal:update_self_profile",
        "portal:read_regional_ranking",
        "portal:simulate_self",
        "portal:read_rules",
    ],
    "regional_manager_viewer": [
        "portal:read_self",
        "portal:update_self_profile",
        "portal:read_regional_ranking",
        "portal:simulate_self",
        "portal:read_rules",
        "portal:read_regional_summary",
        "operations:read",
        "operations:views:read_global",
    ],
    "viewer": [
        "dashboard:read",
        "audit:read",
        "orders:read",
        "scoring:read",
        "portal:read_self",
        "portal:update_self_profile",
        "portal:read_regional_ranking",
        "portal:simulate_self",
        "portal:read_rules",
        "operations:read",
        "operations:views:read_global",
    ],
    "operator": [
        "dashboard:read",
        "audit:read",
        "orders:read",
        "scoring:read",
        "orders:import",
        "portal:read_self",
        "portal:update_self_profile",
        "portal:read_regional_ranking",
        "portal:simulate_self",
        "portal:read_rules",
        "operations:read",
        "operations:manage",
        "operations:views:read_global",
        "operations:sync_ixc",
        "operations:view_order_details",
    ],
    "admin": [
        "dashboard:read",
        "audit:read",
        "orders:read",
        "orders:import",
        "scoring:read",
        "scoring:write",
        "penalties:write",
        "health_rules:write",
        "settings:write",
        "calculation:run",
        "users:manage",
        "portal:read_self",
        "portal:update_self_profile",
        "portal:read_regional_ranking",
        "portal:simulate_self",
        "portal:read_rules",
        "portal:read_regional_summary",
        "portal:read_overview",
        "operations:read",
        "operations:manage",
        "operations:sync_ixc",
        "operations:manage_filters",
        "operations:views:read_global",
        "operations:views:create_global",
        "operations:views:update_global",
        "operations:views:delete_global",
        "operations:manage_team_models",
        "operations:manage_subjects",
        "operations:view_order_details",
        "operations:view_sla",
        "operations:view_calendar",
        "operations:view_backlog",
        "operations:export",
        "admin:users:read",
        "admin:users:write",
        "admin:users:delete",
        "admin:roles:read",
        "admin:roles:write",
        "admin:permissions:read",
        "admin:audit:read",
    ],
}

ROLE_LABELS = {
    "collaborator": ("Colaborador Portal", "Acesso próprio ao portal do colaborador."),
    "regional_manager_viewer": ("Gestor Regional Portal", "Acompanha portal e operação das regionais vinculadas."),
    "viewer": ("Leitor Operacional", "Consulta dashboards, auditoria e operação sem alterações críticas."),
    "operator": ("Operador Operacional", "Opera importações e rotinas da operação com acesso gerencial."),
    "admin": ("Admin Ecossistema", "Controle total de módulos, usuários, perfis e configurações."),
}


def upgrade() -> None:
    op.create_table(
        "access_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("legacy_role", sa.String(length=30), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_access_profiles_name"),
    )
    op.create_index("ix_access_profiles_name", "access_profiles", ["name"])
    op.create_index("ix_access_profiles_legacy_role", "access_profiles", ["legacy_role"])
    op.create_index("ix_access_profiles_active", "access_profiles", ["active"])

    op.create_table(
        "access_profile_permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("access_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("permission", sa.String(length=120), nullable=False),
        sa.UniqueConstraint("profile_id", "permission", name="uq_access_profile_permission"),
    )
    op.create_index("ix_access_profile_permissions_profile_id", "access_profile_permissions", ["profile_id"])
    op.create_index("ix_access_profile_permissions_permission", "access_profile_permissions", ["permission"])

    op.create_table(
        "user_access_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("access_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "profile_id", name="uq_user_access_profile"),
    )
    op.create_index("ix_user_access_profiles_user_id", "user_access_profiles", ["user_id"])
    op.create_index("ix_user_access_profiles_profile_id", "user_access_profiles", ["profile_id"])

    access_profiles = sa.table(
        "access_profiles",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("legacy_role", sa.String()),
        sa.column("active", sa.Boolean()),
        sa.column("is_system", sa.Boolean()),
    )
    profile_permissions = sa.table(
        "access_profile_permissions",
        sa.column("profile_id", sa.Integer()),
        sa.column("permission", sa.String()),
    )
    connection = op.get_bind()
    for legacy_role, permissions in ROLE_PERMISSIONS.items():
        name, description = ROLE_LABELS[legacy_role]
        result = connection.execute(
            access_profiles.insert()
            .values(name=name, description=description, legacy_role=legacy_role, active=True, is_system=True)
            .returning(access_profiles.c.id)
        )
        profile_id = result.scalar_one()
        connection.execute(
            profile_permissions.insert(),
            [{"profile_id": profile_id, "permission": permission} for permission in sorted(set(permissions))],
        )

    op.execute(
        """
        INSERT INTO user_access_profiles (user_id, profile_id)
        SELECT users.id, access_profiles.id
        FROM users
        JOIN access_profiles ON access_profiles.legacy_role = users.role
        ON CONFLICT (user_id, profile_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("user_access_profiles")
    op.drop_table("access_profile_permissions")
    op.drop_table("access_profiles")
