"""add intelligence dashboard profiles and cockpit content (F2)

Revision ID: 20260817_0067
Revises: 20260816_0066
Create Date: 2026-08-17 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260817_0067"
down_revision = "20260816_0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intelligence_dashboard_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False, server_default="MATRIX_TV"),
        sa.Column("scope_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("widgets_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("display_config_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("refresh_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("key", name="uq_intelligence_dashboard_profiles_key"),
    )
    op.create_index("ix_intelligence_dashboard_profiles_key", "intelligence_dashboard_profiles", ["key"])

    op.create_table(
        "intelligence_cockpit_content",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_type", sa.String(length=30), nullable=False),
        sa.Column("profile_key", sa.String(length=80), nullable=True),
        sa.Column("scope_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("regional", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="INFO"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_key", sa.String(length=120), nullable=True),
        sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_intelligence_cockpit_content_content_type", "intelligence_cockpit_content", ["content_type"])
    op.create_index("ix_intelligence_cockpit_content_profile_key", "intelligence_cockpit_content", ["profile_key"])
    op.create_index("ix_intelligence_cockpit_content_regional", "intelligence_cockpit_content", ["regional"])
    op.create_index("ix_intelligence_cockpit_content_status", "intelligence_cockpit_content", ["status"])
    op.create_index("ix_intelligence_cockpit_content_valid_until", "intelligence_cockpit_content", ["valid_until"])
    op.create_index("ix_intelligence_cockpit_content_created_at", "intelligence_cockpit_content", ["created_at"])
    op.create_index("ix_intelligence_cockpit_content_status_profile", "intelligence_cockpit_content", ["status", "profile_key"])


def downgrade() -> None:
    op.drop_index("ix_intelligence_cockpit_content_status_profile", table_name="intelligence_cockpit_content")
    op.drop_index("ix_intelligence_cockpit_content_created_at", table_name="intelligence_cockpit_content")
    op.drop_index("ix_intelligence_cockpit_content_valid_until", table_name="intelligence_cockpit_content")
    op.drop_index("ix_intelligence_cockpit_content_status", table_name="intelligence_cockpit_content")
    op.drop_index("ix_intelligence_cockpit_content_regional", table_name="intelligence_cockpit_content")
    op.drop_index("ix_intelligence_cockpit_content_profile_key", table_name="intelligence_cockpit_content")
    op.drop_index("ix_intelligence_cockpit_content_content_type", table_name="intelligence_cockpit_content")
    op.drop_table("intelligence_cockpit_content")

    op.drop_index("ix_intelligence_dashboard_profiles_key", table_name="intelligence_dashboard_profiles")
    op.drop_table("intelligence_dashboard_profiles")
