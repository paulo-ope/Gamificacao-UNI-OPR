from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.operations.ixc_ingestion import import_current_month_period, import_open_backlog
from app.modules.operations.period import OPERATIONS_TIMEZONE
from app.modules.operations.scope import PRIMARY_IXC_SECTOR_IDS, normalize_ixc_sector_ids
from app.services.calculation import get_setting, recalculate_current_period, upsert_setting
from app.services.ixc_client import IxcClient, get_ixc_client
from app.services.operations_sync import run_operations_to_service_orders_sync

logger = logging.getLogger("ixc_sync")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

# Chaves de saúde da sincronização (AppSetting) - não existe infra de e-mail/webhook neste projeto para
# alertar ativamente, então isso fica gravado e exposto por uma rota (ver imports.py) para alguém checar.
# Sem isso, uma falha silenciosa (token expirado, IXC fora do ar) só é percebida quando alguém notar que
# os números não batem - já aconteceu nesta integração (ver docs/plano-integracao-ixc.md).
IXC_SYNC_LAST_SUCCESS_AT_KEY = "ixc_sync_last_success_at"
IXC_SYNC_LAST_ATTEMPT_AT_KEY = "ixc_sync_last_attempt_at"
IXC_SYNC_NEXT_ALLOWED_AT_KEY = "ixc_sync_next_allowed_at"
IXC_SYNC_LAST_ERROR_KEY = "ixc_sync_last_error"
IXC_SYNC_LAST_ERROR_AT_KEY = "ixc_sync_last_error_at"
IXC_SYNC_CONSECUTIVE_FAILURES_KEY = "ixc_sync_consecutive_failures"

# Configuráveis dentro da própria ferramenta (tela de configuração), não só via variável de ambiente/
# reinício do container - lidos do banco (`AppSetting`) a cada ciclo, então uma mudança feita na tela
# passa a valer no próximo ciclo, sem precisar reiniciar nada.
IXC_SYNC_ENABLED_KEY = "ixc_sync_enabled"
IXC_SYNC_INTERVAL_MINUTES_KEY = "ixc_sync_interval_minutes"
IXC_SYNC_AUTO_RECALCULATE_KEY = "ixc_sync_auto_recalculate"
IXC_SYNC_SECTOR_IDS_KEY = "ixc_sync_sector_ids"

# Quantos dias antes de hoje o ciclo automático (todo ciclo, não só o backlog periódico) reimporta -
# cobre O.S. que só fecham/atualizam alguns dias depois de abertas. Configurável pela tela (evita
# precisar de um backfill manual toda vez que esse recorte precisar crescer).
IXC_SYNC_LOOKBACK_DAYS_KEY = "ixc_sync_lookback_days"
IXC_SYNC_DEFAULT_LOOKBACK_DAYS = 1

# A varredura de backlog aberto (`import_open_backlog`) particiona a consulta por setor x status
# (3 setores x 9 códigos = ~27 chamadas sequenciais ao IXC) - rodar isso em TODO ciclo do polling
# (a cada poucos minutos) prendia a conexão/transação do banco por dezenas de segundos e deixava
# outras requisições (ex.: o resumo do dashboard) esperando na fila. A importação do período
# (hoje/ontem, ~4 chamadas) continua todo ciclo; a varredura de backlog roda só a cada
# `IXC_SYNC_BACKLOG_SWEEP_INTERVAL_MINUTES` (configurável, mesmo padrão AppSetting das outras
# chaves desta sincronização).
IXC_SYNC_LAST_BACKLOG_SWEEP_AT_KEY = "ixc_sync_last_backlog_sweep_at"
IXC_SYNC_BACKLOG_SWEEP_INTERVAL_MINUTES_KEY = "ixc_sync_backlog_sweep_interval_minutes"
IXC_SYNC_DEFAULT_BACKLOG_SWEEP_INTERVAL_MINUTES = 60


