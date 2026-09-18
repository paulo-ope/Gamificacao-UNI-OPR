"""Fase 4 do plano de evolução analítica do Atendimento IXC (2026-09-15): baseline hora-do-dia/
dia-da-semana (`ixc_ticket_baseline.py`) e detecção de picos (`BURST_V1`)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.modules.support import ixc_ticket_baseline
from app.modules.support.models import SupportIxcHourlyBaseline, SupportIxcTicket

REGIONAL = "UNI - NOVA BRASILANDIA DOESTE"


def _ticket(db, *, source_id, created_at, regional=REGIONAL):
    row = SupportIxcTicket(source_id=source_id, regional=regional, created_at=created_at)
    db.add(row)
    return row


def test_recompute_hourly_baseline_averages_the_same_slot_across_weeks(db_session):
    """3 tickets numa terça-feira 10h, em 3 das 4 semanas da janela de `baseline_weeks` (a 4a
    semana não teve nenhum) - o slot (terça, 10h) deve virar avg_count=0.75 (3 tickets / 4
    semanas, contagem zero nas semanas sem ticket também entra na média)."""
    reference_date = date(2026, 9, 15)  # terça-feira
    for weeks_ago in (1, 2, 3):
        day = reference_date - timedelta(days=7 * weeks_ago)
        _ticket(db_session, source_id=f"T{weeks_ago}", created_at=datetime(day.year, day.month, day.day, 10, 0, tzinfo=timezone.utc))
    db_session.commit()

    written = ixc_ticket_baseline.recompute_hourly_baseline(
        db_session, scope_type="global", scope_id=None, reference_date=reference_date, baseline_weeks=4
    )

    assert written == 168  # 7 dias x 24 horas
    slot = db_session.query(SupportIxcHourlyBaseline).filter_by(
        scope_type="global", scope_id=None, weekday=1, hour=10
    ).one()
    assert slot.avg_count == 0.75  # 3 tickets / 4 semanas da janela (a 4a semana não teve ticket)
    assert slot.sample_weeks == 4


def test_recompute_hourly_baseline_excludes_the_reference_date_itself(db_session):
    """Um ticket criado NO PRÓPRIO `reference_date` (dia parcial/em andamento) não pode entrar na
    média - só os dias JÁ FECHADOS anteriores a ele contam."""
    reference_date = date(2026, 9, 15)
    _ticket(db_session, source_id="TODAY", created_at=datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc))
    db_session.commit()

    ixc_ticket_baseline.recompute_hourly_baseline(
        db_session, scope_type="global", scope_id=None, reference_date=reference_date, baseline_weeks=4
    )

    slot = db_session.query(SupportIxcHourlyBaseline).filter_by(scope_type="global", weekday=1, hour=8).one()
    assert slot.avg_count == 0.0


def test_recompute_hourly_baseline_is_scoped_by_regional(db_session):
    """Um ticket de OUTRA regional não pode contaminar o baseline `scope_type="regional"` de uma
    regional diferente."""
    reference_date = date(2026, 9, 15)
    day = reference_date - timedelta(days=7)
    _ticket(db_session, source_id="OTHER", created_at=datetime(day.year, day.month, day.day, 9, 0, tzinfo=timezone.utc), regional="UNI - OUTRA")
    db_session.commit()

    ixc_ticket_baseline.recompute_hourly_baseline(
        db_session, scope_type="regional", scope_id=REGIONAL, reference_date=reference_date, baseline_weeks=4
    )

    slot = db_session.query(SupportIxcHourlyBaseline).filter_by(
        scope_type="regional", scope_id=REGIONAL, weekday=1, hour=9
    ).one()
    assert slot.avg_count == 0.0


def test_recompute_all_hourly_baselines_is_idempotent_the_same_day(db_session):
    """Rodar duas vezes no mesmo dia não recalcula de novo (mesmo espírito de
    `backlog_snapshot.capture_backlog_snapshot`) - evita custo repetido sem trazer nada novo."""
    first = ixc_ticket_baseline.recompute_all_hourly_baselines(db_session, reference_date=date(2026, 9, 15))
    assert first > 0

    second = ixc_ticket_baseline.recompute_all_hourly_baselines(db_session, reference_date=date(2026, 9, 15))
    assert second == 0


def test_detect_bursts_returns_basis_none_without_a_computed_baseline(db_session):
    """Antes do job diário rodar (ou escopo sem amostra suficiente), o burst não pode inventar um
    limiar - `basis="none"` deixa isso explícito pro chamador, em vez de `active=False` silencioso
    que pareceria "está tudo normal"."""
    windows = ixc_ticket_baseline.detect_bursts(db_session, scope_type="global", scope_id=None, reference_time=datetime(2026, 9, 15, 12, tzinfo=timezone.utc))

    assert len(windows) == 3  # 1h/2h/6h
    for window in windows:
        assert window["basis"] == "none"
        assert window["active"] is False
        assert window["expected"] is None


def test_detect_bursts_flags_active_when_observed_exceeds_the_expected_upper_limit(db_session):
    """Baseline baixo (avg_count=1, stddev=0) pro slot da hora de referência + volume real bem
    acima disso na última hora -> `active=True`, com `basis="baseline"`."""
    reference_time = datetime(2026, 9, 15, 14, 30, tzinfo=timezone.utc)  # terça, 14h
    db_session.add(
        SupportIxcHourlyBaseline(
            scope_type="global", scope_id=None, weekday=1, hour=14, avg_count=1.0, stddev_count=0.0, sample_weeks=4
        )
    )
    for i in range(10):
        _ticket(db_session, source_id=f"BURST{i}", created_at=datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc))
    db_session.commit()

    windows = ixc_ticket_baseline.detect_bursts(db_session, scope_type="global", scope_id=None, reference_time=reference_time, windows_hours=(1,))

    window = windows[0]
    assert window["basis"] == "baseline"
    assert window["observed"] == 10
    assert window["expected"] == 1.0
    assert window["active"] is True
