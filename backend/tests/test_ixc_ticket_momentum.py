"""Fase 4 do plano de evolução analítica do Atendimento IXC (2026-09-15): `MOMENTUM_V1` -
tendência recente de um escopo (`ixc_ticket_momentum.py`), complementar ao desvio pontual e ao
burst horário."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.support import ixc_ticket_momentum
from app.modules.support.models import SupportIxcTicket

REGIONAL = "UNI - NOVA BRASILANDIA DOESTE"
REFERENCE = datetime(2026, 9, 15, tzinfo=timezone.utc)  # "hoje" nos testes - só "ontem" pra trás conta


def _tickets_on(db, day_offset_from_reference, count, *, source_prefix, regional=REGIONAL):
    day = REFERENCE - timedelta(days=day_offset_from_reference)
    for i in range(count):
        db.add(SupportIxcTicket(source_id=f"{source_prefix}-{day_offset_from_reference}-{i}", regional=regional, created_at=day))


def test_daily_momentum_flags_accelerating_when_recent_average_jumps(db_session):
    """3 dias recentes (ontem, anteontem, retrasado) com volume bem maior que os 3 dias
    imediatamente anteriores -> `change_pct` positivo alto, `trend="accelerating"`."""
    for offset in (1, 2, 3):
        _tickets_on(db_session, offset, 10, source_prefix="RECENT")
    for offset in (4, 5, 6):
        _tickets_on(db_session, offset, 5, source_prefix="PREV")
    db_session.commit()

    result = ixc_ticket_momentum.daily_momentum(db_session, regional=REGIONAL, reference_date=REFERENCE.date())

    assert result["recent_avg"] == 10.0
    assert result["previous_avg"] == 5.0
    assert result["change_pct"] == 100.0
    assert result["trend"] == "accelerating"


def test_daily_momentum_flags_decelerating_when_recent_average_drops(db_session):
    for offset in (1, 2, 3):
        _tickets_on(db_session, offset, 2, source_prefix="RECENT")
    for offset in (4, 5, 6):
        _tickets_on(db_session, offset, 10, source_prefix="PREV")
    db_session.commit()

    result = ixc_ticket_momentum.daily_momentum(db_session, regional=REGIONAL, reference_date=REFERENCE.date())

    assert result["trend"] == "decelerating"
    assert result["change_pct"] < 0


def test_daily_momentum_is_stable_when_change_is_within_the_neutral_band(db_session):
    for offset in (1, 2, 3):
        _tickets_on(db_session, offset, 10, source_prefix="RECENT")
    for offset in (4, 5, 6):
        _tickets_on(db_session, offset, 9, source_prefix="PREV")
    db_session.commit()

    result = ixc_ticket_momentum.daily_momentum(db_session, regional=REGIONAL, reference_date=REFERENCE.date())

    assert result["trend"] == "stable"


def test_daily_momentum_is_sem_dado_when_there_is_no_previous_history(db_session):
    """Sem nenhum ticket no período anterior, `previous_avg=0` não pode virar divisão por zero -
    o contrato é `change_pct=None`/`trend="sem_dado"`, não um erro nem um "infinito"."""
    for offset in (1, 2, 3):
        _tickets_on(db_session, offset, 5, source_prefix="RECENT")
    db_session.commit()

    result = ixc_ticket_momentum.daily_momentum(db_session, regional=REGIONAL, reference_date=REFERENCE.date())

    assert result["previous_avg"] == 0.0
    assert result["change_pct"] is None
    assert result["trend"] == "sem_dado"


def test_daily_momentum_excludes_todays_partial_day(db_session):
    """Ticket criado HOJE (dia em andamento) não pode contar em `recent_avg` - só dias já
    fechados (a partir de ontem) entram na conta."""
    _tickets_on(db_session, 0, 999, source_prefix="TODAY")  # offset 0 = hoje
    for offset in (1, 2, 3):
        _tickets_on(db_session, offset, 1, source_prefix="RECENT")
    db_session.commit()

    result = ixc_ticket_momentum.daily_momentum(db_session, regional=REGIONAL, reference_date=REFERENCE.date())

    assert result["recent_avg"] == 1.0


def test_daily_momentum_counts_consecutive_days_above_expected(db_session):
    """`consecutive_days_above_expected` conta, a partir de ontem pra trás, quantos dias seguidos
    superaram o próprio esperado (média do mesmo dia-da-semana nas semanas anteriores) - pára no
    primeiro dia que não superar."""
    # Ontem e anteontem bem acima do normal (que é baixo, por causa das semanas anteriores).
    for offset in (1, 2):
        _tickets_on(db_session, offset, 20, source_prefix="SPIKE")
    # Dia 3 (retrasado) normal.
    _tickets_on(db_session, 3, 1, source_prefix="NORMAL")
    # Mesmos dias-da-semana de offset 1 e 2, em semanas anteriores (baixo volume - "esperado").
    for week in range(1, 5):
        _tickets_on(db_session, 1 + week * 7, 1, source_prefix=f"HIST1-{week}")
        _tickets_on(db_session, 2 + week * 7, 1, source_prefix=f"HIST2-{week}")
        _tickets_on(db_session, 3 + week * 7, 1, source_prefix=f"HIST3-{week}")
    db_session.commit()

    result = ixc_ticket_momentum.daily_momentum(db_session, regional=REGIONAL, reference_date=REFERENCE.date())

    assert result["consecutive_days_above_expected"] == 2
