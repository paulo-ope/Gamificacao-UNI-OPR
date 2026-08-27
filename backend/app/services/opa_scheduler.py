from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.support.opa_filters import SUPPORT_TIMEZONE
from app.modules.support.opa_ingestion import (
    OpaImportInterrupted,
    _maybe_mark_month_complete,
    _month_bounds,
    import_months_status,
    import_opa_attendances,
)
from app.services.calculation import get_setting, upsert_setting
from app.services.opa_client import get_opa_client

logger = logging.getLogger("opa_sync")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


SUPPORT_OPA_SYNC_ENABLED_KEY = "support_opa_sync_enabled"
SUPPORT_OPA_SYNC_INTERVAL_MINUTES_KEY = "support_opa_sync_interval_minutes"
SUPPORT_OPA_SYNC_LOOKBACK_DAYS_KEY = "support_opa_sync_lookback_days"
SUPPORT_OPA_SYNC_LAST_SUCCESS_AT_KEY = "support_opa_sync_last_success_at"
SUPPORT_OPA_SYNC_LAST_ATTEMPT_AT_KEY = "support_opa_sync_last_attempt_at"
SUPPORT_OPA_SYNC_NEXT_ALLOWED_AT_KEY = "support_opa_sync_next_allowed_at"
SUPPORT_OPA_SYNC_LAST_ERROR_KEY = "support_opa_sync_last_error"
SUPPORT_OPA_SYNC_LAST_ERROR_AT_KEY = "support_opa_sync_last_error_at"
SUPPORT_OPA_SYNC_CONSECUTIVE_FAILURES_KEY = "support_opa_sync_consecutive_failures"

SUPPORT_OPA_BACKFILL_ENABLED_KEY = "support_opa_backfill_enabled"
SUPPORT_OPA_BACKFILL_RUN_HOUR_KEY = "support_opa_backfill_run_hour"
SUPPORT_OPA_BACKFILL_LOOKBACK_MONTHS_KEY = "support_opa_backfill_lookback_months"
SUPPORT_OPA_BACKFILL_LAST_RUN_DATE_KEY = "support_opa_backfill_last_run_date"


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


def _current_sync_enabled(default: bool) -> bool:
    try:
        with SessionLocal() as db:
            raw = get_setting(db, SUPPORT_OPA_SYNC_ENABLED_KEY, "")
    except SQLAlchemyError:
        logger.warning("Sincronização OPA pausada: configurações do banco ainda não estão acessíveis.")
        return False
    if not raw:
        return default
    return raw.strip().lower() in {"true", "1", "sim", "yes"}


def _current_interval_minutes(default: int) -> int:
    try:
        with SessionLocal() as db:
            raw = get_setting(db, SUPPORT_OPA_SYNC_INTERVAL_MINUTES_KEY, "")
    except SQLAlchemyError:
        return max(default, 5)
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        return default
    return min(max(minutes, 5), 1440)


def _current_lookback_days(default: int) -> int:
    try:
        with SessionLocal() as db:
            raw = get_setting(db, SUPPORT_OPA_SYNC_LOOKBACK_DAYS_KEY, "")
    except SQLAlchemyError:
        return min(max(default, 1), 30)
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return min(max(default, 1), 30)
    return min(max(days, 1), 30)


def _setting_timestamp(key: str) -> datetime | None:
    try:
        with SessionLocal() as db:
            raw = get_setting(db, key, "")
    except SQLAlchemyError:
        return None
    return _parse_sync_timestamp(raw)


def _seconds_until_next_sync(default_interval_minutes: int) -> float:
    current_interval = _current_interval_minutes(default=default_interval_minutes)
    now = datetime.now(timezone.utc)
    next_allowed_at = _setting_timestamp(SUPPORT_OPA_SYNC_NEXT_ALLOWED_AT_KEY)
    if next_allowed_at is None:
        next_allowed_at = now + timedelta(minutes=current_interval)
        with SessionLocal() as db:
            upsert_setting(db, SUPPORT_OPA_SYNC_NEXT_ALLOWED_AT_KEY, next_allowed_at.isoformat())
            db.commit()
    return max((next_allowed_at - now).total_seconds(), 0.0)


def recompute_support_opa_next_allowed_at(db: Session, interval_minutes: int) -> None:
    last_attempt_at = _setting_timestamp(SUPPORT_OPA_SYNC_LAST_ATTEMPT_AT_KEY)
    base = last_attempt_at or datetime.now(timezone.utc)
    upsert_setting(db, SUPPORT_OPA_SYNC_NEXT_ALLOWED_AT_KEY, (base + timedelta(minutes=max(interval_minutes, 5))).isoformat())


