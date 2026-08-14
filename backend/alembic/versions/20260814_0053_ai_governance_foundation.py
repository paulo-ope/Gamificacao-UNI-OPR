"""ai governance foundation: exposure policy tables for API/MCP access control

Revision ID: 20260814_0053
Revises: 20260813_0052
Create Date: 2026-08-14 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260814_0053"
down_revision = "20260813_0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_endpoints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("kind", sa.String(length=10), nullable=False, server_default="both"),
        sa.Column("enabled_api", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("enabled_mcp", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("enabled_ai", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("key", name="uq_ai_endpoints_key"),
    )
    op.create_index("ix_ai_endpoints_key", "ai_endpoints", ["key"])

    op.create_table(
        "ai_field_permissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity", sa.String(length=80), nullable=False),
        sa.Column("field", sa.String(length=120), nullable=False),
        sa.Column("filterable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("text_filterable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("groupable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("returnable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("selectable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("detail_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("entity", "field", name="uq_ai_field_permissions_entity_field"),
    )
    op.create_index("ix_ai_field_permissions_entity", "ai_field_permissions", ["entity"])
    op.create_index("ix_ai_field_permissions_field", "ai_field_permissions", ["field"])

    op.create_table(
        "ai_profile_endpoint_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("access_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint_key", sa.String(length=120), sa.ForeignKey("ai_endpoints.key", ondelete="CASCADE"), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "endpoint_key", name="uq_ai_profile_endpoint_grant"),
    )
    op.create_index("ix_ai_profile_endpoint_grants_profile_id", "ai_profile_endpoint_grants", ["profile_id"])
    op.create_index("ix_ai_profile_endpoint_grants_endpoint_key", "ai_profile_endpoint_grants", ["endpoint_key"])

    op.create_table(
        "ai_profile_field_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("access_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity", sa.String(length=80), nullable=False),
        sa.Column("field", sa.String(length=120), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "entity", "field", name="uq_ai_profile_field_grant"),
    )
    op.create_index("ix_ai_profile_field_grants_profile_id", "ai_profile_field_grants", ["profile_id"])
    op.create_index("ix_ai_profile_field_grants_entity", "ai_profile_field_grants", ["entity"])
    op.create_index("ix_ai_profile_field_grants_field", "ai_profile_field_grants", ["field"])

    op.create_table(
        "ai_api_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("access_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_api_tokens_user_id", "ai_api_tokens", ["user_id"])
    op.create_index("ix_ai_api_tokens_profile_id", "ai_api_tokens", ["profile_id"])
    op.create_index("ix_ai_api_tokens_key_prefix", "ai_api_tokens", ["key_prefix"])

    op.create_table(
        "ai_access_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("token_id", sa.Integer(), sa.ForeignKey("ai_api_tokens.id", ondelete="SET NULL"), nullable=True),
        sa.Column("origin", sa.String(length=10), nullable=False),
        sa.Column("endpoint_key", sa.String(length=120), nullable=False),
        sa.Column("filters_summary", sa.JSON(), nullable=True),
        sa.Column("fields_requested", sa.JSON(), nullable=True),
        sa.Column("response_mode", sa.String(length=20), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="success"),
        sa.Column("error_message", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_ai_access_audit_log_occurred_at", "ai_access_audit_log", ["occurred_at"])
    op.create_index("ix_ai_access_audit_log_user_id", "ai_access_audit_log", ["user_id"])
    op.create_index("ix_ai_access_audit_log_token_id", "ai_access_audit_log", ["token_id"])
    op.create_index("ix_ai_access_audit_log_origin", "ai_access_audit_log", ["origin"])
    op.create_index("ix_ai_access_audit_log_endpoint_key", "ai_access_audit_log", ["endpoint_key"])
    op.create_index("ix_ai_access_audit_log_status", "ai_access_audit_log", ["status"])


def downgrade() -> None:
    op.drop_table("ai_access_audit_log")
    op.drop_table("ai_api_tokens")
    op.drop_table("ai_profile_field_grants")
    op.drop_table("ai_profile_endpoint_grants")
    op.drop_table("ai_field_permissions")
    op.drop_table("ai_endpoints")