def _current_sync_enabled(default: bool) -> bool:
    try:
        with SessionLocal() as db:
            raw = get_setting(db, IXC_SYNC_ENABLED_KEY, "")
    except SQLAlchemyError:
        logger.warning("Sincronizacao IXC pausada: configuracoes do banco ainda nao estao acessiveis.")
        return False
    if not raw:
        return default
    return raw.strip().lower() in {"true", "1", "sim", "yes"}


def _current_interval_minutes(default: int) -> int:
    try:
        with SessionLocal() as db:
            raw = get_setting(db, IXC_SYNC_INTERVAL_MINUTES_KEY, "")
    except SQLAlchemyError:
        return max(default, 1)
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minutes, 1)


def _current_lookback_days() -> int:
    try:
        with SessionLocal() as db:
            raw = get_setting(db, IXC_SYNC_LOOKBACK_DAYS_KEY, "")
    except SQLAlchemyError:
        return IXC_SYNC_DEFAULT_LOOKBACK_DAYS
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return IXC_SYNC_DEFAULT_LOOKBACK_DAYS
    return min(max(days, 1), 30)


def _current_sector_ids() -> list[str]:
    try:
        with SessionLocal() as db:
            raw = get_setting(db, IXC_SYNC_SECTOR_IDS_KEY, "")
    except SQLAlchemyError:
        return list(PRIMARY_IXC_SECTOR_IDS)
    if not raw:
        return list(PRIMARY_IXC_SECTOR_IDS)
    try:
        return normalize_ixc_sector_ids(raw.split(","))
    except ValueError:
        logger.warning("Escopo de setores IXC invalido em app_settings; usando setores principais.")
        return list(PRIMARY_IXC_SECTOR_IDS)


def _parse_sync_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _setting_timestamp(key: str) -> datetime | None:
    try:
        with SessionLocal() as db:
            raw = get_setting(db, key, "")
    except SQLAlchemyError:
        return None
    return _parse_sync_timestamp(raw)


def _sync_wait_seconds(next_allowed_at: datetime | None, interval_minutes: int, *, now: datetime | None = None) -> float:
    interval_seconds = max(interval_minutes, 1) * 60
    if next_allowed_at is None:
        return float(interval_seconds)

    if next_allowed_at.tzinfo is None:
        next_allowed_at = next_allowed_at.replace(tzinfo=timezone.utc)
    else:
        next_allowed_at = next_allowed_at.astimezone(timezone.utc)

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    else:
        current_time = current_time.astimezone(timezone.utc)

    return max((next_allowed_at - current_time).total_seconds(), 0.0)


def _seconds_until_next_sync(default_interval_minutes: int) -> float:
    current_interval = _current_interval_minutes(default=default_interval_minutes)
    now = datetime.now(timezone.utc)
    next_allowed_at = _setting_timestamp(IXC_SYNC_NEXT_ALLOWED_AT_KEY)
    if next_allowed_at is None:
        next_allowed_at = now + timedelta(minutes=max(current_interval, 1))
        with SessionLocal() as db:
            upsert_setting(
                db,
                IXC_SYNC_NEXT_ALLOWED_AT_KEY,
                next_allowed_at.isoformat(),
                description="Proximo horario em que a sincronizacao automatica pode consultar o IXC.",
            )
            db.commit()
    return _sync_wait_seconds(next_allowed_at, current_interval, now=now)


def _record_sync_attempt_started(interval_minutes: int | None = None) -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        upsert_setting(
            db,
            IXC_SYNC_LAST_ATTEMPT_AT_KEY,
            now.isoformat(),
            description="Ultima tentativa de sincronizacao automatica com o IXC.",
        )
        if interval_minutes is not None:
            next_allowed_at = now + timedelta(minutes=max(interval_minutes, 1))
            upsert_setting(
                db,
                IXC_SYNC_NEXT_ALLOWED_AT_KEY,
                next_allowed_at.isoformat(),
                description="Proximo horario em que a sincronizacao automatica pode consultar o IXC.",
            )
        db.commit()


