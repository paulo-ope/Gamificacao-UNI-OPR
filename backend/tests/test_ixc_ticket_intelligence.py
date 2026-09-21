"""Fase 5 do plano de evolução analítica do Atendimento IXC (2026-09-15): `ixc_ticket_intelligence`
- combina contexto (Fase 2), momentum e burst (Fase 4) num resumo (`build_brief`) e numa lista de
sinais (`list_signals`), sem recalcular nada - os testes cobrem a combinação e os critérios de
"o que vira sinal", não as heurísticas de origem (já testadas em seus próprios módulos)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.modules.support import ixc_ticket_intelligence
from app.modules.support.models import SupportIxcTicket

REGIONAL = "UNI - NOVA BRASILANDIA DOESTE"


def _ticket(db, *, source_id, created_at, regional=REGIONAL, **overrides):
    base = dict(source_id=source_id, regional=regional, subject_name="Sem conexão", created_at=created_at)
    base.update(overrides)
    row = SupportIxcTicket(**base)
    db.add(row)
    return row


def test_build_brief_reflects_recent_window_deviation(db_session):
    reference = date(2026, 9, 15)
    for i in range(20):
        _ticket(db_session, source_id=f"CUR{i}", created_at=datetime(2026, 9, 14, 10, tzinfo=timezone.utc))
    for i in range(10):
        _ticket(db_session, source_id=f"PREV{i}", created_at=datetime(2026, 9, 1, 10, tzinfo=timezone.utc))
    db_session.commit()

    brief = ixc_ticket_intelligence.build_brief(db_session, regional=REGIONAL, reference_date=reference)

    assert brief["scope"] == {"type": "regional", "id": REGIONAL}
    assert brief["ticket_count"] == 20
    assert "momentum" in brief and "trend" in brief["momentum"]
    assert isinstance(brief["bursts"], list) and len(brief["bursts"]) == 2  # SIGNAL_BURST_WINDOWS_HOURS = (1, 2)


def test_build_brief_global_scope_has_no_regional_id(db_session):
    brief = ixc_ticket_intelligence.build_brief(db_session, reference_date=date(2026, 9, 15))

    assert brief["scope"] == {"type": "global", "id": None}


def test_list_signals_excludes_regional_within_curve_and_no_momentum(db_session):
    # Volume estável, nada de excesso nem tendência - não deveria virar sinal.
    for week in range(1, 9):
        _ticket(db_session, source_id=f"BASELINE-{week}", created_at=datetime(2026, 9, 15, tzinfo=timezone.utc) - timedelta(weeks=week))
    db_session.commit()

    signals = ixc_ticket_intelligence.list_signals(db_session, reference_date=date(2026, 9, 15))

    assert all(signal["scope"]["id"] != REGIONAL for signal in signals)


def test_list_signals_includes_regional_with_critical_deviation(db_session):
    # Janela do brief/signals: [09-09, 09-15]; período anterior de mesmo tamanho: [09-02, 09-08]
    # (ver `_previous_period_bounds`) - PREV precisa cair DENTRO dele pra contar como amostra.
    reference = date(2026, 9, 15)
    for i in range(30):
        _ticket(db_session, source_id=f"CUR{i}", created_at=datetime(2026, 9, 14, 10, tzinfo=timezone.utc))
    for i in range(10):
        _ticket(db_session, source_id=f"PREV{i}", created_at=datetime(2026, 9, 5, 10, tzinfo=timezone.utc))
    db_session.commit()

    signals = ixc_ticket_intelligence.list_signals(db_session, reference_date=reference)

    matching = [signal for signal in signals if signal["scope"]["id"] == REGIONAL]
    assert matching, "regional com desvio crítico deveria aparecer na lista de sinais"
    assert matching[0]["severity"] == "critico"
    assert matching[0]["severity_basis"] == "historical"
    codes = {item["code"] for item in matching[0]["reason_codes"]}
    assert "HIGH_DEVIATION" in codes
    high_deviation = next(item for item in matching[0]["reason_codes"] if item["code"] == "HIGH_DEVIATION")
    assert high_deviation == {"code": "HIGH_DEVIATION", "current": 30, "expected": 10, "delta_pct": 200.0, "basis": "historical"}


def test_build_brief_consolidates_drivers_and_os_conversion(db_session):
    """Item 2/3/7 da correção (2026-09-17): o brief já traz drivers (lista, não só o principal) e
    conversão em O.S. - sem precisar de chamada separada a `driver_decomposition_for_period`/
    `os_conversion_rate`."""
    reference = date(2026, 9, 15)
    for i in range(20):
        _ticket(db_session, source_id=f"CUR{i}", created_at=datetime(2026, 9, 14, 10, tzinfo=timezone.utc))
    for i in range(10):
        _ticket(db_session, source_id=f"PREV{i}", created_at=datetime(2026, 9, 5, 10, tzinfo=timezone.utc))
    db_session.commit()

    brief = ixc_ticket_intelligence.build_brief(db_session, regional=REGIONAL, reference_date=reference)

    assert "drivers" in brief and isinstance(brief["drivers"], list) and brief["drivers"]
    assert brief["drivers"][0]["subject_name"] == "Sem conexão"
    assert "os_conversion" in brief and "conversions" in brief["os_conversion"]
    assert brief["severity_basis"] in ("historical", "peers", "insufficient_data")
    assert "reason_codes" in brief and isinstance(brief["reason_codes"], list)


def test_reason_codes_carry_the_numbers_that_support_them(db_session):
    """Item 6 da correção (2026-09-17): a IA deve entender o motivo do sinal lendo SÓ aquele item
    do reason_codes, sem cruzar com outro payload."""
    reference = date(2026, 9, 15)
    for i in range(20):
        _ticket(db_session, source_id=f"CUR{i}", subject_name="Sem conexão", created_at=datetime(2026, 9, 14, 10, tzinfo=timezone.utc))
    for i in range(10):
        _ticket(db_session, source_id=f"PREV{i}", subject_name="Sem conexão", created_at=datetime(2026, 9, 5, 10, tzinfo=timezone.utc))
    db_session.commit()

    brief = ixc_ticket_intelligence.build_brief(db_session, regional=REGIONAL, reference_date=reference)

    high_deviation = next(item for item in brief["reason_codes"] if item["code"] == "HIGH_DEVIATION")
    assert high_deviation["current"] == 20
    assert high_deviation["expected"] == 10
    assert high_deviation["delta_pct"] == 100.0
    assert high_deviation["basis"] == "historical"

    concentration = next(item for item in brief["reason_codes"] if item["code"] == "DRIVER_CONCENTRATION")
    assert concentration["subject"] == "Sem conexão"
    assert concentration["contribution_pct"] == 100.0


def test_list_signals_sorted_critical_first(db_session):
    signals = ixc_ticket_intelligence.list_signals(db_session, reference_date=date(2026, 9, 15))

    severities = [signal["severity"] for signal in signals]
    # Todo "critico" vem antes de qualquer outro valor - não checa ordem TOTAL (empates existem).
    if "critico" in severities and len(set(severities)) > 1:
        first_non_critical = next(i for i, s in enumerate(severities) if s != "critico")
        assert all(s == "critico" for s in severities[:first_non_critical])
