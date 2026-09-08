"""location_requests - UNI Localiza (MVP de compartilhamento de localização por link)

Revision ID: 20260908_0085
Revises: 20260829_0084
Create Date: 2026-09-08 00:00:00

Migration puramente ADITIVA: cria uma tabela nova, não toca em nenhuma tabela existente.
Ver docs/STATUS.md (UNI Localiza) para o desenho completo do módulo.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260908_0085"
down_revision = "20260829_0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "location_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("order_code", sa.String(length=60), nullable=False),
        sa.Column("customer_id", sa.String(length=60), nullable=True),
        sa.Column("customer_name", sa.String(length=180), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("registered_latitude", sa.Float(), nullable=True),
        sa.Column("registered_longitude", sa.Float(), nullable=True),
        sa.Column("gps_latitude", sa.Float(), nullable=True),
        sa.Column("gps_longitude", sa.Float(), nullable=True),
        sa.Column("confirmed_latitude", sa.Float(), nullable=True),
        sa.Column("confirmed_longitude", sa.Float(), nullable=True),
        sa.Column("accuracy_meters", sa.Float(), nullable=True),
        sa.Column("adjusted_manually", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("distance_from_registered_meters", sa.Float(), nullable=True),
        sa.Column("created_ip_hash", sa.String(length=32), nullable=True),
        sa.Column("confirmed_ip_hash", sa.String(length=32), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_location_requests_public_id", "location_requests", ["public_id"], unique=True)
    op.create_index("ix_location_requests_token_hash", "location_requests", ["token_hash"], unique=True)
    op.create_index("ix_location_requests_order_code", "location_requests", ["order_code"])
    op.create_index("ix_location_requests_customer_id", "location_requests", ["customer_id"])
    op.create_index("ix_location_requests_status", "location_requests", ["status"])
    op.create_index("ix_location_requests_created_by_user_id", "location_requests", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_location_requests_created_by_user_id", table_name="location_requests")
    op.drop_index("ix_location_requests_status", table_name="location_requests")
    op.drop_index("ix_location_requests_customer_id", table_name="location_requests")
    op.drop_index("ix_location_requests_order_code", table_name="location_requests")
    op.drop_index("ix_location_requests_token_hash", table_name="location_requests")
    op.drop_index("ix_location_requests_public_id", table_name="location_requests")
    op.drop_table("location_requests")
