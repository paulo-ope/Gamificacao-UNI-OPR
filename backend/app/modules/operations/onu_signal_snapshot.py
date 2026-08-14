from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.ixc_client import IxcClient, fetch_onu_signal_by_login_ids, get_ixc_client

from .models import OperationLoginCurrentStatus, OperationOnuSignalCurrent

logger = logging.getLogger(__name__)

# Mesmo marcador de "nunca aconteceu" do IXC usado em login_status_snapshot.py - "0000-00-00
# 00:00:00" em vez de NULL.
_IXC_EMPTY_DATETIME_PREFIX = "0000-00-00"


def _parse_ixc_datetime(value: str | None) -> datetime | None:
    if not value or value.startswith(_IXC_EMPTY_DATETIME_PREFIX):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


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


async def run_onu_signal_snapshot_loop() -> None:
    """Loop infinito: captura telemetria óptica/ONU periodicamente, só dos logins já monitorados -
    intervalo mais espaçado que `run_login_status_snapshot_loop` (900s vs 300s) porque cada linha
    aqui exige uma chamada adicional à API do IXC (uma tabela diferente de `radusuarios`), e essa
    telemetria muda mais devagar que o status online/offline em si. Uma falha numa rodada não
    derruba o loop, só é logada."""
    POLL_SECONDS = 900.0
    while True:
        settings = get_settings()
        if not settings.ixc_api_base_url or not settings.ixc_api_token:
            await asyncio.sleep(POLL_SECONDS)
            continue
        try:
            client = get_ixc_client()
            with SessionLocal() as db:
                captured = await asyncio.to_thread(capture_onu_signal_snapshot, db, client)
            if captured:
                logger.info("Snapshot de sinal ONU capturado: %d linhas.", captured)
        except Exception:
            logger.exception("Falha ao capturar snapshot de sinal ONU.")
        await asyncio.sleep(POLL_SECONDS)
