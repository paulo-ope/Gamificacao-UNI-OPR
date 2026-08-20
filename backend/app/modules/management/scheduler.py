"""Geração automática de casos de gestão - 7o loop asyncio do backend, no mesmo padrão dos já
existentes (IXC, OPA, backlog snapshot, login status snapshot, ONU signal snapshot, UNI
Intelligence - ver app/main.py::lifespan).

Antes desta task, `generate_performance_cases` (cases.py) só rodava quando alguém entrava na tela
de Gestão e clicava em "Gerar casos do mês" - nenhum caso nascia sem essa ação manual, mesmo com
desvio real no mês já fechado. Este loop fecha essa lacuna: uma vez por dia, verifica se o mês
anterior (o único sempre fechado) já teve seus casos gerados e, se não, gera - sem exigir que
ninguém entre na tela. `generate_performance_cases` já é idempotente por competência, então rodar
este loop mais de uma vez no mesmo dia (ex.: reinício do processo) nunca duplica caso.

O botão manual "Gerar casos do mês" continua existindo na tela - útil para reprocessar uma
competência específica ou adiantar a geração sem esperar o próximo ciclo do loop."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.services.calculation import get_setting, upsert_setting

from .cases import generate_performance_cases

logger = logging.getLogger("management_case_scheduler")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

# A competência é sempre um mês fechado - checar uma vez por hora é mais que suficiente (a decisão
# real só muda uma vez por dia, quando a data local vira). Mesma ordem de grandeza do polling dos
# outros loops (ver INTELLIGENCE_POLL_SECONDS em intelligence/scheduler.py).
MANAGEMENT_CASE_POLL_SECONDS = 3600.0

MANAGEMENT_TIMEZONE = ZoneInfo("America/Porto_Velho")
AUTO_GENERATE_ENABLED_KEY = "management_case_auto_generate_enabled"
AUTO_GENERATE_LAST_RUN_DATE_KEY = "management_case_auto_generate_last_run_date"


def auto_generate_enabled() -> bool:
    try:
        with SessionLocal() as db:
            raw = get_setting(db, AUTO_GENERATE_ENABLED_KEY, "")
    except SQLAlchemyError:
        logger.warning("Geração automática de casos pausada: configurações do banco ainda não estão acessíveis.")
        return False
    if not raw:
        return True
    return raw.strip().lower() in {"true", "1", "sim", "yes"}


def set_auto_generate_enabled(enabled: bool) -> None:
    with SessionLocal() as db:
        upsert_setting(
            db,
            AUTO_GENERATE_ENABLED_KEY,
            "true" if enabled else "false",
            description="Gera automaticamente, uma vez por dia, os casos de produtividade do mês anterior já fechado.",
        )
        db.commit()


def previous_closed_period(today: date) -> tuple[int, int]:
    """O único mês sempre fechado em relação a `today` é o anterior - o mês corrente ainda está em
    andamento e teria dados incompletos (mesma régua do botão manual, ver `previousMonth` no
    frontend)."""
    first_of_month = today.replace(day=1)
    previous_day = first_of_month - timedelta(days=1)
    return previous_day.year, previous_day.month


def run_auto_generate_once() -> dict | None:
    """Roda a geração automática se ainda não rodou hoje (horário local de Rondônia). Devolve o
    resultado de `generate_performance_cases` quando roda, `None` quando pula (desligado ou já
    rodou hoje) - usado pelos testes para verificar o comportamento sem esperar o loop."""
    if not auto_generate_enabled():
        return None
    today = datetime.now(MANAGEMENT_TIMEZONE).date()

    with SessionLocal() as db:
        last_run_raw = get_setting(db, AUTO_GENERATE_LAST_RUN_DATE_KEY, "")
        if last_run_raw == today.isoformat():
            return None
        year, month = previous_closed_period(today)
        result = generate_performance_cases(db, year=year, month=month, created_by=None)
        upsert_setting(db, AUTO_GENERATE_LAST_RUN_DATE_KEY, today.isoformat())
        db.commit()
        if result["created_cases"]:
            logger.info(
                "Geração automática de casos: %s caso(s) aberto(s) para %02d/%s",
                result["created_cases"],
                month,
                year,
            )
        return result


async def run_management_case_scheduler_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(run_auto_generate_once)
        except Exception:  # nunca derruba o loop - mesma postura dos outros 6 loops do backend.
            logger.exception("Falha na geração automática de casos de gestão")
        await asyncio.sleep(MANAGEMENT_CASE_POLL_SECONDS)
