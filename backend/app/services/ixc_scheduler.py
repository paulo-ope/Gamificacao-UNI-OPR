from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.calculation import get_setting, recalculate_current_period, upsert_setting
from app.services.ixc_client import get_ixc_client
from app.services.ixc_importer import sync_ixc_service_orders

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
IXC_SYNC_LAST_ERROR_KEY = "ixc_sync_last_error"
IXC_SYNC_LAST_ERROR_AT_KEY = "ixc_sync_last_error_at"
IXC_SYNC_CONSECUTIVE_FAILURES_KEY = "ixc_sync_consecutive_failures"

# Configuráveis dentro da própria ferramenta (tela de configuração), não só via variável de ambiente/
# reinício do container - lidos do banco (`AppSetting`) a cada ciclo, então uma mudança feita na tela
# passa a valer no próximo ciclo, sem precisar reiniciar nada.
IXC_SYNC_ENABLED_KEY = "ixc_sync_enabled"
IXC_SYNC_INTERVAL_MINUTES_KEY = "ixc_sync_interval_minutes"
IXC_SYNC_AUTO_RECALCULATE_KEY = "ixc_sync_auto_recalculate"


def _current_sync_enabled(default: bool) -> bool:
    with SessionLocal() as db:
        raw = get_setting(db, IXC_SYNC_ENABLED_KEY, "")
    if not raw:
        return default
    return raw.strip().lower() in {"true", "1", "sim", "yes"}


def _current_interval_minutes(default: int) -> int:
    with SessionLocal() as db:
        raw = get_setting(db, IXC_SYNC_INTERVAL_MINUTES_KEY, "")
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minutes, 1)


def _auto_recalculate_enabled() -> bool:
    with SessionLocal() as db:
        raw = get_setting(db, IXC_SYNC_AUTO_RECALCULATE_KEY, "true")
    return raw.strip().lower() in {"true", "1", "sim", "yes"}


def run_ixc_sync_once() -> dict | None:
    """Roda uma sincronização e faz commit. Retorna None se IXC não estiver configurado."""
    settings = get_settings()
    if not settings.ixc_api_base_url or not settings.ixc_api_token:
        return None

    client = get_ixc_client()
    with SessionLocal() as db:
        try:
            result = sync_ixc_service_orders(db, client)
            upsert_setting(db, IXC_SYNC_LAST_SUCCESS_AT_KEY, datetime.now(timezone.utc).isoformat())
            upsert_setting(db, IXC_SYNC_CONSECUTIVE_FAILURES_KEY, "0")
            db.commit()
            logger.info("Sincronização IXC concluída: %s", result.get("summary"))
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

    summary = result.get("summary") or {}
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
    while True:
        if _current_sync_enabled(default=initial_enabled):
            await asyncio.to_thread(run_ixc_sync_once)
        current_interval = _current_interval_minutes(default=interval_minutes)
        await asyncio.sleep(current_interval * 60)
