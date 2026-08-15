"""Busca e detalhamento completo de logins - pedido do usuário em 2026-08-15 pra fechar o fluxo
"login caiu -> investigar" sem precisar de várias chamadas manuais. Reaproveita
`OperationLoginCurrentStatus` (status atual), `OperationOnuSignalCurrent` (telemetria óptica/ONU,
join opcional) e `OperationLoginStatusSnapshot` (histórico append-only, usado só para reconstruir
eventos recentes de conexão/desconexão)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .login_geo_clusters import _geo_radius_condition
from .models import OperationLoginCurrentStatus, OperationLoginStatusSnapshot, OperationOnuSignalCurrent

# Mesmo espírito de `login_geo_clusters.MAX_LOGIN_STATUS_RESULTS` - limite defensivo, nunca
# devolve a base inteira de uma vez.
MAX_LOGIN_SEARCH_RESULTS = 500

# Campos datetime aceitos no filtro fino (mesmo formato {"gte"/"gt"/"lte"/"lt"/"eq": datetime} de
# `ai.queries._datetime_filter_conditions`, mas aqui local a este módulo - login não passa pelo
# schema de O.S.) - chave = nome aceito no filtro, valor = coluna real.
LOGIN_DATE_FIELD_COLUMNS = {
    "captured_at": OperationLoginCurrentStatus.captured_at,
    "status_changed_at": OperationLoginCurrentStatus.status_changed_at,
    "last_connected_at": OperationLoginCurrentStatus.last_connected_at,
    "last_disconnected_at": OperationLoginCurrentStatus.last_disconnected_at,
}


def _as_utc(value: datetime) -> datetime:
    # Mesmo racional de operations.queries._as_utc - SQLite (testes) desserializa sem tzinfo.
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _datetime_op_conditions(column, op: dict | None) -> list:
    if not op:
        return []
    conditions = []
    if op.get("gte") is not None:
        conditions.append(column >= _as_utc(op["gte"]))
    if op.get("gt") is not None:
        conditions.append(column > _as_utc(op["gt"]))
    if op.get("lte") is not None:
        conditions.append(column <= _as_utc(op["lte"]))
    if op.get("lt") is not None:
        conditions.append(column < _as_utc(op["lt"]))
    if op.get("eq") is not None:
        conditions.append(column == _as_utc(op["eq"]))
    return conditions


def search_logins(
    db: Session,
    *,
    logins: list[str] | None = None,
    login_query: str | None = None,
    login_ids: list[int] | None = None,
    online_statuses: list[str] | None = None,
    regionals: list[str] | None = None,
    pon_ids: list[str] | None = None,
    transmitter_ids: list[str] | None = None,
    contract_ids: list[str] | None = None,
    near_latitude: float | None = None,
    near_longitude: float | None = None,
    radius_km: float | None = None,
    status_changed_at: dict | None = None,
    last_connected_at: dict | None = None,
    last_disconnected_at: dict | None = None,
    captured_at: dict | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Pesquisa geral de logins com paginação real (mesmo padrão de `ai.queries.search_orders`).

    `logins` é igualdade exata (lista); `login_query` é busca parcial (`ILIKE %valor%`) - "pesquise
    o login cliente123" usa `login_query`, "traga estes 3 logins exatos" usa `logins`. `pon_ids`/
    `transmitter_ids`/`contract_ids` fazem JOIN com `operations_onu_signal_current` (só logins com
    telemetria capturada aparecem quando esses filtros são usados)."""
    page_size = min(page_size, MAX_LOGIN_SEARCH_RESULTS)
    conditions = []
    if logins:
        conditions.append(OperationLoginCurrentStatus.login.in_(logins))
    if login_query:
        conditions.append(OperationLoginCurrentStatus.login.ilike(f"%{login_query}%"))
    if login_ids:
        conditions.append(OperationLoginCurrentStatus.login_id.in_(login_ids))
    if online_statuses:
        conditions.append(OperationLoginCurrentStatus.online.in_(online_statuses))
    if regionals:
        conditions.append(OperationLoginCurrentStatus.regional.in_(regionals))
    if near_latitude is not None and near_longitude is not None and radius_km is not None:
        conditions.append(
            _geo_radius_condition(
                OperationLoginCurrentStatus.latitude, OperationLoginCurrentStatus.longitude,
                near_latitude, near_longitude, radius_km,
            )
        )
    conditions.extend(_datetime_op_conditions(OperationLoginCurrentStatus.status_changed_at, status_changed_at))
    conditions.extend(_datetime_op_conditions(OperationLoginCurrentStatus.last_connected_at, last_connected_at))
    conditions.extend(_datetime_op_conditions(OperationLoginCurrentStatus.last_disconnected_at, last_disconnected_at))
    conditions.extend(_datetime_op_conditions(OperationLoginCurrentStatus.captured_at, captured_at))

    needs_onu_join = bool(pon_ids or transmitter_ids or contract_ids)
    stmt = select(OperationLoginCurrentStatus, OperationOnuSignalCurrent).select_from(OperationLoginCurrentStatus).join(
        OperationOnuSignalCurrent,
        OperationOnuSignalCurrent.login_id == OperationLoginCurrentStatus.login_id,
        isouter=not needs_onu_join,
    )
    if pon_ids:
        conditions.append(OperationOnuSignalCurrent.pon_id.in_(pon_ids))
    if transmitter_ids:
        conditions.append(OperationOnuSignalCurrent.transmitter_id.in_(transmitter_ids))
    if contract_ids:
        conditions.append(OperationOnuSignalCurrent.contract_id.in_(contract_ids))

    stmt = stmt.where(*conditions)
    count_stmt = select(OperationLoginCurrentStatus.login_id).select_from(OperationLoginCurrentStatus).join(
        OperationOnuSignalCurrent,
        OperationOnuSignalCurrent.login_id == OperationLoginCurrentStatus.login_id,
        isouter=not needs_onu_join,
    ).where(*conditions)
    total = len(list(db.scalars(count_stmt)))

    offset = (page - 1) * page_size
    rows = db.execute(
        stmt.order_by(OperationLoginCurrentStatus.status_changed_at.desc()).offset(offset).limit(page_size)
    ).all()

    items = []
    for login, onu in rows:
        items.append(
            {
                "login_id": login.login_id,
                "login": login.login,
                "online": login.online,
                "regional": login.regional,
                "latitude": login.latitude,
                "longitude": login.longitude,
                "last_connected_at": login.last_connected_at,
                "last_disconnected_at": login.last_disconnected_at,
                "status_changed_at": login.status_changed_at,
                "captured_at": login.captured_at,
                "contract_id": onu.contract_id if onu else None,
                "pon_id": onu.pon_id if onu else None,
                "transmitter_id": onu.transmitter_id if onu else None,
                "last_drop_cause": onu.last_drop_cause if onu else None,
            }
        )
    return {
        "items": items,
        "total_encontrado": total,
        "page": page,
        "page_size": page_size,
        "has_more": offset + len(items) < total,
    }


