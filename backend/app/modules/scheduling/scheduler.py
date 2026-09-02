"""Loop de sincronização automática do módulo de Agendamento com o IXC.

Roda sempre em modo INCREMENTAL (a partir da marca d'água `scheduling_sync_last_event_at`, ver
`sync.py`) - nunca faz backfill grande sozinho. Sem marca d'água (nenhum backfill manual rodou
ainda), registra um erro controlado orientando a rodar `POST /scheduling/sync` com `date_from`/
`date_to` uma vez, e tenta de novo no próximo ciclo. Mesmo padrão de `app/services/ixc_scheduler.py`
e `app/services/opa_scheduler.py`: liga/desliga e intervalo controlados por `AppSetting`, lidos a
cada ciclo (dá pra mudar pela tela, sem reiniciar o backend); uma falha numa rodada nunca derruba o
loop, só é logada.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.scheduling.sync import run_sync
from app.services.calculation import get_setting, upsert_setting
from app.services.ixc_client import get_ixc_client

logger = logging.getLogger("scheduling_sync")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


SCHEDULING_SYNC_ENABLED_KEY = "scheduling_sync_enabled"
SCHEDULING_SYNC_INTERVAL_MINUTES_KEY = "scheduling_sync_interval_minutes"
SCHEDULING_SYNC_LAST_SUCCESS_AT_KEY = "scheduling_sync_last_success_at"
SCHEDULING_SYNC_LAST_ATTEMPT_AT_KEY = "scheduling_sync_last_attempt_at"
SCHEDULING_SYNC_NEXT_ALLOWED_AT_KEY = "scheduling_sync_next_allowed_at"
SCHEDULING_SYNC_LAST_ERROR_KEY = "scheduling_sync_last_error"
SCHEDULING_SYNC_LAST_ERROR_AT_KEY = "scheduling_sync_last_error_at"
SCHEDULING_SYNC_CONSECUTIVE_FAILURES_KEY = "scheduling_sync_consecutive_failures"

_NO_WATERMARK_ERROR = (
    "Sem marca d'água - rode um backfill manual (informando date_from/date_to em "
    "POST /scheduling/sync) antes da sincronização automática poder continuar."
)


def _current_sync_enabled(default: bool) -> bool:
    try:
        with SessionLocal() as db:
            raw = get_setting(db, SCHEDULING_SYNC_ENABLED_KEY, "")
    except SQLAlchemyError:
        logger.warning("Sincronização de Agendamento pausada: configurações do banco ainda não estão acessíveis.")
        return False
    if not raw:
        return default
    return raw.strip().lower() in {"true", "1", "sim", "yes"}


def _current_interval_minutes(default: int) -> int:
    try:
        with SessionLocal() as db:
            raw = get_setting(db, SCHEDULING_SYNC_INTERVAL_MINUTES_KEY, "")
    except SQLAlchemyError:
        return max(default, 1)
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minutes, 1)


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


def _seconds_until_next_sync(default_interval_minutes: int) -> float:
    current_interval = _current_interval_minutes(default=default_interval_minutes)
    now = datetime.now(timezone.utc)
    next_allowed_at = _setting_timestamp(SCHEDULING_SYNC_NEXT_ALLOWED_AT_KEY)
    if next_allowed_at is None:
        next_allowed_at = now + timedelta(minutes=current_interval)
        with SessionLocal() as db:
            upsert_setting(db, SCHEDULING_SYNC_NEXT_ALLOWED_AT_KEY, next_allowed_at.isoformat())
            db.commit()
    return max((next_allowed_at - now).total_seconds(), 0.0)


def _record_sync_attempt_started(interval_minutes: int) -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        upsert_setting(db, SCHEDULING_SYNC_LAST_ATTEMPT_AT_KEY, now.isoformat())
        upsert_setting(db, SCHEDULING_SYNC_NEXT_ALLOWED_AT_KEY, (now + timedelta(minutes=max(interval_minutes, 1))).isoformat())
        db.commit()


def _record_failure(db, message: str) -> None:
    try:
        failures = int(get_setting(db, SCHEDULING_SYNC_CONSECUTIVE_FAILURES_KEY, "0") or "0")
    except ValueError:
        failures = 0
    upsert_setting(db, SCHEDULING_SYNC_LAST_ERROR_KEY, message[:250])
    upsert_setting(db, SCHEDULING_SYNC_LAST_ERROR_AT_KEY, datetime.now(timezone.utc).isoformat())
    upsert_setting(db, SCHEDULING_SYNC_CONSECUTIVE_FAILURES_KEY, str(failures + 1))
    db.commit()


def run_scheduling_sync_once(interval_minutes: int | None = None) -> dict | None:
    """Roda um ciclo incremental (sem `date_from`/`date_to`). Retorna `None` se o IXC não estiver
    configurado, ou se a rodada falhar (erro já registrado em `AppSetting` para a tela consultar)."""
    settings = get_settings()
    if not settings.ixc_api_base_url or not settings.ixc_api_token:
        return None

    current_interval = interval_minutes or _current_interval_minutes(settings.scheduling_sync_interval_minutes)
    _record_sync_attempt_started(current_interval)

    with SessionLocal() as db:
        try:
            client = get_ixc_client()
            result = run_sync(db, client)
        except RuntimeError as exc:
            # Sem marca d'água: erro esperado e controlado - não é falha de integração, é uma
            # condição de pré-requisito (backfill manual inicial ainda não rodou).
            logger.warning("Sincronização automática de Agendamento não pôde continuar: %s", exc)
            _record_failure(db, str(exc) or _NO_WATERMARK_ERROR)
            return None
        except Exception as exc:
            db.rollback()
            logger.exception("Falha na sincronização periódica do módulo de Agendamento com o IXC")
            _record_failure(db, str(exc))
            return None

    with SessionLocal() as db:
        upsert_setting(db, SCHEDULING_SYNC_LAST_SUCCESS_AT_KEY, datetime.now(timezone.utc).isoformat())
        upsert_setting(db, SCHEDULING_SYNC_CONSECUTIVE_FAILURES_KEY, "0")
        db.commit()
    logger.info("Sincronização de Agendamento concluída: %s", result)
    return result


async def run_scheduling_sync_loop(interval_minutes: int, initial_enabled: bool = True) -> None:
    """Loop infinito: dorme, roda um ciclo incremental, repete. Uma falha (inclusive marca d'água
    ausente) nunca derruba o loop - só é registrada, e a próxima rodada tenta de novo."""
    POLL_SECONDS = 15.0

    while True:
        if not _current_sync_enabled(default=initial_enabled):
            await asyncio.sleep(POLL_SECONDS)
            continue

        wait_seconds = _seconds_until_next_sync(default_interval_minutes=interval_minutes)
        if wait_seconds > 0:
            await asyncio.sleep(min(wait_seconds, POLL_SECONDS))
            continue

        current_interval = _current_interval_minutes(default=interval_minutes)
        await asyncio.to_thread(run_scheduling_sync_once, current_interval)
