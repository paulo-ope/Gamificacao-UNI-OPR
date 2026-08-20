from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.support.opa_ingestion import OpaImportInterrupted, import_opa_attendances
from app.services.calculation import get_setting, upsert_setting
from app.services.opa_client import get_opa_client

logger = logging.getLogger("opa_sync")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


SUPPORT_TIMEZONE = ZoneInfo("America/Porto_Velho")
SUPPORT_OPA_SYNC_ENABLED_KEY = "support_opa_sync_enabled"
SUPPORT_OPA_SYNC_INTERVAL_MINUTES_KEY = "support_opa_sync_interval_minutes"
SUPPORT_OPA_SYNC_LOOKBACK_DAYS_KEY = "support_opa_sync_lookback_days"
SUPPORT_OPA_SYNC_LAST_SUCCESS_AT_KEY = "support_opa_sync_last_success_at"
SUPPORT_OPA_SYNC_LAST_ATTEMPT_AT_KEY = "support_opa_sync_last_attempt_at"
SUPPORT_OPA_SYNC_NEXT_ALLOWED_AT_KEY = "support_opa_sync_next_allowed_at"
SUPPORT_OPA_SYNC_LAST_ERROR_KEY = "support_opa_sync_last_error"
SUPPORT_OPA_SYNC_LAST_ERROR_AT_KEY = "support_opa_sync_last_error_at"
SUPPORT_OPA_SYNC_CONSECUTIVE_FAILURES_KEY = "support_opa_sync_consecutive_failures"


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
            db.commit()
            return None


async def run_opa_sync_loop(interval_minutes: int, initial_enabled: bool = True) -> None:
    poll_seconds = 15.0
    while True:
        if not _current_sync_enabled(default=initial_enabled):
            await asyncio.sleep(poll_seconds)
            continue

        wait_seconds = _seconds_until_next_sync(default_interval_minutes=interval_minutes)
        if wait_seconds > 0:
            await asyncio.sleep(min(wait_seconds, poll_seconds))
            continue

        current_interval = _current_interval_minutes(default=interval_minutes)
        await asyncio.to_thread(run_opa_sync_once, current_interval)
