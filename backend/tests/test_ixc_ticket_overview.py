from __future__ import annotations

from datetime import date, datetime, timezone

from app.modules.operations.models import OperationCustomerContract
from app.modules.support import ixc_ticket_overview
from app.modules.support.models import SupportIxcTaxonomyMapping, SupportIxcTicket

REGIONAL = "UNI - NOVA BRASILANDIA DOESTE"
PEER_REGIONAL = "UNI - JI PARANA"


def _ticket(
    db,
    *,
    source_id,
    regional=REGIONAL,
    city=None,
    created_at,
    subject_id="90",
    subject_name="Sem conexão",
    sector_id=None,
):
    row = SupportIxcTicket(
        source_id=source_id,
        regional=regional,
        city=city,
        subject_id=subject_id,
        subject_name=subject_name,
        sector_id=sector_id,
        created_at=created_at,
    )
    db.add(row)
    return row


def _contract(db, *, id_seq, regional=REGIONAL, city=None, status="A"):
    row = OperationCustomerContract(source_contract_id=id_seq, regional=regional, city=city, status=status)
    db.add(row)
    return row


def _dt(y, m, d):
    return datetime(y, m, d, 10, 0, tzinfo=timezone.utc)


def test_overview_kpis_computes_partial_incidence_and_deviation(db_session):
    for i in range(100):
        _contract(db_session, id_seq=f"C{i}")
    # Mês corrente (setembro/2026): 25 tickets até dia 10 (cutoff simulado via `today`).
    for i in range(25):
        _ticket(db_session, source_id=f"T{i}", created_at=_dt(2026, 9, min(i + 1, 10)))
    # Mesmo corte (dia 1-10) no mês anterior: 20 tickets -> média histórica (amostra >= piso
    # mínimo de MIN_HISTORICAL_SAMPLE, senão o desvio nem é calculado - ver teste dedicado abaixo).
    for i in range(20):
        _ticket(db_session, source_id=f"H{i}", created_at=_dt(2026, 8, min(i + 1, 10)))
    db_session.commit()

    kpis = ixc_ticket_overview.overview_kpis(
        db_session, month=date(2026, 9, 1), regional=REGIONAL, history_months=1, today=date(2026, 9, 10)
    )

    assert kpis["cutoff_day"] == 10
    assert kpis["ticket_count"] == 25
    assert kpis["incidencia_parcial"] == 250.0  # 25 / 100 * 1000
    assert kpis["media_historica"] == 200.0  # 20 / 100 * 1000
    assert kpis["desvio_pct"] == 25.0  # (250-200)/200*100
    assert kpis["severity"] == "critico"  # >= 20%
    assert kpis["contract_count"] == 100


def test_overview_kpis_skips_deviation_when_historical_sample_is_too_small(db_session):
    """Achado explícito do usuário (2026-09-11): regional com histórico minúsculo não pode virar
    CRÍTICO por ruído estatístico - 5 tickets hoje vs 1 no histórico seria +400%, sem significar
    nada de verdade."""
    for i in range(100):
        _contract(db_session, id_seq=f"C{i}")
    for i in range(5):
        _ticket(db_session, source_id=f"T{i}", created_at=_dt(2026, 9, 1))
    _ticket(db_session, source_id="H0", created_at=_dt(2026, 8, 1))
    db_session.commit()

    kpis = ixc_ticket_overview.overview_kpis(
        db_session, month=date(2026, 9, 1), regional=REGIONAL, history_months=1, today=date(2026, 9, 10)
    )

    assert kpis["desvio_pct"] is None
    assert kpis["severity"] == "sem_dado"


def test_overview_kpis_returns_none_metrics_without_contracts(db_session):
    _ticket(db_session, source_id="T1", created_at=_dt(2026, 9, 1))
    db_session.commit()

    kpis = ixc_ticket_overview.overview_kpis(db_session, month=date(2026, 9, 1), regional=REGIONAL, today=date(2026, 9, 10))

    assert kpis["contract_count"] == 0
    assert kpis["incidencia_parcial"] is None
    assert kpis["coverage_pct"] is None