def _record_sync_attempt_started(interval_minutes: int) -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        upsert_setting(db, SUPPORT_OPA_SYNC_LAST_ATTEMPT_AT_KEY, now.isoformat())
        upsert_setting(db, SUPPORT_OPA_SYNC_NEXT_ALLOWED_AT_KEY, (now + timedelta(minutes=max(interval_minutes, 5))).isoformat())
        db.commit()


def _push_next_allowed_at_from_now(db: Session, interval_minutes: int) -> None:
    """Recalcula `next_allowed_at` a partir do FIM da execução, não do início.

    Antes, `next_allowed_at` era fixado em `_record_sync_attempt_started` só com base no
    início da tentativa. Como a rotina agora busca mensagens por atendimento para TMR,
    um ciclo pode durar mais que o intervalo configurado — nesse caso o valor calculado
    no início já ficava no passado quando a run terminava, e a UI mostrava "próxima
    janela" atrasada mesmo com tudo funcionando, ou o loop tentava iniciar de novo
    imediatamente. Recalcular no fim garante que o intervalo seja respeitado a partir de
    quando a execução anterior realmente terminou.
    """
    now = datetime.now(timezone.utc)
    upsert_setting(db, SUPPORT_OPA_SYNC_NEXT_ALLOWED_AT_KEY, (now + timedelta(minutes=max(interval_minutes, 5))).isoformat())


def run_opa_sync_once(interval_minutes: int | None = None) -> dict | None:
    settings = get_settings()
    if not settings.opa_api_base_url or not settings.opa_api_token:
        return None

    current_interval = interval_minutes or _current_interval_minutes(settings.opa_sync_interval_minutes)
    _record_sync_attempt_started(current_interval)
    lookback_days = _current_lookback_days(settings.opa_sync_lookback_days)
    today = datetime.now(SUPPORT_TIMEZONE).date()
    days = [today - timedelta(days=offset) for offset in range(lookback_days, -1, -1)]

    client = get_opa_client()
    with SessionLocal() as db:
        try:
            imports = [
                import_opa_attendances(db, client, date_from=day, date_to=day, imported_by=None)
                for day in days
            ]
            upsert_setting(db, SUPPORT_OPA_SYNC_LAST_SUCCESS_AT_KEY, datetime.now(timezone.utc).isoformat())
            upsert_setting(db, SUPPORT_OPA_SYNC_CONSECUTIVE_FAILURES_KEY, "0")
            _push_next_allowed_at_from_now(db, current_interval)
            db.commit()
            logger.info("Sincronização OPA concluída: %s", imports)
            return {"imports": imports}
        except OpaImportInterrupted as exc:
            logger.exception("Sincronização periódica OPA interrompida")
            try:
                failures = int(get_setting(db, SUPPORT_OPA_SYNC_CONSECUTIVE_FAILURES_KEY, "0") or "0")
            except ValueError:
                failures = 0
            upsert_setting(db, SUPPORT_OPA_SYNC_LAST_ERROR_KEY, f"Run #{exc.run_id} interrompido: {str(exc)[:200]}")
            upsert_setting(db, SUPPORT_OPA_SYNC_LAST_ERROR_AT_KEY, datetime.now(timezone.utc).isoformat())
            upsert_setting(db, SUPPORT_OPA_SYNC_CONSECUTIVE_FAILURES_KEY, str(failures + 1))
            _push_next_allowed_at_from_now(db, current_interval)
            db.commit()
            return None
        except Exception as exc:
            db.rollback()
            logger.exception("Falha na sincronização periódica com o OPA Suite")
            try:
                failures = int(get_setting(db, SUPPORT_OPA_SYNC_CONSECUTIVE_FAILURES_KEY, "0") or "0")
            except ValueError:
                failures = 0
            upsert_setting(db, SUPPORT_OPA_SYNC_LAST_ERROR_KEY, str(exc)[:250])
            upsert_setting(db, SUPPORT_OPA_SYNC_LAST_ERROR_AT_KEY, datetime.now(timezone.utc).isoformat())
            upsert_setting(db, SUPPORT_OPA_SYNC_CONSECUTIVE_FAILURES_KEY, str(failures + 1))
            _push_next_allowed_at_from_now(db, current_interval)
            db.commit()
            return None


def _current_backfill_enabled(default: bool) -> bool:
    try:
        with SessionLocal() as db:
            raw = get_setting(db, SUPPORT_OPA_BACKFILL_ENABLED_KEY, "")
    except SQLAlchemyError:
        return default
    if not raw:
        return default
    return raw.strip().lower() in {"true", "1", "sim", "yes"}


def _current_backfill_run_hour(default: int) -> int:
    try:
        with SessionLocal() as db:
            raw = get_setting(db, SUPPORT_OPA_BACKFILL_RUN_HOUR_KEY, "")
    except SQLAlchemyError:
        return default
    try:
        hour = int(raw)
    except (TypeError, ValueError):
        return default
    return min(max(hour, 0), 23)


