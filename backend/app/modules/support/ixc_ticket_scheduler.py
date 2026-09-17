"""Sincronização automática do atendimento IXC (`su_ticket`) e da base de clientes por regional
(`cliente_contrato`) - o usuário deixou claro que isso não é importação manual, é a mesma
sincronização contínua que já existe pra O.S. (ver docs/STATUS.md 2026-09-11: "a importação de
tudo é do IXC da aba atendimentos"). Mesmo padrão leve de `operations/login_status_snapshot.py`
(configurável só por `AppSetting`, sem variável de ambiente nova, roda sempre que o IXC estiver
configurado) - mais simples que `ixc_scheduler.py` porque não precisa de backlog particionado nem
de recálculo automático de nada.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.operations.customer_contract_ingestion import import_customer_contracts
from app.modules.support.opa_filters import SUPPORT_TIMEZONE
from app.services.calculation import get_setting, upsert_setting
from app.services.ixc_client import get_ixc_client

from .ixc_ticket_ingestion import import_tickets_for_period

logger = logging.getLogger(__name__)

SUPPORT_IXC_TICKET_SYNC_ENABLED_KEY = "support_ixc_ticket_sync_enabled"
SUPPORT_IXC_TICKET_SYNC_INTERVAL_MINUTES_KEY = "support_ixc_ticket_sync_interval_minutes"
SUPPORT_IXC_TICKET_SYNC_LOOKBACK_DAYS_KEY = "support_ixc_ticket_sync_lookback_days"
SUPPORT_IXC_TICKET_SYNC_DEFAULT_INTERVAL_MINUTES = 10
SUPPORT_IXC_TICKET_SYNC_MIN_INTERVAL_MINUTES = 2
SUPPORT_IXC_TICKET_SYNC_MAX_INTERVAL_MINUTES = 120
SUPPORT_IXC_TICKET_SYNC_DEFAULT_LOOKBACK_DAYS = 1

# Contrato de cliente é cadastro (não fluxo diário como atendimento) - re-sincronizar toda a
# `cliente_contrato` a cada ciclo curto seria desperdício de chamada ao IXC pra um dado que muda
# devagar. Roda só a cada N horas (mesma ideia de `IXC_SYNC_BACKLOG_SWEEP_INTERVAL_MINUTES` do
# scheduler de O.S., mas com intervalo maior porque contrato muda com frequência bem menor).
SUPPORT_IXC_CONTRACT_SYNC_LAST_AT_KEY = "support_ixc_contract_sync_last_at"
SUPPORT_IXC_CONTRACT_SYNC_INTERVAL_HOURS_KEY = "support_ixc_contract_sync_interval_hours"
SUPPORT_IXC_CONTRACT_SYNC_DEFAULT_INTERVAL_HOURS = 12

SUPPORT_IXC_TICKET_SYNC_LAST_SUCCESS_AT_KEY = "support_ixc_ticket_sync_last_success_at"
SUPPORT_IXC_TICKET_SYNC_LAST_ERROR_KEY = "support_ixc_ticket_sync_last_error"
SUPPORT_IXC_TICKET_SYNC_LAST_ERROR_AT_KEY = "support_ixc_ticket_sync_last_error_at"


def _sync_enabled(default: bool) -> bool:
    with SessionLocal() as db:
        raw = get_setting(db, SUPPORT_IXC_TICKET_SYNC_ENABLED_KEY, "")
    if not raw:
        return default
    return raw.strip().lower() in {"true", "1", "sim", "yes"}


def _interval_seconds() -> float:
    with SessionLocal() as db:
        raw = get_setting(db, SUPPORT_IXC_TICKET_SYNC_INTERVAL_MINUTES_KEY, "")
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        minutes = SUPPORT_IXC_TICKET_SYNC_DEFAULT_INTERVAL_MINUTES
    minutes = min(
        max(minutes, SUPPORT_IXC_TICKET_SYNC_MIN_INTERVAL_MINUTES), SUPPORT_IXC_TICKET_SYNC_MAX_INTERVAL_MINUTES
    )
    return minutes * 60.0


def _lookback_days() -> int:
    with SessionLocal() as db:
        raw = get_setting(db, SUPPORT_IXC_TICKET_SYNC_LOOKBACK_DAYS_KEY, "")
    try:
        return max(int(raw), 0)
    except (TypeError, ValueError):
        return SUPPORT_IXC_TICKET_SYNC_DEFAULT_LOOKBACK_DAYS


def _contract_sync_due(db) -> bool:
    raw = get_setting(db, SUPPORT_IXC_CONTRACT_SYNC_LAST_AT_KEY, "")
    if not raw:
        return True
    try:
        last_at = datetime.fromisoformat(raw)
    except ValueError:
        return True
    try:
        interval_hours = int(get_setting(db, SUPPORT_IXC_CONTRACT_SYNC_INTERVAL_HOURS_KEY, "") or "0")
    except ValueError:
        interval_hours = 0
    interval_hours = interval_hours or SUPPORT_IXC_CONTRACT_SYNC_DEFAULT_INTERVAL_HOURS
    return datetime.now(timezone.utc) - last_at >= timedelta(hours=interval_hours)


def run_ixc_ticket_sync_once() -> dict | None:
    """Roda um ciclo: importa `su_ticket` de hoje + lookback, e `cliente_contrato` quando devido.
    Retorna `None` se o IXC não estiver configurado."""
    settings = get_settings()
    if not settings.ixc_api_base_url or not settings.ixc_api_token:
        return None

    client = get_ixc_client()
    today = datetime.now(SUPPORT_TIMEZONE).date()
    lookback_days = _lookback_days()
    date_from = today - timedelta(days=lookback_days)

    with SessionLocal() as db:
        try:
            ticket_result = import_tickets_for_period(
                db,
                client,
                created_after=f"{date_from.isoformat()} 00:00:00",
                created_before=f"{today.isoformat()} 23:59:59",
            )

            contract_result = None
            if _contract_sync_due(db):
                contract_result = import_customer_contracts(db, client)
                upsert_setting(db, SUPPORT_IXC_CONTRACT_SYNC_LAST_AT_KEY, datetime.now(timezone.utc).isoformat())

            upsert_setting(db, SUPPORT_IXC_TICKET_SYNC_LAST_SUCCESS_AT_KEY, datetime.now(timezone.utc).isoformat())
            db.commit()
            logger.info("Sincronização de atendimento IXC concluída: %s", ticket_result)
            return {"tickets": ticket_result, "contracts": contract_result}
        except RuntimeError as exc:
            # Mesmo tratamento de `scheduling/scheduler.py`: "outra importação já em andamento" é
            # condição esperada (o ciclo anterior ainda não terminou, ex.: 552 mil tickets
            # históricos), não falha de integração - não marca `last_error`, só pula este ciclo.
            db.rollback()
            logger.warning("Sincronização automática de atendimento IXC não pôde continuar: %s", exc)
            return None
        except Exception as exc:
            db.rollback()
            logger.exception("Falha na sincronização periódica de atendimento IXC")
            upsert_setting(db, SUPPORT_IXC_TICKET_SYNC_LAST_ERROR_KEY, str(exc)[:250])
            upsert_setting(db, SUPPORT_IXC_TICKET_SYNC_LAST_ERROR_AT_KEY, datetime.now(timezone.utc).isoformat())
            db.commit()
            return None


async def run_ixc_ticket_sync_loop() -> None:
    """Loop infinito: mesmo formato de `login_status_snapshot.run_login_status_snapshot_loop` -
    dorme quando o IXC não está configurado ou a sincronização está desligada, senão roda um ciclo
    e dorme pelo intervalo configurado. Uma falha numa rodada não derruba o loop."""
    IDLE_POLL_SECONDS = 60.0
    while True:
        settings = get_settings()
        if not settings.ixc_api_base_url or not settings.ixc_api_token:
            await asyncio.sleep(IDLE_POLL_SECONDS)
            continue
        if not _sync_enabled(default=True):
            await asyncio.sleep(IDLE_POLL_SECONDS)
            continue
        await asyncio.to_thread(run_ixc_ticket_sync_once)
        await asyncio.sleep(_interval_seconds())