def test_overview_kpis_classifies_improving_when_deviation_is_very_negative(db_session):
    for i in range(100):
        _contract(db_session, id_seq=f"C{i}")
    _ticket(db_session, source_id="T1", created_at=_dt(2026, 9, 1))
    for i in range(20):
        _ticket(db_session, source_id=f"H{i}", created_at=_dt(2026, 8, 1))
    db_session.commit()

    kpis = ixc_ticket_overview.overview_kpis(
        db_session, month=date(2026, 9, 1), regional=REGIONAL, history_months=1, today=date(2026, 9, 1)
    )

    assert kpis["desvio_pct"] < ixc_ticket_overview.IMPROVING_DEVIATION_PCT
    assert kpis["severity"] == "em_melhora"


def test_overview_kpis_filters_by_subject_and_supports_multiple_values(db_session):
    """Pedido do usuário (2026-09-12): filtro de motivo/setor não é só do drill-down, tem que
    valer pros KPIs também - e é multi-seleção (vários ids separados por vírgula)."""
    for i in range(100):
        _contract(db_session, id_seq=f"C{i}")
    _ticket(db_session, source_id="T1", created_at=_dt(2026, 9, 1), subject_id="90")
    _ticket(db_session, source_id="T2", created_at=_dt(2026, 9, 1), subject_id="91")
    _ticket(db_session, source_id="T3", created_at=_dt(2026, 9, 1), subject_id="92")
    db_session.commit()

    single = ixc_ticket_overview.overview_kpis(
        db_session, month=date(2026, 9, 1), regional=REGIONAL, today=date(2026, 9, 10), subject_id="90"
    )
    assert single["ticket_count"] == 1

    multi = ixc_ticket_overview.overview_kpis(
        db_session, month=date(2026, 9, 1), regional=REGIONAL, today=date(2026, 9, 10), subject_id="90,91"
    )
    assert multi["ticket_count"] == 2


def test_overview_kpis_filters_by_sector(db_session):
    for i in range(100):
        _contract(db_session, id_seq=f"C{i}")
    _ticket(db_session, source_id="T1", created_at=_dt(2026, 9, 1), sector_id="2")
    _ticket(db_session, source_id="T2", created_at=_dt(2026, 9, 1), sector_id="3")
    db_session.commit()

    kpis = ixc_ticket_overview.overview_kpis(
        db_session, month=date(2026, 9, 1), regional=REGIONAL, today=date(2026, 9, 10), sector_id="2"
    )
    assert kpis["ticket_count"] == 1


def test_daily_incidence_series_filters_by_subject(db_session):
    _ticket(db_session, source_id="T1", created_at=_dt(2026, 9, 1), subject_id="90")
    _ticket(db_session, source_id="T2", created_at=_dt(2026, 9, 1), subject_id="91")
    db_session.commit()

    series = ixc_ticket_overview.daily_incidence_series(
        db_session, month=date(2026, 9, 1), regional=REGIONAL, today=date(2026, 9, 10), subject_id="91"
    )
    assert series[0]["current"] == 1


def test_priorities_filters_by_subject(db_session):
    for i in range(100):
        _contract(db_session, id_seq=f"C{i}")
    _ticket(db_session, source_id="T1", created_at=_dt(2026, 9, 1), subject_id="90")
    _ticket(db_session, source_id="T2", created_at=_dt(2026, 9, 1), subject_id="91")
    db_session.commit()

    items = ixc_ticket_overview.priorities(
        db_session, month=date(2026, 9, 1), history_months=1, today=date(2026, 9, 5), subject_id="90"
    )

    by_regional = {item["regional"]: item for item in items}
    assert by_regional[REGIONAL]["incidencia_parcial"] == 10.0  # 1 ticket / 100 contratos * 1000


def test_overview_kpis_with_day_counts_only_that_day_not_cumulative(db_session):
    """Pedido do usuário (2026-09-12): "ver só um dia específico" - os KPIs deixam de ser
    acumulados do início do mês até o corte, passam a contar só aquele dia."""
    for i in range(100):
        _contract(db_session, id_seq=f"C{i}")
    _ticket(db_session, source_id="T1", created_at=_dt(2026, 9, 1))
    _ticket(db_session, source_id="T2", created_at=_dt(2026, 9, 5))
    _ticket(db_session, source_id="T3", created_at=_dt(2026, 9, 5))
    db_session.commit()

    kpis = ixc_ticket_overview.overview_kpis(
        db_session, month=date(2026, 9, 1), regional=REGIONAL, today=date(2026, 9, 10), day=date(2026, 9, 5)
    )

    assert kpis["ticket_count"] == 2  # só dia 5, não acumulado desde dia 1
    assert kpis["cutoff_day"] == 5


