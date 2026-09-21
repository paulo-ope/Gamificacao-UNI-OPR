"""Fase 2 do plano de evolução analítica do Atendimento IXC (2026-09-14): contrato de contexto
único (`ixc_ticket_context.py`) - generaliza breakdown/prioridades por `dimension` + filtros
independentes, no modelo de período livre (date_from/date_to + janela anterior de mesmo
tamanho)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.modules.operations.models import OperationCustomerContract
from app.modules.support import ixc_ticket_context
from app.modules.support.models import SupportIxcTicket

REGIONAL = "UNI - NOVA BRASILANDIA DOESTE"
CITY = "Nova Brasilândia D'Oeste"
NEIGHBORHOOD = "Centro"


def _ticket(db, *, source_id, **overrides):
    base = dict(
        source_id=source_id,
        customer_id="500",
        regional=REGIONAL,
        city=CITY,
        neighborhood=NEIGHBORHOOD,
        subject_id="90",
        subject_name="Sem conexão",
        created_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )
    base.update(overrides)
    row = SupportIxcTicket(**base)
    db.add(row)
    return row


def _contract(db, *, id_seq, **overrides):
    base = dict(source_contract_id=id_seq, regional=REGIONAL, city=CITY, status="A")
    base.update(overrides)
    row = OperationCustomerContract(**base)
    db.add(row)
    return row


def test_resolve_context_computes_deviation_vs_previous_period_of_same_length(db_session):
    for i in range(12):
        _ticket(db_session, source_id=f"CUR{i}", created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
    for i in range(10):
        _ticket(db_session, source_id=f"PREV{i}", created_at=datetime(2026, 9, 8, tzinfo=timezone.utc))
    db_session.commit()

    context = ixc_ticket_context.resolve_context(
        db_session, date_from=date(2026, 9, 9), date_to=date(2026, 9, 10), regional=REGIONAL
    )

    assert context["ticket_count"] == 12
    assert context["previous_ticket_count"] == 10
    assert context["deviation_pct"] == 20.0
    assert context["severity"] == "critico"
    assert context["severity_basis"] == "historical"
    assert context["effective_deviation_pct"] == 20.0


def test_resolve_context_uses_peers_fallback_when_own_history_insufficient(db_session):
    """Item 1 da correção pedida (2026-09-17): regional pequena (histórico próprio abaixo de
    MIN_DEVIATION_SAMPLE=10) não pode virar "sem dado" quando existem pares confiáveis pra
    comparar - mesma proteção que a Visão Geral clássica já tinha, portada pro contrato único."""
    SMALL_REGIONAL = "UNI - PEQUENA"
    PEER_REGIONAL = "UNI - PAR"
    for i in range(20):
        _ticket(db_session, source_id=f"SMALL-CUR{i}", regional=SMALL_REGIONAL, created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
    for i in range(3):  # abaixo de MIN_DEVIATION_SAMPLE - deviation_pct próprio vira None
        _ticket(db_session, source_id=f"SMALL-PREV{i}", regional=SMALL_REGIONAL, created_at=datetime(2026, 9, 8, tzinfo=timezone.utc))
    for i in range(5):  # regional-par, só serve de referência de pares neste teste
        _ticket(db_session, source_id=f"PEER-CUR{i}", regional=PEER_REGIONAL, created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
    db_session.commit()

    context = ixc_ticket_context.resolve_context(
        db_session, date_from=date(2026, 9, 9), date_to=date(2026, 9, 10), regional=SMALL_REGIONAL
    )

    assert context["deviation_pct"] is None
    assert context["peers_deviation_pct"] == 300.0  # (20 - 5) / 5 * 100
    assert context["effective_deviation_pct"] == 300.0
    assert context["severity_basis"] == "peers"
    assert context["severity"] == "critico"


def test_resolve_context_severity_basis_is_insufficient_data_without_history_or_peers(db_session):
    """Nem histórico próprio nem pares confiáveis (nenhuma outra regional existe no recorte) -
    NUNCA pode virar "dentro_da_curva" por acidente (regra explícita do usuário: ausência de
    amostra não é normalidade)."""
    SMALL_REGIONAL = "UNI - PEQUENA"
    for i in range(20):
        _ticket(db_session, source_id=f"CUR{i}", regional=SMALL_REGIONAL, created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
    for i in range(3):
        _ticket(db_session, source_id=f"PREV{i}", regional=SMALL_REGIONAL, created_at=datetime(2026, 9, 8, tzinfo=timezone.utc))
    db_session.commit()

    context = ixc_ticket_context.resolve_context(
        db_session, date_from=date(2026, 9, 9), date_to=date(2026, 9, 10), regional=SMALL_REGIONAL
    )

    assert context["deviation_pct"] is None
    assert context["peers_deviation_pct"] is None
    assert context["severity_basis"] == "insufficient_data"
    assert context["severity"] == "sem_dado"


def test_resolve_context_next_dimension_progresses_through_hierarchy(db_session):
    _ticket(db_session, source_id="T1")
    db_session.commit()

    assert ixc_ticket_context.resolve_context(db_session, date_from=None, date_to=None)["next_dimension"] == "regional"
    assert ixc_ticket_context.resolve_context(
        db_session, date_from=None, date_to=None, regional=REGIONAL
    )["next_dimension"] == "city"
    assert ixc_ticket_context.resolve_context(
        db_session, date_from=None, date_to=None, regional=REGIONAL, city=CITY
    )["next_dimension"] == "neighborhood"
    assert ixc_ticket_context.resolve_context(
        db_session, date_from=None, date_to=None, regional=REGIONAL, city=CITY, neighborhood=NEIGHBORHOOD
    )["next_dimension"] == "subject"
    assert ixc_ticket_context.resolve_context(
        db_session, date_from=None, date_to=None, regional=REGIONAL, city=CITY, neighborhood=NEIGHBORHOOD, subject_id="90"
    )["next_dimension"] is None


def test_resolve_context_contract_count_is_none_without_regional_or_city(db_session):
    _ticket(db_session, source_id="T1")
    db_session.commit()

    context = ixc_ticket_context.resolve_context(db_session, date_from=None, date_to=None)

    assert context["contract_count"] is None
    assert context["tickets_per_1000_contracts"] is None


def test_resolve_context_includes_reach_summary(db_session):
    _ticket(db_session, source_id="T1", customer_id="500")
    _ticket(db_session, source_id="T2", customer_id="501")
    db_session.commit()

    context = ixc_ticket_context.resolve_context(
        db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30), regional=REGIONAL
    )

    assert context["reach"]["unique_customers"] == 2


def test_resolve_context_top_driver_is_none_without_tickets(db_session):
    context = ixc_ticket_context.resolve_context(db_session, date_from=None, date_to=None)

    assert context["top_driver"] is None


def test_driver_decomposition_for_period_uses_previous_period_as_expected(db_session):
    for i in range(5):
        _ticket(
            db_session, source_id=f"CUR{i}", subject_name="Lentidão",
            created_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
        )
    _ticket(db_session, source_id="PREV1", subject_name="Lentidão", created_at=datetime(2026, 9, 8, tzinfo=timezone.utc))
    db_session.commit()

    items = ixc_ticket_context.driver_decomposition_for_period(
        db_session, date_from=date(2026, 9, 9), date_to=date(2026, 9, 10)
    )

    assert items[0]["subject_name"] == "Lentidão"
    assert items[0]["current"] == 5
    assert items[0]["expected"] == 1
    assert items[0]["excess"] == 4
    assert items[0]["contribution_pct"] == 100.0


def test_context_key_is_deterministic_for_the_same_filters():
    key1 = ixc_ticket_context.build_context_key(regional=REGIONAL, date_from=date(2026, 9, 9), date_to=date(2026, 9, 15))
    key2 = ixc_ticket_context.build_context_key(regional=REGIONAL, date_from=date(2026, 9, 9), date_to=date(2026, 9, 15))

    assert key1 == key2


def test_context_key_differs_for_different_filters():
    key1 = ixc_ticket_context.build_context_key(regional=REGIONAL, date_from=date(2026, 9, 9), date_to=date(2026, 9, 15))
    key2 = ixc_ticket_context.build_context_key(regional=REGIONAL, city=CITY, date_from=date(2026, 9, 9), date_to=date(2026, 9, 15))

    assert key1 != key2


def test_context_key_round_trips_through_parse():
    key = ixc_ticket_context.build_context_key(
        regional=REGIONAL, city=CITY, neighborhood=NEIGHBORHOOD, subject_id="90",
        date_from=date(2026, 9, 9), date_to=date(2026, 9, 15),
    )

    parsed = ixc_ticket_context.parse_context_key(key)

    assert parsed == {
        "regional": REGIONAL, "city": CITY, "neighborhood": NEIGHBORHOOD, "subject_id": "90",
        "sector_id": None, "date_from": date(2026, 9, 9), "date_to": date(2026, 9, 15),
    }


def test_parse_context_key_rejects_malformed_key():
    with pytest.raises(ValueError):
        ixc_ticket_context.parse_context_key("isso-nao-e-uma-chave-valida-!!!")


def test_drill_from_context_key_returns_the_same_tickets_used_in_the_calculation(db_session):
    """Item 3 e teste 10 exigidos: sinal -> context_key -> drill -> EXATAMENTE os tickets usados
    naquele contexto - não um subconjunto nem um conjunto diferente."""
    for i in range(5):
        _ticket(db_session, source_id=f"IN-{i}", created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
    _ticket(db_session, source_id="OUT-OF-PERIOD", created_at=datetime(2026, 8, 1, tzinfo=timezone.utc))
    _ticket(db_session, source_id="OUT-OF-REGIONAL", regional="UNI - OUTRA", created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
    db_session.commit()

    context = ixc_ticket_context.resolve_context(
        db_session, date_from=date(2026, 9, 9), date_to=date(2026, 9, 10), regional=REGIONAL
    )
    filters = ixc_ticket_context.parse_context_key(context["context_key"])

    from app.modules.support.ixc_ticket_queries import list_tickets

    total, tickets = list_tickets(db_session, **filters, limit=100)

    assert total == 5
    assert {ticket.source_id for ticket in tickets} == {f"IN-{i}" for i in range(5)}


def test_priorities_for_context_items_carry_a_drillable_context_key(db_session):
    _ticket(db_session, source_id="T1", created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
    db_session.commit()

    items = ixc_ticket_context.priorities_for_context(
        db_session, dimension="regional", date_from=date(2026, 9, 9), date_to=date(2026, 9, 10)
    )

    parsed = ixc_ticket_context.parse_context_key(items[0]["context_key"])
    assert parsed["regional"] == REGIONAL
    assert parsed["date_from"] == date(2026, 9, 9)


def test_geographic_concentration_finds_top_city_and_neighborhood(db_session):
    """Item 5 da correção: principal cidade + principal bairro, `share_pct` sobre o total do
    escopo (regional inteira), não em cascata."""
    OTHER_CITY = "Outra Cidade"
    for i in range(3):
        _ticket(db_session, source_id=f"CENTRO-{i}", created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))  # CITY/NEIGHBORHOOD default
    for i in range(1):
        _ticket(db_session, source_id=f"OUTRO-BAIRRO-{i}", neighborhood="Outro Bairro", created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
    _ticket(db_session, source_id="OUTRA-CIDADE", city=OTHER_CITY, neighborhood="Bairro X", created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
    db_session.commit()

    concentration = ixc_ticket_context.geographic_concentration(
        db_session, date_from=date(2026, 9, 10), date_to=date(2026, 9, 10), regional=REGIONAL
    )

    assert concentration["city"] == {"value": CITY, "count": 4, "share_pct": 80.0}
    assert concentration["neighborhood"] == {"value": NEIGHBORHOOD, "count": 3, "share_pct": 60.0}


def test_driver_decomposition_reports_no_concentration_when_excess_is_spread_out(db_session):
    """Item 8 dos testes exigidos: ausência de concentração - excesso dividido igualmente entre
    vários motivos não deve apontar nenhum como dominante (`contribution_pct` baixo pra todos)."""
    for name in ["Sem conexão", "Lentidão", "Registro de Atendimento"]:
        for i in range(4):  # 4 atuais vs. 2 esperados em cada um - excesso igual nos 3
            _ticket(db_session, source_id=f"{name}-CUR{i}", subject_name=name, created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
        for i in range(2):
            _ticket(db_session, source_id=f"{name}-PREV{i}", subject_name=name, created_at=datetime(2026, 9, 8, tzinfo=timezone.utc))
    db_session.commit()

    items = ixc_ticket_context.driver_decomposition_for_period(
        db_session, date_from=date(2026, 9, 9), date_to=date(2026, 9, 10)
    )

    assert len(items) == 3
    assert all(item["contribution_pct"] == pytest.approx(33.3, abs=0.1) for item in items)
    assert max(item["contribution_pct"] for item in items) < 40.0  # abaixo do limiar de DRIVER_CONCENTRATION


def test_geographic_concentration_is_none_without_regional():
    assert ixc_ticket_context.geographic_concentration(None, date_from=None, date_to=None, regional=None) is None


def test_priorities_for_context_requires_parent_filters():
    with pytest.raises(ValueError):
        ixc_ticket_context.priorities_for_context(
            None, dimension="city", date_from=None, date_to=None  # regional ausente
        )


def test_priorities_for_context_regional_dimension_adds_severity_and_label(db_session):
    for i in range(30):
        _ticket(db_session, source_id=f"T{i}", created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
    for i in range(10):
        _ticket(db_session, source_id=f"P{i}", created_at=datetime(2026, 9, 8, tzinfo=timezone.utc))
    db_session.commit()

    items = ixc_ticket_context.priorities_for_context(
        db_session, dimension="regional", date_from=date(2026, 9, 9), date_to=date(2026, 9, 10)
    )

    assert items[0]["key"] == REGIONAL
    assert items[0]["dimension"] == "regional"
    assert items[0]["severity"] == "critico"
    assert items[0]["severity_basis"] == "historical"


def test_priorities_for_context_falls_back_to_peers_for_small_regional(db_session):
    SMALL_REGIONAL = "UNI - PEQUENA"
    PEER_REGIONAL = "UNI - PAR"
    for i in range(20):
        _ticket(db_session, source_id=f"SMALL-CUR{i}", regional=SMALL_REGIONAL, created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
    for i in range(3):
        _ticket(db_session, source_id=f"SMALL-PREV{i}", regional=SMALL_REGIONAL, created_at=datetime(2026, 9, 8, tzinfo=timezone.utc))
    for i in range(5):
        _ticket(db_session, source_id=f"PEER-CUR{i}", regional=PEER_REGIONAL, created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
    db_session.commit()

    items = ixc_ticket_context.priorities_for_context(
        db_session, dimension="regional", date_from=date(2026, 9, 9), date_to=date(2026, 9, 10)
    )

    small = next(item for item in items if item["key"] == SMALL_REGIONAL)
    assert small["deviation_pct"] is None
    assert small["peers_deviation_pct"] == 300.0
    assert small["severity_basis"] == "peers"
    assert small["severity"] == "critico"


def test_priorities_for_context_insufficient_data_without_peers(db_session):
    ONLY_REGIONAL = "UNI - SOZINHA"
    for i in range(20):
        _ticket(db_session, source_id=f"CUR{i}", regional=ONLY_REGIONAL, created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
    for i in range(3):
        _ticket(db_session, source_id=f"PREV{i}", regional=ONLY_REGIONAL, created_at=datetime(2026, 9, 8, tzinfo=timezone.utc))
    db_session.commit()

    items = ixc_ticket_context.priorities_for_context(
        db_session, dimension="regional", date_from=date(2026, 9, 9), date_to=date(2026, 9, 10)
    )

    assert len(items) == 1
    assert items[0]["deviation_pct"] is None
    assert items[0]["peers_deviation_pct"] is None
    assert items[0]["severity_basis"] == "insufficient_data"
    assert items[0]["severity"] == "sem_dado"
