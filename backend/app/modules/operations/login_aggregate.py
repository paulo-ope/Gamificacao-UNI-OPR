"""Agregação, quedas por período e série temporal de logins - pedido do usuário em 2026-08-15 para
detecção de incidente coletivo (várias PONs/regionais caindo juntas) sem precisar baixar milhares de
registros individuais. Prioriza agregação no backend (item 6 do pedido: "priorize agregações")."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .models import OperationLoginCurrentStatus, OperationLoginStatusSnapshot, OperationOnuSignalCurrent

LoginAggregateDimension = Literal["regional", "online", "transmitter_id", "pon_id", "last_drop_cause"]

# Dimensões que vivem em operations_onu_signal_current (exigem join) - as demais estão direto em
# operations_login_current_status.
_ONU_DIMENSIONS = {"transmitter_id", "pon_id", "last_drop_cause"}

MAX_LOGIN_OUTAGES_RESULTS = 1000

# ~2-4 capturas antes de `since` (loop de captura roda a cada 5-15min em produção) - só o
# suficiente pra LAG() de login_timeseries enxergar o estado "antes" da primeira captura já dentro
# da janela pedida, sem incluir esse ponto extra no resultado devolvido.
_LOOKBACK_BUFFER = timedelta(minutes=20)


def login_aggregate(
    db: Session,
    *,
    group_by: LoginAggregateDimension,
    regionals: list[str] | None = None,
    online_statuses: list[str] | None = None,
) -> list[dict]:
    """Contagem de logins por dimensão (regional/status/transmissor/PON/causa de queda) - mesmo
    formato de `ai.queries.aggregate_orders` (label/quantity/percentage), mas sobre o estado ATUAL
    de conectividade, não sobre O.S. `group_by` desconhecido levanta erro explícito (mesma correção
    aplicada em `_group_label` - nunca cai num fallback silencioso)."""
    if group_by not in LoginAggregateDimension.__args__:
        raise ValueError(f"group_by inválido: '{group_by}'. Dimensões aceitas: {', '.join(LoginAggregateDimension.__args__)}.")

    conditions = []
    if regionals:
        conditions.append(OperationLoginCurrentStatus.regional.in_(regionals))
    if online_statuses:
        conditions.append(OperationLoginCurrentStatus.online.in_(online_statuses))

    if group_by in _ONU_DIMENSIONS:
        label_column = func.coalesce(getattr(OperationOnuSignalCurrent, group_by), "Não identificado")
        stmt = (
            select(label_column, func.count(OperationLoginCurrentStatus.login_id))
            .select_from(OperationLoginCurrentStatus)
            .join(OperationOnuSignalCurrent, OperationOnuSignalCurrent.login_id == OperationLoginCurrentStatus.login_id)
            .where(*conditions)
            .group_by(label_column)
        )
    else:
        label_column = func.coalesce(getattr(OperationLoginCurrentStatus, group_by), "Não identificado")
        stmt = (
            select(label_column, func.count(OperationLoginCurrentStatus.login_id))
            .where(*conditions)
            .group_by(label_column)
        )

    rows = db.execute(stmt).all()
    total = sum(count for _, count in rows)
    return sorted(
        (
            {"label": label, "quantity": int(count), "percentage": round((count / total) * 100, 2) if total else 0.0}
            for label, count in rows
        ),
        key=lambda item: item["quantity"],
        reverse=True,
    )


def login_outages(
    db: Session,
    *,
    since: datetime,
    until: datetime | None = None,
    regionals: list[str] | None = None,
    limit: int = 200,
) -> list[dict]:
    """Logins que estão OFFLINE agora e cuja queda (`status_changed_at`) aconteceu dentro de
    [since, until] - mesma lógica de `login_geo_clusters._fetch_recent_disconnections`
    (generalizada aqui: regional em vez de só raio geográfico, e janela explícita em vez de só
    "últimos N minutos"). Usa a tabela `operations_login_current_status` (indexada em
    `online`+`status_changed_at`), não o histórico completo - eficiente mesmo em produção.

    Limitação conhecida: só pega quedas que CONTINUAM offline no momento da consulta - um login que
    caiu e já reconectou dentro da janela não aparece aqui (nesse caso, veja `opr_get_login_detail`
    -> `recent_events`, que reconstrói o histórico completo por login individual)."""
    until = until or datetime.now(timezone.utc)
    conditions = [
        OperationLoginCurrentStatus.online == "N",
        OperationLoginCurrentStatus.status_changed_at >= since,
        OperationLoginCurrentStatus.status_changed_at <= until,
    ]
    if regionals:
        conditions.append(OperationLoginCurrentStatus.regional.in_(regionals))
    rows = db.execute(
        select(OperationLoginCurrentStatus)
        .where(*conditions)
        .order_by(OperationLoginCurrentStatus.status_changed_at.desc())
        .limit(min(limit, MAX_LOGIN_OUTAGES_RESULTS))
    ).scalars()
    return [
        {
            "login_id": row.login_id,
            "login": row.login,
            "regional": row.regional,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "status_changed_at": row.status_changed_at,
            "last_disconnected_at": row.last_disconnected_at,
        }
        for row in rows
    ]


# Índice existente em operations_login_status_snapshots.captured_at (mapped_column(index=True))
# confirmado suficiente por EXPLAIN ANALYZE real (janela de 6h, ~176 mil linhas, 83ms) - não criou
# necessidade de índice novo.
_TIMESERIES_SQL = text(
    """
    WITH captures AS (
        SELECT
            captured_at,
            login_id,
            online,
            LAG(online) OVER (PARTITION BY login_id ORDER BY captured_at) AS prev_online
        FROM operations_login_status_snapshots
        WHERE captured_at BETWEEN :lookback_start AND :until
    )
    SELECT
        captured_at,
        count(*) FILTER (WHERE online = 'N') AS disconnected,
        count(*) FILTER (WHERE online = 'S') AS connected,
        count(*) FILTER (WHERE online = 'N' AND prev_online IS DISTINCT FROM 'N') AS new_drops,
        count(*) FILTER (WHERE online = 'S' AND prev_online IS DISTINCT FROM 'S') AS new_reconnects
    FROM captures
    WHERE captured_at >= :since
    GROUP BY captured_at
    ORDER BY captured_at
    """
)


def login_timeseries(db: Session, *, since: datetime, until: datetime | None = None) -> list[dict]:
    """Série temporal de conectados/desconectados/quedas novas/reconexões novas, um ponto por
    captura real do snapshot (a cada ~5-15min, conforme o loop de captura em produção - não há
    agregação por bucket de tempo fixo, cada captura já é um ponto discreto).

    "Quedas novas"/"reconexões novas" (não só a contagem estática de quem está offline/online numa
    captura) usam `LAG()` por login comparando com a captura ANTERIOR - por isso a consulta busca
    um pouco antes de `since` (20 minutos, ~2-4 capturas) só para ter o "antes" da primeira captura
    dentro da janela pedida; o resultado devolvido começa exatamente em `since`."""
    until = until or datetime.now(timezone.utc)
    lookback_start = since - _LOOKBACK_BUFFER
    rows = db.execute(_TIMESERIES_SQL, {"lookback_start": lookback_start, "since": since, "until": until}).all()
    return [
        {
            "captured_at": row.captured_at,
            "connected": int(row.connected),
            "disconnected": int(row.disconnected),
            "new_drops": int(row.new_drops),
            "new_reconnects": int(row.new_reconnects),
        }
        for row in rows
    ]