def recompute_next_allowed_at(db: Session, interval_minutes: int) -> None:
    """Chamado pela tela de configuração quando o intervalo muda - recalcula `next_allowed_at` a
    partir da última tentativa registrada. Sem isso, baixar o intervalo de 60 para 5 min só valeria
    na tentativa seguinte ao horário antigo (até 1h depois) ou exigiria reiniciar o backend, porque
    `next_allowed_at` é um horário absoluto já gravado com o intervalo anterior.
    """
    last_attempt_at = _setting_timestamp(IXC_SYNC_LAST_ATTEMPT_AT_KEY)
    base = last_attempt_at or datetime.now(timezone.utc)
    next_allowed_at = base + timedelta(minutes=max(interval_minutes, 1))
    upsert_setting(
        db,
        IXC_SYNC_NEXT_ALLOWED_AT_KEY,
        next_allowed_at.isoformat(),
        description="Proximo horario em que a sincronizacao automatica pode consultar o IXC.",
    )


def _auto_recalculate_enabled() -> bool:
    with SessionLocal() as db:
        raw = get_setting(db, IXC_SYNC_AUTO_RECALCULATE_KEY, "true")
    return raw.strip().lower() in {"true", "1", "sim", "yes"}


def _backlog_sweep_interval_minutes(db: Session) -> int:
    raw = get_setting(db, IXC_SYNC_BACKLOG_SWEEP_INTERVAL_MINUTES_KEY, "")
    try:
        return max(int(raw), 1)
    except (TypeError, ValueError):
        return IXC_SYNC_DEFAULT_BACKLOG_SWEEP_INTERVAL_MINUTES


def _should_run_backlog_sweep(db: Session) -> bool:
    last_swept_at = _parse_sync_timestamp(get_setting(db, IXC_SYNC_LAST_BACKLOG_SWEEP_AT_KEY, ""))
    if last_swept_at is None:
        return True
    interval = timedelta(minutes=_backlog_sweep_interval_minutes(db))
    return datetime.now(timezone.utc) - last_swept_at >= interval


def _run_operations_ixc_import_cycle(db: Session, client: IxcClient) -> dict:
    """Único ponto do sistema que consulta O.S. no IXC (`fetch_service_orders`). Importa para
    `operations_orders` (módulo de operações analíticas) hoje e os `IXC_SYNC_LOOKBACK_DAYS_KEY` dias
    anteriores (pega O.S. que atravessam a meia-noite ou só fecham/atualizam alguns dias depois de
    abertas) todo ciclo, e periodicamente (não todo ciclo - ver
    `IXC_SYNC_BACKLOG_SWEEP_INTERVAL_MINUTES_KEY`) o backlog aberto corrente. Em seguida projeta o
    resultado em `service_orders` (ver `run_operations_to_service_orders_sync`) - a gamificação não
    faz mais nenhuma chamada direta ao IXC, ela só lê o que o módulo operations já importou.
    """
    today = datetime.now(OPERATIONS_TIMEZONE).date()
    lookback_days = _current_lookback_days()
    days = [today - timedelta(days=offset) for offset in range(lookback_days, -1, -1)]
    sector_ids = _current_sector_ids()

    operations_imports = []
    for day in days:
        operations_imports.append(
            import_current_month_period(
                db, client, date_from=day, date_to=day, imported_by=None, sector_ids=sector_ids,
            )
        )

    ran_backlog_sweep = _should_run_backlog_sweep(db)
    if ran_backlog_sweep:
        operations_imports.append(
            import_open_backlog(db, client, imported_by=None, sector_ids=sector_ids)
        )
        upsert_setting(db, IXC_SYNC_LAST_BACKLOG_SWEEP_AT_KEY, datetime.now(timezone.utc).isoformat())
    db.commit()

    service_orders_sync = run_operations_to_service_orders_sync(db, imported_by=None)
    db.commit()

    return {
        "operations_imports": operations_imports,
        "ran_backlog_sweep": ran_backlog_sweep,
        "service_orders_sync": service_orders_sync,
    }


