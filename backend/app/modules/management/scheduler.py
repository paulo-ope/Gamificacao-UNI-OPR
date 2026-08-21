"""Geração automática de casos de gestão - 7o loop asyncio do backend, no mesmo padrão dos já
existentes (IXC, OPA, backlog snapshot, login status snapshot, ONU signal snapshot, UNI
Intelligence - ver app/main.py::lifespan).

Antes desta task, tanto `generate_performance_cases` (caso mensal) quanto
`get_or_create_daily_case` (caso de um dia especifico) só rodavam sob ação manual - o primeiro
quando alguém clicava em "Gerar casos do mês" em Gestão, o segundo quando o supervisor clicava em
"Justificar dia" num dia vermelho do calendário. Nenhum caso nascia sozinho, mesmo com desvio real
já visível na tela. Este loop fecha as duas lacunas, uma vez por dia cada:

- Mensal: verifica se o mês anterior (o único sempre fechado) já teve seus casos gerados e, se
  não, gera (`run_monthly_auto_generate_once`).
- Diário: verifica se ontem (o último dia sempre fechado) já teve seus casos de dia-abaixo-da-meta
  gerados e, se não, varre todo responsável/regional e abre um caso para todo dia que o calendário
  classificaria como vermelho (`run_daily_auto_generate_once`).

As duas funções de geração já são idempotentes, então rodar este loop mais de uma vez no mesmo dia
(ex.: reinício do processo) nunca duplica caso. Os botões manuais ("Gerar casos do mês" em Gestão,
"Justificar dia" no calendário) continuam existindo nas telas - úteis para reprocessar uma
competência/dia específico ou adiantar a geração sem esperar o próximo ciclo do loop."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.services.calculation import get_setting, upsert_setting

from .cases import generate_daily_cases_for_date, generate_performance_cases

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
DAILY_AUTO_GENERATE_LAST_RUN_DATE_KEY = "management_case_daily_auto_generate_last_run_date"


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


def run_monthly_auto_generate_once() -> dict | None:
    """Roda a geração mensal se ainda não rodou hoje (horário local de Rondônia). Devolve o
    resultado de `generate_performance_cases` quando roda, `None` quando pula (desligado ou já
    rodou hoje) - usado pelos testes para verificar o comportamento sem esperar o loop."""
    if not auto_generate_enabled():
        logger.info("Geração automática de casos: desligada (management_case_auto_generate_enabled=false).")
        return None
    today = datetime.now(MANAGEMENT_TIMEZONE).date()

    with SessionLocal() as db:
        last_run_raw = get_setting(db, AUTO_GENERATE_LAST_RUN_DATE_KEY, "")
        if last_run_raw == today.isoformat():
            logger.info("Geração automática de casos (mensal): já verificado hoje (%s), nada a fazer.", today.isoformat())
            return None
        year, month = previous_closed_period(today)
        result = generate_performance_cases(db, year=year, month=month, created_by=None)
        upsert_setting(db, AUTO_GENERATE_LAST_RUN_DATE_KEY, today.isoformat())
        db.commit()
        # Sempre loga o resultado, mesmo com 0 casos criados - silêncio total no log não deixa
        # distinguir "loop nunca rodou" de "rodou e não achou desvio", e essa distinção é
        # exatamente o que alguém verificando o deploy precisa ver.
        logger.info(
            "Geração automática de casos (mensal): %s caso(s) aberto(s) para %02d/%s (%s avaliado(s), %s já tinha(m) caso).",
            result["created_cases"],
            month,
            year,
            result["evaluated_members"],
            result["skipped_existing"],
        )
        return result


# Alias: nome usado antes desta task de adicionar o caso diário - mantido para não quebrar quem já
# chama `run_auto_generate_once` (ex.: testes existentes).
run_auto_generate_once = run_monthly_auto_generate_once


def run_daily_auto_generate_once() -> dict | None:
    """Roda a geração de casos diários (dia-abaixo-da-meta) se ainda não rodou hoje. Sempre para
    ONTEM (horário local de Rondônia) - o único dia sempre fechado; o dia corrente ainda está em
    andamento e um caso aberto sobre produção parcial do próprio dia seria prematuro. Devolve o
    resultado de `generate_daily_cases_for_date`, ou `None` quando pula (desligado ou já rodou
    hoje)."""
    if not auto_generate_enabled():
        return None
    today = datetime.now(MANAGEMENT_TIMEZONE).date()

    with SessionLocal() as db:
        last_run_raw = get_setting(db, DAILY_AUTO_GENERATE_LAST_RUN_DATE_KEY, "")
        if last_run_raw == today.isoformat():
            logger.info("Geração automática de casos (diária): já verificado hoje (%s), nada a fazer.", today.isoformat())
            return None
        yesterday = today - timedelta(days=1)
        result = generate_daily_cases_for_date(db, day=yesterday, created_by=None)
        upsert_setting(db, DAILY_AUTO_GENERATE_LAST_RUN_DATE_KEY, today.isoformat())
        db.commit()
        logger.info(
            "Geração automática de casos (diária): %s caso(s) aberto(s) para %s (%s avaliado(s), %s já tinha(m) caso).",
            result["created_cases"],
            result["reference_date"],
            result["evaluated_members"],
            result["already_open_cases"],
        )
        return result


async def run_management_case_scheduler_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(run_monthly_auto_generate_once)
        except Exception:  # nunca derruba o loop - mesma postura dos outros 6 loops do backend.
            logger.exception("Falha na geração automática de casos de gestão (mensal)")
        try:
            await asyncio.to_thread(run_daily_auto_generate_once)
        except Exception:
            logger.exception("Falha na geração automática de casos de gestão (diária)")
        await asyncio.sleep(MANAGEMENT_CASE_POLL_SECONDS)
