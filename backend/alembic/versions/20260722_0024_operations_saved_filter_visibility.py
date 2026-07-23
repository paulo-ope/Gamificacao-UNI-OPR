"""add operation saved filter visibility

Revision ID: 20260722_0024
Revises: 20260722_0023
Create Date: 2026-07-22 10:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260722_0024"
down_revision = "20260722_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operations_saved_filters",
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="personal"),
    )
    op.create_index("ix_operations_saved_filters_visibility", "operations_saved_filters", ["visibility"])
    op.execute("UPDATE operations_saved_filters SET visibility = 'personal' WHERE visibility IS NULL OR visibility = ''")
    op.execute(
        """
        INSERT INTO access_profile_permissions (profile_id, permission)
        SELECT id, 'operations:views:read_global'
        FROM access_profiles
        WHERE legacy_role IN ('regional_manager_viewer', 'viewer', 'operator', 'admin')
        ON CONFLICT (profile_id, permission) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO access_profile_permissions (profile_id, permission)
        SELECT profile.id, permission.name
        FROM access_profiles profile
        CROSS JOIN (
            VALUES
                ('operations:views:create_global'),
                ('operations:views:update_global'),
                ('operations:views:delete_global')
        ) AS permission(name)
        WHERE profile.legacy_role = 'admin'
        ON CONFLICT (profile_id, permission) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM access_profile_permissions
        WHERE permission IN (
            'operations:views:read_global',
            'operations:views:create_global',
            'operations:views:update_global',
            'operations:views:delete_global'
        )
        """
    )
    op.drop_index("ix_operations_saved_filters_visibility", table_name="operations_saved_filters")
    op.drop_column("operations_saved_filters", "visibility")
