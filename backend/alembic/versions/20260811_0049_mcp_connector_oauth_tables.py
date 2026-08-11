"""mcp connector: oauth tables for the remote MCP connector (Claude.ai/Cowork)

Revision ID: 20260811_0049
Revises: 20260811_0048
Create Date: 2026-08-11 03:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260811_0049"
down_revision = "20260811_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_oauth_clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("client_secret_hash", sa.String(length=255), nullable=True),
        sa.Column("client_name", sa.String(length=200), nullable=True),
        sa.Column("redirect_uris", sa.JSON(), nullable=False),
        sa.Column("grant_types", sa.JSON(), nullable=False),
        sa.Column("response_types", sa.JSON(), nullable=False),
        sa.Column("token_endpoint_auth_method", sa.String(length=40), nullable=False, server_default="none"),
        sa.Column("scope", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mcp_oauth_clients_client_id", "mcp_oauth_clients", ["client_id"], unique=True)

    op.create_table(
        "mcp_oauth_pending_authorizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("redirect_uri", sa.String(length=1000), nullable=False),
        sa.Column("redirect_uri_provided_explicitly", sa.Boolean(), nullable=False),
        sa.Column("code_challenge", sa.String(length=255), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=500), nullable=True),
        sa.Column("resource", sa.String(length=500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_mcp_oauth_pending_authorizations_request_id", "mcp_oauth_pending_authorizations", ["request_id"], unique=True
    )
    op.create_index(
        "ix_mcp_oauth_pending_authorizations_client_id", "mcp_oauth_pending_authorizations", ["client_id"], unique=False
    )

    op.create_table(
        "mcp_oauth_authorization_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("redirect_uri", sa.String(length=1000), nullable=False),
        sa.Column("redirect_uri_provided_explicitly", sa.Boolean(), nullable=False),
        sa.Column("code_challenge", sa.String(length=255), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("resource", sa.String(length=500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mcp_oauth_authorization_codes_code_hash", "mcp_oauth_authorization_codes", ["code_hash"], unique=True)
    op.create_index("ix_mcp_oauth_authorization_codes_client_id", "mcp_oauth_authorization_codes", ["client_id"], unique=False)
    op.create_index("ix_mcp_oauth_authorization_codes_user_id", "mcp_oauth_authorization_codes", ["user_id"], unique=False)

    op.create_table(
        "mcp_oauth_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("access_token_hash", sa.String(length=64), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=True),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("resource", sa.String(length=500), nullable=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mcp_oauth_tokens_access_token_hash", "mcp_oauth_tokens", ["access_token_hash"], unique=True)
    op.create_index("ix_mcp_oauth_tokens_refresh_token_hash", "mcp_oauth_tokens", ["refresh_token_hash"], unique=True)
    op.create_index("ix_mcp_oauth_tokens_client_id", "mcp_oauth_tokens", ["client_id"], unique=False)
    op.create_index("ix_mcp_oauth_tokens_user_id", "mcp_oauth_tokens", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("mcp_oauth_tokens")
    op.drop_table("mcp_oauth_authorization_codes")
    op.drop_table("mcp_oauth_pending_authorizations")
    op.drop_table("mcp_oauth_clients")