@dataclass
class LoginHistoryEvent:
    event: str  # "connected" | "disconnected"
    at: datetime


def _recent_login_events(db: Session, login_id: int, *, since: datetime) -> list[LoginHistoryEvent]:
    """Reconstrói eventos de conexão/desconexão a partir do histórico append-only
    (`OperationLoginStatusSnapshot`, capturado a cada ~5min) - não usa o horário da captura em si
    (`captured_at`, que só diz "quando o sistema olhou"), e sim `last_connected_at`/
    `last_disconnected_at` (horário real gravado pelo IXC) - um evento é emitido toda vez que um
    desses dois campos muda de valor entre duas capturas consecutivas, o que dá o horário exato do
    evento mesmo com captura só a cada 5 minutos."""
    rows = list(
        db.scalars(
            select(OperationLoginStatusSnapshot)
            .where(
                OperationLoginStatusSnapshot.login_id == login_id,
                OperationLoginStatusSnapshot.captured_at >= since,
            )
            .order_by(OperationLoginStatusSnapshot.captured_at.asc())
        )
    )
    events: list[LoginHistoryEvent] = []
    seen_connected: datetime | None = None
    seen_disconnected: datetime | None = None
    for row in rows:
        if row.last_connected_at and row.last_connected_at != seen_connected:
            events.append(LoginHistoryEvent(event="connected", at=row.last_connected_at))
            seen_connected = row.last_connected_at
        if row.last_disconnected_at and row.last_disconnected_at != seen_disconnected:
            events.append(LoginHistoryEvent(event="disconnected", at=row.last_disconnected_at))
            seen_disconnected = row.last_disconnected_at
    events.sort(key=lambda e: e.at)
    return events