def test_overview_kpis_with_day_compares_against_same_day_of_month_in_history(db_session):
    for i in range(100):
        _contract(db_session, id_seq=f"C{i}")
    # Dia 5 de setembro: 10 tickets.
    for i in range(10):
        _ticket(db_session, source_id=f"T{i}", created_at=_dt(2026, 9, 5))
    # Dia 5 de agosto (histórico): 2 tickets - dia 1 de agosto tem 50, mas NÃO deve entrar na
    # média (senão a comparação seria "1 dia" vs "mês inteiro").
    for i in range(2):
        _ticket(db_session, source_id=f"H{i}", created_at=_dt(2026, 8, 5))
    for i in range(50):
        _ticket(db_session, source_id=f"N{i}", created_at=_dt(2026, 8, 1))
    db_session.commit()

    kpis = ixc_ticket_overview.overview_kpis(
        db_session,
        month=date(2026, 9, 1),
        regional=REGIONAL,
        history_months=1,
        today=date(2026, 9, 10),
        day=date(2026, 9, 5),
    )

    assert kpis["ticket_count"] == 10
    assert kpis["media_historica"] == 20.0  # 2 tickets / 100 contratos * 1000


def test_priorities_with_day_filters_by_single_day(db_session):
    for i in range(100):
        _contract(db_session, id_seq=f"C{i}")
    _ticket(db_session, source_id="T1", created_at=_dt(2026, 9, 1))
    _ticket(db_session, source_id="T2", created_at=_dt(2026, 9, 5))
    db_session.commit()

    items = ixc_ticket_overview.priorities(
        db_session, month=date(2026, 9, 1), history_months=1, today=date(2026, 9, 10), day=date(2026, 9, 5)
    )

    by_regional = {item["regional"]: item for item in items}
    assert by_regional[REGIONAL]["incidencia_parcial"] == 10.0  # 1 ticket / 100 * 1000


def test_coverage_pct_reflects_missing_city_within_a_regional(db_session):
    for i in range(10):
        row = OperationCustomerContract(source_contract_id=f"C{i}", regional=REGIONAL, status="A")
        if i < 3:
            row.city = "Nova Brasilândia D'Oeste"
        db_session.add(row)
    db_session.commit()

    kpis = ixc_ticket_overview.overview_kpis(db_session, month=date(2026, 9, 1), regional=REGIONAL, today=date(2026, 9, 10))

    assert kpis["coverage_pct"] == 30.0


def test_taxonomy_coverage_pct_is_none_without_any_ticket_in_the_recorte(db_session):
    for i in range(5):
        _contract(db_session, id_seq=f"C{i}")
    db_session.commit()

    kpis = ixc_ticket_overview.overview_kpis(db_session, month=date(2026, 9, 1), regional=REGIONAL, today=date(2026, 9, 10))

    assert kpis["taxonomy_coverage_pct"] is None


def test_taxonomy_coverage_pct_weighs_by_ticket_not_by_distinct_subject(db_session):
    for i in range(10):
        _contract(db_session, id_seq=f"C{i}")
    db_session.add(
        SupportIxcTaxonomyMapping(
            subject_id="90",
            theme_id="conectividade",
            theme_label="Conectividade",
            category_id="operacoes",
            category_label="Operações",
            effective_from=date(2026, 1, 1),
        )
    )
    # "90" (mapeado) tem 3 atendimentos, "91" (não mapeado) tem 1 - cobertura pondera por
    # atendimento (3/4 = 75%), não por motivo distinto (que daria 50%).
    for i in range(3):
        _ticket(db_session, source_id=f"T{i}", created_at=_dt(2026, 9, 5), subject_id="90")
    _ticket(db_session, source_id="T3", created_at=_dt(2026, 9, 5), subject_id="91", subject_name="Outro motivo")
    db_session.commit()

    kpis = ixc_ticket_overview.overview_kpis(db_session, month=date(2026, 9, 1), regional=REGIONAL, today=date(2026, 9, 10))

    assert kpis["taxonomy_coverage_pct"] == 75.0