def _current_backfill_lookback_months(default: int) -> int:
    try:
        with SessionLocal() as db:
            raw = get_setting(db, SUPPORT_OPA_BACKFILL_LOOKBACK_MONTHS_KEY, "")
    except SQLAlchemyError:
        return default
    try:
        months = int(raw)
    except (TypeError, ValueError):
        return default
    return min(max(months, 1), 24)


def _target_backfill_months(today, lookback_months: int) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year, month = today.year, today.month
    for _ in range(lookback_months):
        months.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    months.reverse()
    return months


def run_opa_backfill_once(lookback_months: int | None = None) -> dict | None:
    """Backfill diário de meses calendário completos - roda 1x por dia, a partir da
    hora configurada (`SUPPORT_OPA_BACKFILL_RUN_HOUR_KEY`), e importa (mês inteiro,
    `date_from`/`date_to` no 1º e último dia) qualquer um dos últimos N meses que
    ainda não está marcado "complete" em `SupportOpaImportMonth`. Auto-gated por
    data (mesmo padrão de `management/scheduler.py`): se já rodou hoje, não roda de
    novo, mesmo chamado várias vezes no mesmo dia."""
    settings = get_settings()
    if not settings.opa_api_base_url or not settings.opa_api_token:
        return None

    months = lookback_months or _current_backfill_lookback_months(3)
    today = datetime.now(SUPPORT_TIMEZONE).date()
    target_months = _target_backfill_months(today, months)
    year_months = [f"{year:04d}-{month:02d}" for year, month in target_months]

    with SessionLocal() as db:
        status_by_month = import_months_status(db, year_months)
    pending_months = [
        (year, month) for (year, month), year_month in zip(target_months, year_months)
        if status_by_month[year_month]["status"] != "complete"
    ]
    if not pending_months:
        with SessionLocal() as db:
            upsert_setting(db, SUPPORT_OPA_BACKFILL_LAST_RUN_DATE_KEY, today.isoformat())
            db.commit()
        return {"imported_months": []}

    client = get_opa_client()
    imported: list[dict] = []
    for year, month in pending_months:
        date_from, date_to = _month_bounds(year, month)
        with SessionLocal() as db:
            try:
                result = import_opa_attendances(db, client, date_from=date_from, date_to=date_to, imported_by=None)
                db.commit()
                _maybe_mark_month_complete(
                    db, run_id=result["run_id"], date_from=date_from, date_to=date_to, status=result["status"]
                )
                imported.append({"year_month": f"{year:04d}-{month:02d}", **result})
                logger.info("Backfill OPA: mês %04d-%02d -> %s", year, month, result["status"])
            except OpaImportInterrupted as exc:
                db.commit()
                logger.exception("Backfill OPA interrompido no mês %04d-%02d (run #%s)", year, month, exc.run_id)
            except Exception:
                db.rollback()
                logger.exception("Falha no backfill OPA do mês %04d-%02d", year, month)

    with SessionLocal() as db:
        upsert_setting(db, SUPPORT_OPA_BACKFILL_LAST_RUN_DATE_KEY, today.isoformat())
        db.commit()
    return {"imported_months": imported}


def _backfill_due(default_enabled: bool, default_run_hour: int) -> bool:
    if not _current_backfill_enabled(default=default_enabled):
        return False
    now_local = datetime.now(SUPPORT_TIMEZONE)
    run_hour = _current_backfill_run_hour(default=default_run_hour)
    if now_local.hour < run_hour:
        return False
    try:
        with SessionLocal() as db:
            last_run_raw = get_setting(db, SUPPORT_OPA_BACKFILL_LAST_RUN_DATE_KEY, "")
    except SQLAlchemyError:
        return False
    return last_run_raw != now_local.date().isoformat()


async def run_opa_sync_loop(interval_minutes: int, initial_enabled: bool = True) -> None:
    poll_seconds = 15.0
    while True:
        if _backfill_due(default_enabled=True, default_run_hour=3):
            try:
                await asyncio.to_thread(run_opa_backfill_once)
            except Exception:
                logger.exception("Falha ao rodar o backfill automático de meses do OPA Suite")

        if not _current_sync_enabled(default=initial_enabled):
            await asyncio.sleep(poll_seconds)
            continue

        wait_seconds = _seconds_until_next_sync(default_interval_minutes=interval_minutes)
        if wait_seconds > 0:
            await asyncio.sleep(min(wait_seconds, poll_seconds))
            continue

        current_interval = _current_interval_minutes(default=interval_minutes)
        await asyncio.to_thread(run_opa_sync_once, current_interval)
