"""Administração parametrizável: semeadura idempotente de perfil, permissões próprias e ajuste de módulo

Revision ID: 20260909_0088
Revises: 20260908_0087
Create Date: 2026-09-09 00:00:00

Três tabelas novas, nenhuma coluna alterada em tabela existente (migration aditiva):

1. `access_profile_permission_seeds` - registra que uma permissão de perfil de sistema já foi
   semeada uma vez. Corrige o achado real de que `ensure_access_profiles` (roda a cada start do
   backend) devolvia sozinha qualquer permissão removida na tela de Perfis de Acesso.

   O backfill abaixo registra as permissões que os perfis de sistema TÊM neste banco agora. Efeito
   colateral consciente: se alguém removeu uma permissão antes deste deploy, ela ainda volta UMA
   última vez na primeira subida (a semeadura vai vê-la como "nunca semeada") e a partir daí a
   remoção fica de pé para sempre. Preferido a copiar `ROLE_PERMISSIONS` inteiro para dentro da
   migration, que congelaria aqui uma lista que muda em código.

2. `custom_permissions` - permissões criadas pela aba Permissões, fora do código. O catálogo
   efetivo é a união delas com `PERMISSION_LABELS`; só as daqui são excluíveis.

3. `workspace_module_settings` - nome/descrição/status/ordem que o admin sobrepõe ao
   `app/modules/registry.py`. Rota, prefixo de API e permissão mínima continuam só em código.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260909_0088"
down_revision = "20260908_0087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "access_profile_permission_seeds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legacy_role", sa.String(length=30), nullable=False),
        sa.Column("permission", sa.String(length=120), nullable=False),
        sa.Column("seeded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("legacy_role", "permission", name="uq_access_profile_permission_seed"),
    )
    op.create_index("ix_access_profile_permission_seeds_legacy_role", "access_profile_permission_seeds", ["legacy_role"])
    op.create_index("ix_access_profile_permission_seeds_permission", "access_profile_permission_seeds", ["permission"])

    # Backfill: o que os perfis de sistema já têm hoje conta como semeado.
    op.execute(
        """
        INSERT INTO access_profile_permission_seeds (legacy_role, permission)
        SELECT p.legacy_role, app.permission
        FROM access_profiles p
        JOIN access_profile_permissions app ON app.profile_id = p.id
        WHERE p.legacy_role IS NOT NULL AND p.is_system
        """
    )

    op.create_table(
        "custom_permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("module_key", sa.String(length=80), nullable=True),
        sa.Column("sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_custom_permissions_key", "custom_permissions", ["key"], unique=True)
    op.create_index("ix_custom_permissions_module_key", "custom_permissions", ["module_key"])
    op.create_index("ix_custom_permissions_active", "custom_permissions", ["active"])

    op.create_table(
        "workspace_module_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module_key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_workspace_module_settings_module_key", "workspace_module_settings", ["module_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_workspace_module_settings_module_key", table_name="workspace_module_settings")
    op.drop_table("workspace_module_settings")
    op.drop_index("ix_custom_permissions_active", table_name="custom_permissions")
    op.drop_index("ix_custom_permissions_module_key", table_name="custom_permissions")
    op.drop_index("ix_custom_permissions_key", table_name="custom_permissions")
    op.drop_table("custom_permissions")
    op.drop_index("ix_access_profile_permission_seeds_permission", table_name="access_profile_permission_seeds")
    op.drop_index("ix_access_profile_permission_seeds_legacy_role", table_name="access_profile_permission_seeds")
    op.drop_table("access_profile_permission_seeds")