def get_login_detail(db: Session, *, login: str | None = None, login_id: int | None = None, history_hours: int = 24) -> dict | None:
    """Detalhamento completo de um login (identificação, status de conexão com tempo no estado
    atual JÁ CALCULADO, telemetria ONU/PON e histórico recente de eventos) - `login` ou `login_id`,
    pelo menos um dos dois. Retorna `None` quando não encontrado (o chamador decide o formato do
    erro - HTTPException na rota REST, ValueError na tool MCP)."""
    if login is None and login_id is None:
        raise ValueError("Informe login ou login_id.")
    conditions = []
    if login_id is not None:
        conditions.append(OperationLoginCurrentStatus.login_id == login_id)
    if login is not None:
        conditions.append(OperationLoginCurrentStatus.login == login)
    row = db.execute(
        select(OperationLoginCurrentStatus, OperationOnuSignalCurrent)
        .select_from(OperationLoginCurrentStatus)
        .join(OperationOnuSignalCurrent, OperationOnuSignalCurrent.login_id == OperationLoginCurrentStatus.login_id, isouter=True)
        .where(and_(*conditions))
        .limit(1)
    ).first()
    if row is None:
        return None
    login_row, onu_row = row

    now = datetime.now(timezone.utc)
    status_changed_at = login_row.status_changed_at
    if status_changed_at.tzinfo is None:
        status_changed_at = status_changed_at.replace(tzinfo=timezone.utc)
    seconds_in_state = max(0, int((now - status_changed_at).total_seconds()))

    since = now - timedelta(hours=history_hours)
    events = _recent_login_events(db, login_row.login_id, since=since)

    return {
        "login_id": login_row.login_id,
        "login": login_row.login,
        "regional": login_row.regional,
        "latitude": login_row.latitude,
        "longitude": login_row.longitude,
        "online": login_row.online,
        "captured_at": login_row.captured_at,
        "status_changed_at": login_row.status_changed_at,
        "last_connected_at": login_row.last_connected_at,
        "last_disconnected_at": login_row.last_disconnected_at,
        "seconds_in_current_state": seconds_in_state,
        "onu_serial": onu_row.onu_serial if onu_row else None,
        "onu_model": onu_row.onu_model if onu_row else None,
        "signal_rx_dbm": onu_row.signal_rx_dbm if onu_row else None,
        "signal_tx_dbm": onu_row.signal_tx_dbm if onu_row else None,
        "signal_measured_at": onu_row.signal_measured_at if onu_row else None,
        "temperature_c": onu_row.temperature_c if onu_row else None,
        "voltage": onu_row.voltage if onu_row else None,
        "last_drop_cause": onu_row.last_drop_cause if onu_row else None,
        "transmitter_id": onu_row.transmitter_id if onu_row else None,
        "pon_id": onu_row.pon_id if onu_row else None,
        "pon_no": onu_row.pon_no if onu_row else None,
        "slot_no": onu_row.slot_no if onu_row else None,
        "contract_id": onu_row.contract_id if onu_row else None,
        "recent_events": [{"event": e.event, "at": e.at} for e in events],
    }
