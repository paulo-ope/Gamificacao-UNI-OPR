"""slim operations_login_status_snapshots: drop unused login/lat/long + redundant indexes

Reaproveita a migration 20260918_0104 da PR #28 (`claude/slim-login-status-snapshots`), que nunca
foi mesclada: o model enxuto (sem `login`/`latitude`/`longitude`) chegou à `master` no commit
7a352fe sem ela, e em produção todo INSERT do histórico falhou com NotNullViolation em `login`
de 19/09 a 28/10/2026 (a captura de status de login ficou parada e o status atual também, pois
os dois gravam na mesma transação). Em 28/10 a VM recebeu um `ALTER COLUMN login DROP NOT NULL`
manual só para voltar a capturar; esta migration traz o esquema definitivo e funciona tanto com
essa coluna já nullable quanto com ela ainda NOT NULL.

Motivo do enxugamento (levantamento de 2026-09-18): a tabela chegou a 66GB/87% do disco da VM.
`login`, `latitude` e `longitude` nunca eram lidos de volta - `login_timeseries` usa só
captured_at/login_id/online e `_recent_login_events` só last_connected_at/last_disconnected_at;
a detecção de cluster usa `operations_login_current_status`. `ix_..._login_id` é redundante com
o composto `(login_id, captured_at)` e `ix_..._online_geo` nunca foi consultado.

Revision ID: 20261029_0123
Revises: 20261028_0122
Create Date: 2026-10-29 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20261029_0123"
down_revision = "20261028_0122"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_operations_login_status_snapshots_online_geo", table_name="operations_login_status_snapshots")
    op.drop_index("ix_operations_login_status_snapshots_login_id", table_name="operations_login_status_snapshots")
    op.drop_column("operations_login_status_snapshots", "login")
    op.drop_column("operations_login_status_snapshots", "latitude")
    op.drop_column("operations_login_status_snapshots", "longitude")


def downgrade() -> None:
    op.add_column("operations_login_status_snapshots", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("operations_login_status_snapshots", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column(
        "operations_login_status_snapshots",
        sa.Column("login", sa.String(length=160), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_operations_login_status_snapshots_login_id",
        "operations_login_status_snapshots",
        ["login_id"],
    )
    op.create_index(
        "ix_operations_login_status_snapshots_online_geo",
        "operations_login_status_snapshots",
        ["online", "latitude", "longitude"],
    )