def test_daily_incidence_series_covers_whole_month_with_history_and_moving_average(db_session):
    for day in (1, 2, 3, 8, 9, 10):
        _ticket(db_session, source_id=f"T{day}", created_at=_dt(2026, 9, day))
    for day in (1, 2):
        _ticket(db_session, source_id=f"P{day}", created_at=_dt(2026, 8, day))
    db_session.commit()

    series = ixc_ticket_overview.daily_incidence_series(
        db_session, month=date(2026, 9, 1), regional=REGIONAL, history_months=1, today=date(2026, 9, 10)
    )

    assert len(series) == 30  # setembro tem 30 dias
    day1 = series[0]
    assert day1["current"] == 1
    assert day1["previous_month"] == 1
    day10 = series[9]
    assert day10["current"] == 1
    day15 = series[14]
    assert day15["current"] is None  # depois do "hoje" simulado (dia 10)


def test_priorities_flags_the_subject_that_spiked_not_the_most_frequent_one(db_session):
    """Pedido explícito do usuário (2026-09-11): "pense em como metrificar se algo está saindo do
    padrão, ex. lentidão" - o motivo mais FREQUENTE de uma regional tende a ser sempre o mesmo
    (aqui "Registro de Atendimento Operacional") e mascara o que realmente mudou. "Lentidão" tem
    volume baixo em termos absolutos (8 vs histórico de ~1/mês), mas é o maior salto - deve ser
    escolhido como categoria, não o motivo de maior volume bruto."""
    for i in range(100):
        _contract(db_session, id_seq=f"C{i}")

    # Motivo de sempre: alto volume, estável mês a mês (sem novidade).
    for i in range(50):
        _ticket(db_session, source_id=f"R{i}", created_at=_dt(2026, 9, 1), subject_name="Registro de Atendimento Operacional")
    for i in range(48):
        _ticket(db_session, source_id=f"HR{i}", created_at=_dt(2026, 8, 1), subject_name="Registro de Atendimento Operacional")

    # Lentidão: quase inexistente no histórico, dispara este mês - é o sinal relevante.
    for i in range(8):
        _ticket(db_session, source_id=f"L{i}", created_at=_dt(2026, 9, 1), subject_name="Lentidão")
    _ticket(db_session, source_id="HL0", created_at=_dt(2026, 8, 1), subject_name="Lentidão")
    db_session.commit()

    items = ixc_ticket_overview.priorities(db_session, month=date(2026, 9, 1), history_months=1, today=date(2026, 9, 5))

    by_regional = {item["regional"]: item for item in items}
    assert by_regional[REGIONAL]["category"] == "Lentidão"


def test_driver_decomposition_computes_contribution_pct_of_excess(db_session):
    """Mesmo cenário de `test_priorities_flags_the_subject_that_spiked_not_the_most_frequent_one`,
    mas verificando a decomposição completa (Fase 1 do plano de evolução analítica, 2026-09-14):
    "Lentidão" tem excesso 7,0 (8 atual - 1,0 esperado) e "Registro..." tem excesso 2,0 (50 - 48) -
    excesso total positivo = 9,0, então Lentidão explica 7/9 = 77,8% do aumento, não 62% (esse
    número é só o exemplo do pedido original, não um valor fixado)."""
    for i in range(50):
        _ticket(db_session, source_id=f"R{i}", created_at=_dt(2026, 9, 1), subject_name="Registro de Atendimento Operacional")
    for i in range(48):
        _ticket(db_session, source_id=f"HR{i}", created_at=_dt(2026, 8, 1), subject_name="Registro de Atendimento Operacional")
    for i in range(8):
        _ticket(db_session, source_id=f"L{i}", created_at=_dt(2026, 9, 1), subject_name="Lentidão")
    _ticket(db_session, source_id="HL0", created_at=_dt(2026, 8, 1), subject_name="Lentidão")
    db_session.commit()

    items = ixc_ticket_overview.driver_decomposition(
        db_session, month_start=date(2026, 9, 1), cutoff=date(2026, 9, 5),
        history_month_starts=[date(2026, 8, 1)], regional=REGIONAL,
    )

    by_name = {item["subject_name"]: item for item in items}
    assert by_name["Lentidão"] == {"subject_name": "Lentidão", "current": 8, "expected": 1.0, "excess": 7.0, "contribution_pct": 77.8}
    assert by_name["Registro de Atendimento Operacional"]["contribution_pct"] == 22.2
    # Ordenado por excesso decrescente - o driver principal vem primeiro.
    assert items[0]["subject_name"] == "Lentidão"


