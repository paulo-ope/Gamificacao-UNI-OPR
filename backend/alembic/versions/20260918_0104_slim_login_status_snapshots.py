"""slim operations_login_status_snapshots: drop unused login/lat/long + redundant indexes

Levantamento de espaço em disco de 2026-09-18: esta tabela chegou a 66GB/87% do disco da VM
(que tem 97GB, sem expansão possível). `login`, `latitude` e `longitude` são gravados em toda
captura (~5min, 1 linha por login) mas nunca lidos de volta por nenhum consumidor -
`login_aggregate.login_timeseries` só usa captured_at/login_id/online, e
`login_search._recent_login_events` só usa last_connected_at/last_disconnected_at. A detecção
geográfica de cluster (`login_geo_clusters`) usa `operations_login_current_status`, que já tem
login/lat/long sempre atualizados por login_id - nunca esta tabela. `ix_..._login_id` é redundante
com o índice composto `(login_id, captured_at)` (mesmo prefixo), e `ix_..._online_geo` nunca foi
consultado por nenhuma query (índice morto desde a criação da tabela em 20260813_0050).

Revision ID: 20260918_0104
Revises: 20260917_0103
Create Date: 2026-09-18 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260918_0104"
down_revision = "20260917_0103"
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