def run_ixc_sync_once(interval_minutes: int | None = None) -> dict | None:
    """Roda um ciclo completo (importação analítica do IXC + projeção para `service_orders`) e faz
    commit. Retorna None se IXC não estiver configurado."""
    settings = get_settings()
    if not settings.ixc_api_base_url or not settings.ixc_api_token:
        return None

    _record_sync_attempt_started(interval_minutes=interval_minutes)
    client = get_ixc_client()
    with SessionLocal() as db:
        try:
            result = _run_operations_ixc_import_cycle(db, client)
            upsert_setting(db, IXC_SYNC_LAST_SUCCESS_AT_KEY, datetime.now(timezone.utc).isoformat())
            upsert_setting(db, IXC_SYNC_CONSECUTIVE_FAILURES_KEY, "0")
            db.commit()
            logger.info(
                "Sincronização IXC concluída: %s",
                result["service_orders_sync"].get("summary"),
            )
        except Exception as exc:
            db.rollback()
            logger.exception("Falha na sincronização periódica com o IXC")
            try:
                failures = int(get_setting(db, IXC_SYNC_CONSECUTIVE_FAILURES_KEY, "0") or "0")
            except ValueError:
                failures = 0
            upsert_setting(db, IXC_SYNC_LAST_ERROR_KEY, str(exc)[:250])
            upsert_setting(db, IXC_SYNC_LAST_ERROR_AT_KEY, datetime.now(timezone.utc).isoformat())
            upsert_setting(db, IXC_SYNC_CONSECUTIVE_FAILURES_KEY, str(failures + 1))
            db.commit()
            return None

    summary = result["service_orders_sync"].get("summary") or {}
    touched = int(summary.get("created_count", 0)) + int(summary.get("updated_count", 0))
    if touched > 0 and _auto_recalculate_enabled():
        with SessionLocal() as db:
            recalculate_current_period(db, execution_note="Recálculo automático após sincronização com o IXC.")

    return result


async def run_ixc_sync_loop(interval_minutes: int, initial_enabled: bool = True) -> None:
    """Loop infinito: roda a sincronização, dorme, repete. Uma falha numa rodada não derruba o loop -
    só é logada, e a próxima rodada tenta de novo.

    `interval_minutes`/`initial_enabled` são só os valores iniciais (do ambiente, `.env`) - a cada ciclo,
    o intervalo e se a sincronização está ligada são relidos do banco (`AppSetting`), então dá pra mudar
    isso pela própria tela de configuração, sem reiniciar o backend. Enquanto ninguém mexer na tela, o
    comportamento é exatamente o mesmo de antes (controlado só pelo `.env`).
    """
    # Dormir em fatias curtas (em vez de um único `sleep(wait_seconds)`) para que uma mudança de
    # intervalo feita na tela de configuração enquanto o loop está dormindo valha em segundos, não
    # só depois que o sono antigo (calculado com o intervalo anterior) terminar sozinho.
    POLL_SECONDS = 15.0

    while True:
        if not _current_sync_enabled(default=initial_enabled):
            await asyncio.sleep(POLL_SECONDS)
            continue

        wait_seconds = _seconds_until_next_sync(default_interval_minutes=interval_minutes)
        if wait_seconds > 0:
            await asyncio.sleep(min(wait_seconds, POLL_SECONDS))
            continue

        # `run_ixc_sync_once` já grava o próximo `next_allowed_at` (ver `_record_sync_attempt_started`),
        # então a próxima iteração recalcula a espera correta sozinha - dormir de novo aqui dobraria
        # o intervalo configurado a cada ciclo.
        current_interval = _current_interval_minutes(default=interval_minutes)
        await asyncio.to_thread(run_ixc_sync_once, current_interval)