def test_driver_decomposition_zeroes_contribution_when_nothing_exceeds_expected(db_session):
    """Sem nenhum motivo com excesso positivo (tudo estável ou em queda), `contribution_pct` é
    0.0 pra todo mundo - não divide por zero, e não inventa participação onde não houve aumento
    nenhum a explicar."""
    for i in range(10):
        _ticket(db_session, source_id=f"R{i}", created_at=_dt(2026, 9, 1), subject_name="Registro de Atendimento Operacional")
    for i in range(20):
        _ticket(db_session, source_id=f"HR{i}", created_at=_dt(2026, 8, 1), subject_name="Registro de Atendimento Operacional")
    db_session.commit()

    items = ixc_ticket_overview.driver_decomposition(
        db_session, month_start=date(2026, 9, 1), cutoff=date(2026, 9, 5),
        history_month_starts=[date(2026, 8, 1)], regional=REGIONAL,
    )

    assert items[0]["contribution_pct"] == 0.0
    assert items[0]["excess"] < 0


def test_driver_decomposition_is_empty_without_any_ticket_in_the_current_period(db_session):
    assert ixc_ticket_overview.driver_decomposition(
        db_session, month_start=date(2026, 9, 1), cutoff=date(2026, 9, 5),
        history_month_starts=[date(2026, 8, 1)], regional=REGIONAL,
    ) == []


def test_priorities_ranks_by_historical_deviation_and_computes_peers(db_session):
    for i in range(100):
        _contract(db_session, id_seq=f"CA{i}", regional=REGIONAL)
        _contract(db_session, id_seq=f"CB{i}", regional=PEER_REGIONAL)

    # Regional em alta: 30 tickets este mês vs 10 no histórico (corte dia 5).
    for i in range(30):
        _ticket(db_session, source_id=f"A{i}", regional=REGIONAL, created_at=_dt(2026, 9, 1))
    for i in range(10):
        _ticket(db_session, source_id=f"HA{i}", regional=REGIONAL, created_at=_dt(2026, 8, 1))

    # Regional pareada: estável, 10 este mês vs 10 no histórico.
    for i in range(10):
        _ticket(db_session, source_id=f"B{i}", regional=PEER_REGIONAL, created_at=_dt(2026, 9, 1))
    for i in range(10):
        _ticket(db_session, source_id=f"HB{i}", regional=PEER_REGIONAL, created_at=_dt(2026, 8, 1))
    db_session.commit()

    items = ixc_ticket_overview.priorities(db_session, month=date(2026, 9, 1), history_months=1, today=date(2026, 9, 5))

    by_regional = {item["regional"]: item for item in items}
    assert by_regional[REGIONAL]["severity"] == "critico"
    assert by_regional[REGIONAL]["historical_deviation_pct"] == 200.0  # (30-10)/10*100
    assert by_regional[REGIONAL]["category"] == "Sem conexão"
    # A primeira da lista deve ser a de maior desvio histórico.
    assert items[0]["regional"] == REGIONAL


def test_priorities_falls_back_to_peer_deviation_when_historical_sample_is_insufficient(db_session):
    """Achado comparando com o painel de referência do Comercial (2026-09-14, pedido do usuário
    "visualiza os drill e as heuristicas que tem"): quando não há amostra histórica suficiente
    (MIN_HISTORICAL_SAMPLE), a severidade não pode virar "sem_dado" se ainda houver como comparar
    contra os PARES - o painel de referência faz exatamente isso. `severity_basis` diz qual base
    foi usada."""
    for i in range(100):
        _contract(db_session, id_seq=f"CA{i}", regional=REGIONAL)
        _contract(db_session, id_seq=f"CB{i}", regional=PEER_REGIONAL)

    # Regional sem histórico nenhum (0 tickets em agosto) - `historical_deviation_pct` tem que
    # vir None (amostra insuficiente), mas ainda há sinal contra o par.
    for i in range(30):
        _ticket(db_session, source_id=f"A{i}", regional=REGIONAL, created_at=_dt(2026, 9, 1))

    # Par estável, com histórico suficiente (não é o foco do teste, só dá uma base de comparação).
    for i in range(5):
        _ticket(db_session, source_id=f"B{i}", regional=PEER_REGIONAL, created_at=_dt(2026, 9, 1))
    for i in range(10):
        _ticket(db_session, source_id=f"HB{i}", regional=PEER_REGIONAL, created_at=_dt(2026, 8, 1))
    db_session.commit()

    items = ixc_ticket_overview.priorities(db_session, month=date(2026, 9, 1), history_months=1, today=date(2026, 9, 5))

    by_regional = {item["regional"]: item for item in items}
    target = by_regional[REGIONAL]
    assert target["historical_deviation_pct"] is None
    assert target["peers_deviation_pct"] == 500.0  # (300-50)/50*100
    assert target["severity_basis"] == "peers"
    assert target["severity"] == "critico"  # +500% vs. pares, mesmo limiar de +20% da classificação


