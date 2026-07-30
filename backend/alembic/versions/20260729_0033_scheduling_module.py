"""scheduling module: local sync tables + permissions

Revision ID: 20260729_0033
Revises: 20260729_0032
Create Date: 2026-07-29

Módulo próprio de Agendamento (ver docs/estudo-kpis-agendamento.md): espelho local dos eventos do
IXC (`scheduling_orders`/`scheduling_events`), cadastro da equipe (`scheduling_operators`) e as
permissões novas `scheduling:read|sync|manage` para perfis customizados que já tinham acesso à aba
antiga (perfis de sistema são sincronizados automaticamente por ensure_access_profiles no startup).
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_0033"
down_revision = "20260729_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduling_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ixc_os_id", sa.Integer(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("setor_id", sa.String(length=10), nullable=False),
        sa.Column("setor_name", sa.String(length=120), nullable=False),
        sa.Column("filial_id", sa.String(length=10), nullable=False),
        sa.Column("assunto_id", sa.String(length=20), nullable=True),
        sa.Column("assunto_name", sa.String(length=180), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=True),
        sa.Column("first_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_operator_id", sa.Integer(), nullable=True),
        sa.Column("schedule_event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduling_orders_ixc_os_id", "scheduling_orders", ["ixc_os_id"], unique=True)
    op.create_index("ix_scheduling_orders_opened_at", "scheduling_orders", ["opened_at"])
    op.create_index("ix_scheduling_orders_setor_id", "scheduling_orders", ["setor_id"])
    op.create_index("ix_scheduling_orders_filial_id", "scheduling_orders", ["filial_id"])
    op.create_index("ix_scheduling_orders_assunto_id", "scheduling_orders", ["assunto_id"])
    op.create_index("ix_scheduling_orders_status", "scheduling_orders", ["status"])
    op.create_index("ix_scheduling_orders_first_scheduled_at", "scheduling_orders", ["first_scheduled_at"])
    op.create_index("ix_scheduling_orders_first_operator_id", "scheduling_orders", ["first_operator_id"])

    op.create_table(
        "scheduling_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ixc_message_id", sa.Integer(), nullable=False),
        sa.Column("ixc_os_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=4), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("operator_id", sa.Integer(), nullable=True),
        sa.Column("technician_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ixc_message_id", name="uq_scheduling_events_message"),
    )
    op.create_index("ix_scheduling_events_ixc_os_id", "scheduling_events", ["ixc_os_id"])
    op.create_index("ix_scheduling_events_event_type", "scheduling_events", ["event_type"])
    op.create_index("ix_scheduling_events_event_at", "scheduling_events", ["event_at"])
    op.create_index("ix_scheduling_events_operator_id", "scheduling_events", ["operator_id"])

    op.create_table(
        "scheduling_operators",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ixc_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("is_team_member", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduling_operators_ixc_user_id", "scheduling_operators", ["ixc_user_id"], unique=True)
    op.create_index("ix_scheduling_operators_is_team_member", "scheduling_operators", ["is_team_member"])

    # Perfis customizados que tinham a aba antiga ganham o acesso equivalente ao módulo novo.
    # (Perfis de sistema não precisam: ensure_access_profiles completa no startup.)
    op.execute(
        """
        INSERT INTO access_profile_permissions (profile_id, permission)
        SELECT DISTINCT app.profile_id, perm.new_permission
        FROM access_profile_permissions app
        CROSS JOIN (VALUES ('scheduling:read'), ('scheduling:sync')) AS perm(new_permission)
        WHERE app.permission = 'operations:view_scheduling'
          AND NOT EXISTS (
            SELECT 1 FROM access_profile_permissions done
            WHERE done.profile_id = app.profile_id AND done.permission = perm.new_permission
          )
        """
    )
    op.execute(
        """
        INSERT INTO access_profile_permissions (profile_id, permission)
        SELECT DISTINCT app.profile_id, 'scheduling:manage'
        FROM access_profile_permissions app
        WHERE app.permission = 'operations:manage'
          AND EXISTS (
            SELECT 1 FROM access_profile_permissions r
            WHERE r.profile_id = app.profile_id AND r.permission = 'operations:view_scheduling'
          )
          AND NOT EXISTS (
            SELECT 1 FROM access_profile_permissions done
            WHERE done.profile_id = app.profile_id AND done.permission = 'scheduling:manage'
          )
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM access_profile_permissions WHERE permission IN ('scheduling:read', 'scheduling:sync', 'scheduling:manage')")
    op.drop_table("scheduling_operators")
    op.drop_table("scheduling_events")
    op.drop_table("scheduling_orders")
