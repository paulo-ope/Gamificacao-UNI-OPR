"""Agregação, quedas por período e série temporal de logins - pedido do usuário em 2026-08-15 para
detecção de incidente coletivo (várias PONs/regionais caindo juntas) sem precisar baixar milhares de
registros individuais. Prioriza agregação no backend (item 6 do pedido: "priorize agregações")."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.modules.ai_governance.response_meta import build_meta

from .login_geo_clusters import find_offline_login_clusters
from .models import OperationLoginCurrentStatus, OperationLoginStatusSnapshot, OperationOnuSignalCurrent

LoginAggregateDimension = Literal["regional", "online", "transmitter_id", "pon_id", "last_drop_cause"]

# Dimensões que vivem em operations_onu_signal_current (exigem join) - as demais estão direto em
# operations_login_current_status.
_ONU_DIMENSIONS = {"transmitter_id", "pon_id", "last_drop_cause"}

MAX_LOGIN_OUTAGES_RESULTS = 1000


def _login_source_last_sync(db: Session) -> datetime | None:
    """Horário da última captura de status de login concluída - usado como `source_last_sync` no
    envelope `meta` (Fase 1, item 1 do plano de confiabilidade de dado, pedido do usuário em
    2026-08-15). Sinaliza pra quem consome o endpoint há quanto tempo o dado é real, sem precisar
    inferir isso de fora."""
    return db.scalar(select(func.max(OperationLoginCurrentStatus.captured_at)))

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
    status_changed_since: datetime | None = None,
) -> list[dict]:
    """Contagem de logins por dimensão (regional/status/transmissor/PON/causa de queda) - mesmo
    formato de `ai.queries.aggregate_orders` (label/quantity/percentage), mas sobre o estado ATUAL
    de conectividade, não sobre O.S. `group_by` desconhecido levanta erro explícito (mesma correção
    aplicada em `_group_label` - nunca cai num fallback silencioso). `status_changed_since` restringe
    a quem TRANSICIONOU de estado dentro da janela (ex.: combinado com `online_statuses=["N"]`,
    responde "quem caiu E continua caído nos últimos N minutos, por dimensão")."""
    if group_by not in LoginAggregateDimension.__args__:
        raise ValueError(f"group_by inválido: '{group_by}'. Dimensões aceitas: {', '.join(LoginAggregateDimension.__args__)}.")

    conditions = []
    if regionals:
        conditions.append(OperationLoginCurrentStatus.regional.in_(regionals))
    if online_statuses:
        conditions.append(OperationLoginCurrentStatus.online.in_(online_statuses))
    if status_changed_since is not None:
        conditions.append(OperationLoginCurrentStatus.status_changed_at >= status_changed_since)

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
    data = sorted(
        (
            {"label": label, "quantity": int(count), "percentage": round((count / total) * 100, 2) if total else 0.0}
            for label, count in rows
        ),
        key=lambda item: item["quantity"],
        reverse=True,
    )
    return {
        "meta": build_meta(
            applied_filters={"group_by": group_by, "regionals": regionals, "online_statuses": online_statuses, "status_changed_since": status_changed_since},
            source_last_sync=_login_source_last_sync(db),
        ),
        "data": data,
    }


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
    data = [
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
    warnings = []
    if len(data) == MAX_LOGIN_OUTAGES_RESULTS and limit > MAX_LOGIN_OUTAGES_RESULTS:
        warnings.append(
            f"Resultado truncado em {MAX_LOGIN_OUTAGES_RESULTS} registros (limit={limit} solicitado, teto do endpoint)."
        )
    return {
        "meta": build_meta(
            applied_filters={"since": since, "until": until, "regionals": regionals, "limit": limit},
            warnings=warnings,
            source_last_sync=_login_source_last_sync(db),
        ),
        "data": data,
    }


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
    # Achado real da auditoria de 2026-08-21: quando não existe NENHUMA captura entre
    # lookback_start e since (início real da coleta de dados, ou gap de captura > 20min antes de
    # `since`), o LAG() da query não tem "antes" pra comparar - toda linha da primeira captura
    # dentro da janela é contada como transição nova, inflando new_drops/new_reconnects do
    # primeiro ponto pro total de desconectados/conectados daquele instante. Checagem simples e
    # barata (EXISTS) pra sinalizar isso de forma estruturada, em vez de só documentar em prosa.
    has_baseline = bool(
        db.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM operations_login_status_snapshots "
                "WHERE captured_at >= :lookback_start AND captured_at < :since)"
            ),
            {"lookback_start": lookback_start, "since": since},
        ).scalar()
    )
    data = [
        {
            "captured_at": row.captured_at,
            "connected": int(row.connected),
            "disconnected": int(row.disconnected),
            "new_drops": int(row.new_drops),
            "new_reconnects": int(row.new_reconnects),
            "baseline_available": has_baseline or index > 0,
        }
        for index, row in enumerate(rows)
    ]
    warnings = []
    if data and not has_baseline:
        warnings.append({
            "code": "FIRST_POINT_MAY_BE_INFLATED",
            "detail": (
                "Não há captura de status de login antes do início do período pedido (dentro do "
                "buffer de lookback de 20min) - new_drops/new_reconnects do primeiro ponto podem "
                "refletir o total de desconectados/conectados naquele instante, não uma transição "
                "real. Ver campo baseline_available por ponto."
            ),
        })
    return {
        "meta": build_meta(
            applied_filters={"since": since, "until": until},
            warnings=warnings,
            source_last_sync=_login_source_last_sync(db),
        ),
        "data": data,
    }


MAX_INCIDENT_GEO_CLUSTER_LOGINS = 50


def login_incident_analysis(
    db: Session,
    *,
    window_minutes: int = 90,
    regionals: list[str] | None = None,
    cluster_radius_meters: float = 300.0,
    cluster_min_size: int = 3,
) -> dict:
    """Funil de incidente coletivo numa única chamada (pedido do usuário em 2026-08-15, pra não
    precisar de várias idas ao banco/rede pra montar o mesmo quadro manualmente) - compõe as
    funções já existentes e testadas deste módulo, nenhuma lógica nova de consulta:

    - `new_drops`/`reconnects`: somados a partir de `login_timeseries` (janela inteira, não série).
    - `still_offline`: de `login_outages` - quem caiu na janela e CONTINUA offline agora.
    - `by_regional`/`by_transmitter`/`by_pon`/`by_drop_cause`: `login_aggregate` restrito a quem
      está offline E caiu dentro da janela (`status_changed_since`).
    - `geo_clusters`: de `find_offline_login_clusters` - concentração física (independe de
      regional administrativa, propositalmente, porque um rompimento físico pode atravessar
      fronteira de regional)."""
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

    timeseries_points = login_timeseries(db, since=since)["data"]
    new_drops = sum(point["new_drops"] for point in timeseries_points)
    reconnects = sum(point["new_reconnects"] for point in timeseries_points)

    still_offline_items = login_outages(db, since=since, regionals=regionals, limit=MAX_LOGIN_OUTAGES_RESULTS)["data"]

    def _breakdown(dimension: LoginAggregateDimension) -> list[dict]:
        return login_aggregate(
            db, group_by=dimension, regionals=regionals, online_statuses=["N"], status_changed_since=since
        )["data"]

    clusters = find_offline_login_clusters(
        db, radius_meters=cluster_radius_meters, min_cluster_size=cluster_min_size, window_minutes=window_minutes
    )

    return {
        "window_minutes": window_minutes,
        "since": since,
        "new_drops": new_drops,
        "still_offline": len(still_offline_items),
        "reconnects": reconnects,
        "by_regional": _breakdown("regional"),
        "by_transmitter": _breakdown("transmitter_id"),
        "by_pon": _breakdown("pon_id"),
        "by_drop_cause": _breakdown("last_drop_cause"),
        "geo_clusters": [
            {
                "center_latitude": cluster.center_latitude,
                "center_longitude": cluster.center_longitude,
                "radius_meters": cluster.radius_meters,
                "size": cluster.size,
                "logins": [point.login for point in cluster.logins[:MAX_INCIDENT_GEO_CLUSTER_LOGINS]],
            }
            for cluster in clusters
        ],
        "meta": build_meta(
            applied_filters={
                "window_minutes": window_minutes,
                "regionals": regionals,
                "cluster_radius_meters": cluster_radius_meters,
                "cluster_min_size": cluster_min_size,
            },
            source_last_sync=_login_source_last_sync(db),
        ),
    }