def test_priorities_severity_basis_is_none_without_any_comparable_base(db_session):
    """Único regional no sistema (sem pares) e sem histórico - não há NENHUMA base de comparação,
    então `severity_basis` deve ser "none" e a severidade "sem_dado" (não "critico" por acidente)."""
    for i in range(100):
        _contract(db_session, id_seq=f"C{i}", regional=REGIONAL)
    for i in range(30):
        _ticket(db_session, source_id=f"A{i}", regional=REGIONAL, created_at=_dt(2026, 9, 1))
    db_session.commit()

    items = ixc_ticket_overview.priorities(db_session, month=date(2026, 9, 1), history_months=1, today=date(2026, 9, 5))

    by_regional = {item["regional"]: item for item in items}
    target = by_regional[REGIONAL]
    assert target["historical_deviation_pct"] is None
    assert target["peers_deviation_pct"] is None
    assert target["severity_basis"] == "none"
    assert target["severity"] == "sem_dado"


CITY_A = "Rolim de Moura"
CITY_B = "Ji-Paraná"


def test_city_priorities_compares_against_all_cities_regardless_of_regional(db_session):
    """Decisão explícita do usuário (2026-09-11): pares de cidade são TODAS as cidades do
    sistema, mesmo vindo de regionais diferentes - CITY_A e CITY_B aqui pertencem a regionais
    diferentes de propósito."""
    for i in range(30):
        _contract(db_session, id_seq=f"CA{i}", regional=REGIONAL, city=CITY_A)
        _contract(db_session, id_seq=f"CB{i}", regional=PEER_REGIONAL, city=CITY_B)

    # Cidade A em alta: 30 tickets este mês vs 10 no histórico.
    for i in range(30):
        _ticket(db_session, source_id=f"A{i}", regional=REGIONAL, city=CITY_A, created_at=_dt(2026, 9, 1))
    for i in range(10):
        _ticket(db_session, source_id=f"HA{i}", regional=REGIONAL, city=CITY_A, created_at=_dt(2026, 8, 1))

    # Cidade B estável.
    for i in range(10):
        _ticket(db_session, source_id=f"B{i}", regional=PEER_REGIONAL, city=CITY_B, created_at=_dt(2026, 9, 1))
    for i in range(10):
        _ticket(db_session, source_id=f"HB{i}", regional=PEER_REGIONAL, city=CITY_B, created_at=_dt(2026, 8, 1))
    db_session.commit()

    items = ixc_ticket_overview.city_priorities(
        db_session, month=date(2026, 9, 1), history_months=1, today=date(2026, 9, 5), min_active_contracts=10
    )

    by_city = {item["city"]: item for item in items}
    assert by_city[CITY_A]["severity"] == "critico"
    assert by_city[CITY_A]["historical_deviation_pct"] == 200.0
    # Peer de CITY_A é CITY_B (de outra regional) - confirma que a comparação atravessa regional.
    assert by_city[CITY_A]["peers_deviation_pct"] is not None
    assert by_city[CITY_B]["severity"] == "dentro_da_curva"


def test_city_priorities_excludes_cities_with_too_few_active_contracts(db_session):
    """Sem o piso de base ativa, uma cidade minúscula com 1 atendimento e 2 clientes viraria
    "500/1.000, CRÍTICO" por ruído de amostra pequena - mesmo espírito de MIN_HISTORICAL_SAMPLE,
    aqui no eixo populacional em vez do temporal."""
    for i in range(30):
        _contract(db_session, id_seq=f"CA{i}", city=CITY_A)
    _contract(db_session, id_seq="tiny", city="Cidadezinha")
    _ticket(db_session, source_id="T1", city=CITY_A, created_at=_dt(2026, 9, 1))
    _ticket(db_session, source_id="T2", city="Cidadezinha", created_at=_dt(2026, 9, 1))
    db_session.commit()

    items = ixc_ticket_overview.city_priorities(
        db_session, month=date(2026, 9, 1), history_months=1, today=date(2026, 9, 5), min_active_contracts=20
    )

    cities = {item["city"] for item in items}
    assert CITY_A in cities
    assert "Cidadezinha" not in cities
