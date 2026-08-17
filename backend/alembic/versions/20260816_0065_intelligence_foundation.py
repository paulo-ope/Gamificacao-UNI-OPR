"""add intelligence module foundation (monitor runs, alerts, alert events)

Revision ID: 20260816_0065
Revises: 20260816_0064
Create Date: 2026-08-16 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260816_0065"
down_revision = "20260816_0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intelligence_monitor_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("monitor_key", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="RUNNING"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("alerts_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("alerts_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("alerts_resolved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("stats_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_intelligence_monitor_runs_monitor_key", "intelligence_monitor_runs", ["monitor_key"])
    op.create_index("ix_intelligence_monitor_runs_status", "intelligence_monitor_runs", ["status"])
    op.create_index("ix_intelligence_monitor_runs_started_at", "intelligence_monitor_runs", ["started_at"])
    op.create_index("ix_intelligence_monitor_runs_key_started", "intelligence_monitor_runs", ["monitor_key", "started_at"])
    op.create_index("ix_intelligence_monitor_runs_key_status", "intelligence_monitor_runs", ["monitor_key", "status"])

    op.create_table(
        "intelligence_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("alert_type", sa.String(length=60), nullable=False),
        sa.Column("monitor_key", sa.String(length=80), nullable=False),
        sa.Column("dedupe_key", sa.String(length=300), nullable=False),
        sa.Column("regional", sa.String(length=120), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("scope_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("coverage_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("warnings_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("source_last_sync", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="NEW"),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("misses_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_type", sa.String(length=20), nullable=False, server_default="MONITOR"),
        sa.Column("source_key", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dedupe_key", name="uq_intelligence_alerts_dedupe_key"),
    )
    op.create_index("ix_intelligence_alerts_kind", "intelligence_alerts", ["kind"])
    op.create_index("ix_intelligence_alerts_alert_type", "intelligence_alerts", ["alert_type"])
    op.create_index("ix_intelligence_alerts_monitor_key", "intelligence_alerts", ["monitor_key"])
    op.create_index("ix_intelligence_alerts_dedupe_key", "intelligence_alerts", ["dedupe_key"])
    op.create_index("ix_intelligence_alerts_regional", "intelligence_alerts", ["regional"])
    op.create_index("ix_intelligence_alerts_severity", "intelligence_alerts", ["severity"])
    op.create_index("ix_intelligence_alerts_status", "intelligence_alerts", ["status"])
    op.create_index("ix_intelligence_alerts_last_seen_at", "intelligence_alerts", ["last_seen_at"])
    op.create_index("ix_intelligence_alerts_status_severity", "intelligence_alerts", ["status", "severity"])
    op.create_index("ix_intelligence_alerts_monitor_status", "intelligence_alerts", ["monitor_key", "status"])

    op.create_table(
        "intelligence_alert_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("intelligence_alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_intelligence_alert_events_alert_id", "intelligence_alert_events", ["alert_id"])
    op.create_index("ix_intelligence_alert_events_event_type", "intelligence_alert_events", ["event_type"])
    op.create_index("ix_intelligence_alert_events_created_at", "intelligence_alert_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_intelligence_alert_events_created_at", table_name="intelligence_alert_events")
    op.drop_index("ix_intelligence_alert_events_event_type", table_name="intelligence_alert_events")
    op.drop_index("ix_intelligence_alert_events_alert_id", table_name="intelligence_alert_events")
    op.drop_table("intelligence_alert_events")

    op.drop_index("ix_intelligence_alerts_monitor_status", table_name="intelligence_alerts")
    op.drop_index("ix_intelligence_alerts_status_severity", table_name="intelligence_alerts")
    op.drop_index("ix_intelligence_alerts_last_seen_at", table_name="intelligence_alerts")
    op.drop_index("ix_intelligence_alerts_status", table_name="intelligence_alerts")
    op.drop_index("ix_intelligence_alerts_severity", table_name="intelligence_alerts")
    op.drop_index("ix_intelligence_alerts_regional", table_name="intelligence_alerts")
    op.drop_index("ix_intelligence_alerts_dedupe_key", table_name="intelligence_alerts")
    op.drop_index("ix_intelligence_alerts_monitor_key", table_name="intelligence_alerts")
    op.drop_index("ix_intelligence_alerts_alert_type", table_name="intelligence_alerts")
    op.drop_index("ix_intelligence_alerts_kind", table_name="intelligence_alerts")
    op.drop_table("intelligence_alerts")

    op.drop_index("ix_intelligence_monitor_runs_key_status", table_name="intelligence_monitor_runs")
    op.drop_index("ix_intelligence_monitor_runs_key_started", table_name="intelligence_monitor_runs")
    op.drop_index("ix_intelligence_monitor_runs_started_at", table_name="intelligence_monitor_runs")
    op.drop_index("ix_intelligence_monitor_runs_status", table_name="intelligence_monitor_runs")
    op.drop_index("ix_intelligence_monitor_runs_monitor_key", table_name="intelligence_monitor_runs")
    op.drop_table("intelligence_monitor_runs")
