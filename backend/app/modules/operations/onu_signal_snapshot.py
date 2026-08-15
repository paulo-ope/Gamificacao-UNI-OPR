from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.calculation import get_setting
from app.services.ixc_client import IxcClient, fetch_onu_signal_by_login_ids, get_ixc_client

from .models import OperationLoginCurrentStatus, OperationOnuSignalCurrent
from .period import parse_ixc_local_datetime

logger = logging.getLogger(__name__)

# Achado real 2026-08-15: o IXC grava datetime em horário LOCAL (America/Porto_Velho, UTC-4), não
# UTC (ver login_status_snapshot.py para a evidência) - `signal_measured_at` ficava 4h adiantado
# com o parser anterior (`.replace(tzinfo=timezone.utc)` direto, sem deslocar). Corrigido
# reaproveitando `parse_ixc_local_datetime` (mesma fonte/fuso da importação de O.S.).
_parse_ixc_datetime = parse_ixc_local_datetime


def _parse_ixc_float(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _parse_ixc_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


# Mesmo limite de parâmetros por statement de `login_status_snapshot._UPSERT_CHUNK_SIZE` - aqui o
# volume real é muito menor (só os logins já monitorados, não a base de ~90 mil ONUs), mas o
# padrão de chunking é mantido por segurança caso a lista cresça.
_UPSERT_CHUNK_SIZE = 3000


def upsert_onu_signal_current(db: Session, rows: list[dict]) -> None:
    for offset in range(0, len(rows), _UPSERT_CHUNK_SIZE):
        chunk = rows[offset : offset + _UPSERT_CHUNK_SIZE]
        stmt = pg_insert(OperationOnuSignalCurrent).values(chunk)
        update_columns = {name: stmt.excluded[name] for name in chunk[0].keys() if name != "login_id"}
        stmt = stmt.on_conflict_do_update(index_elements=[OperationOnuSignalCurrent.login_id], set_=update_columns)
        db.execute(stmt)


def capture_onu_signal_snapshot(db: Session, client: IxcClient) -> int:
    """Busca telemetria óptica/ONU só para os logins já presentes em
    `OperationLoginCurrentStatus` (decisão do usuário: não varrer a tabela inteira do IXC, ~90 mil
    ONUs, para não sobrecarregar a API deles). Upsert simples (1 linha por login) - sem histórico
    append-only por enquanto (pode ser adicionado depois se análise de tendência de sinal ao longo
    do tempo for necessária)."""
    login_ids = list(db.scalars(select(OperationLoginCurrentStatus.login_id)))
    if not login_ids:
        return 0

    captured_at = datetime.now(timezone.utc)
    # Dedup por login_id, ficando com a última ocorrência - achado real: `radpop_radio_cliente_fibra`
    # pode ter mais de uma linha para o mesmo `id_login` (ex.: ONU trocada/re-provisionada sem
    # apagar o registro antigo), e um único `INSERT ... ON CONFLICT DO UPDATE` não pode afetar a
    # mesma linha duas vezes (Postgres levanta `CardinalityViolation`, derrubando o snapshot inteiro
    # do ciclo). Sem isso, um único login duplicado quebrava a captura de todos os outros.
    deduped: dict[int, dict] = {}
    for record in fetch_onu_signal_by_login_ids(client, login_ids):
        if not record.get("id_login"):
            continue
        deduped[int(record["id_login"])] = {
            "login_id": int(record["id_login"]),
            "contract_id": _parse_ixc_text(record.get("id_contrato")),
            "signal_rx_dbm": _parse_ixc_float(record.get("sinal_rx")),
            "signal_tx_dbm": _parse_ixc_float(record.get("sinal_tx")),
            "last_drop_cause": _parse_ixc_text(record.get("causa_ultima_queda")),
            "onu_serial": _parse_ixc_text(record.get("mac")),
            "onu_model": _parse_ixc_text(record.get("onu_tipo")),
            "transmitter_id": _parse_ixc_text(record.get("id_transmissor")),
            "temperature_c": _parse_ixc_float(record.get("temperatura")),
            "voltage": _parse_ixc_float(record.get("voltagem")),
            "signal_measured_at": _parse_ixc_datetime(record.get("data_sinal")),
            "pon_id": _parse_ixc_text(record.get("ponid")),
            "pon_no": _parse_ixc_text(record.get("ponno")),
            "slot_no": _parse_ixc_text(record.get("slotno")),
            "latitude": _parse_ixc_float(record.get("latitude")),
            "longitude": _parse_ixc_float(record.get("longitude")),
            "captured_at": captured_at,
        }
    parsed = list(deduped.values())
    if not parsed:
        return 0

    upsert_onu_signal_current(db, parsed)
    db.commit()
    return len(parsed)


# Mesmo espírito de `login_geo_clusters.MAX_LOGIN_STATUS_RESULTS` - limite defensivo pra consulta
# individual, nunca devolve a base inteira de uma vez.
MAX_ONU_SIGNAL_RESULTS = 500


def query_onu_signal_status(
    db: Session,
    *,
    login_ids: list[int] | None = None,
    last_drop_causes: list[str] | None = None,
    transmitter_ids: list[str] | None = None,
    limit: int = 200,
) -> list[dict]:
    """Consulta individual de telemetria óptica/ONU, já com o nome do login (join com
    `OperationLoginCurrentStatus`) - sem filtro nenhum, limita a `limit` (até
    `MAX_ONU_SIGNAL_RESULTS`) para nunca devolver a base inteira de logins monitorados de vez."""
    conditions = []
    if login_ids:
        conditions.append(OperationOnuSignalCurrent.login_id.in_(login_ids))
    if last_drop_causes:
        conditions.append(OperationOnuSignalCurrent.last_drop_cause.in_(last_drop_causes))
    if transmitter_ids:
        conditions.append(OperationOnuSignalCurrent.transmitter_id.in_(transmitter_ids))

    stmt = (
        select(OperationOnuSignalCurrent, OperationLoginCurrentStatus.login)
        .join(OperationLoginCurrentStatus, OperationLoginCurrentStatus.login_id == OperationOnuSignalCurrent.login_id)
        .where(*conditions)
        .order_by(OperationOnuSignalCurrent.captured_at.desc())
        .limit(min(limit, MAX_ONU_SIGNAL_RESULTS))
    )
    rows = db.execute(stmt).all()
    return [
        {
            "login_id": signal.login_id,
            "login": login,
            "contract_id": signal.contract_id,
            "signal_rx_dbm": signal.signal_rx_dbm,
            "signal_tx_dbm": signal.signal_tx_dbm,
            "last_drop_cause": signal.last_drop_cause,
            "onu_serial": signal.onu_serial,
            "onu_model": signal.onu_model,
            "transmitter_id": signal.transmitter_id,
            "temperature_c": signal.temperature_c,
            "voltage": signal.voltage,
            "signal_measured_at": signal.signal_measured_at,
            "pon_id": signal.pon_id,
            "pon_no": signal.pon_no,
            "slot_no": signal.slot_no,
            "latitude": signal.latitude,
            "longitude": signal.longitude,
            "captured_at": signal.captured_at,
        }
        for signal, login in rows
    ]


# Configurável pela tela (AppSetting), lido a cada ciclo - mesmo racional de
# `login_status_snapshot.LOGIN_STATUS_SYNC_INTERVAL_MINUTES_KEY` (pedido do usuário em 2026-08-15,
# receio de sobrecarregar a API do IXC).
ONU_SIGNAL_SYNC_INTERVAL_MINUTES_KEY = "onu_signal_sync_interval_minutes"
ONU_SIGNAL_SYNC_DEFAULT_INTERVAL_MINUTES = 15
ONU_SIGNAL_SYNC_MIN_INTERVAL_MINUTES = 5
ONU_SIGNAL_SYNC_MAX_INTERVAL_MINUTES = 180


def _current_onu_signal_interval_seconds() -> float:
    with SessionLocal() as db:
        raw = get_setting(db, ONU_SIGNAL_SYNC_INTERVAL_MINUTES_KEY, "")
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        minutes = ONU_SIGNAL_SYNC_DEFAULT_INTERVAL_MINUTES
    minutes = min(max(minutes, ONU_SIGNAL_SYNC_MIN_INTERVAL_MINUTES), ONU_SIGNAL_SYNC_MAX_INTERVAL_MINUTES)
    return minutes * 60.0


async def run_onu_signal_snapshot_loop() -> None:
    """Loop infinito: captura telemetria óptica/ONU periodicamente, só dos logins já monitorados -
    intervalo configurável pela tela (`ONU_SIGNAL_SYNC_INTERVAL_MINUTES_KEY`, lido a cada ciclo,
    sem precisar reiniciar o backend). Uma falha numa rodada não derruba o loop, só é logada."""
    IDLE_POLL_SECONDS = 60.0
    while True:
        settings = get_settings()
        if not settings.ixc_api_base_url or not settings.ixc_api_token:
            await asyncio.sleep(IDLE_POLL_SECONDS)
            continue
        try:
            client = get_ixc_client()
            with SessionLocal() as db:
                captured = await asyncio.to_thread(capture_onu_signal_snapshot, db, client)
            if captured:
                logger.info("Snapshot de sinal ONU capturado: %d linhas.", captured)
        except Exception:
            logger.exception("Falha ao capturar snapshot de sinal ONU.")
        await asyncio.sleep(_current_onu_signal_interval_seconds())
