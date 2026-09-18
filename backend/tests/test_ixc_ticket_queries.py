from __future__ import annotations

from datetime import date, datetime, timezone

from app.modules.operations.models import OperationCustomerContract
from app.modules.support import ixc_ticket_queries
from app.modules.support.models import SupportIxcTaxonomyMapping, SupportIxcTicket


def _ticket(db, *, source_id, **overrides):
    base = dict(
        source_id=source_id,
        protocol="P-1",
        customer_id="500",
        regional="UNI - NOVA BRASILANDIA DOESTE",
        city="Nova Brasilândia D'Oeste",
        neighborhood="Centro",
        subject_id="90",
        subject_name="Sem conexão",
        sector_id="2",
        sector_name="Pós Venda",
        status="F",
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    row = SupportIxcTicket(**base)
    db.add(row)
    return row


def _contract(db, *, id_seq, **overrides):
    base = dict(
        source_contract_id=id_seq,
        regional="UNI - NOVA BRASILANDIA DOESTE",
        city="Nova Brasilândia D'Oeste",
        status="A",
    )
    base.update(overrides)
    row = OperationCustomerContract(**base)
    db.add(row)
    return row


def test_regional_breakdown_computes_rate_per_1000(db_session):
    for i in range(5):
        _ticket(db_session, source_id=f"T{i}")
    for i in range(1000):
        _contract(db_session, id_seq=f"C{i}")
    db_session.commit()

    items = ixc_ticket_queries.regional_breakdown(db_session, date_from=None, date_to=None)

    assert len(items) == 1
    row = items[0]
    assert row["key"] == "UNI - NOVA BRASILANDIA DOESTE"
    assert row["ticket_count"] == 5
    assert row["contract_count"] == 1000
    assert row["tickets_per_1000_contracts"] == 5.0


def test_regional_breakdown_excludes_inactive_contracts_from_denominator(db_session):
    """Decisão do usuário (2026-09-11, distribuição real conferida no banco: status A=84.022,
    I=30.529, N=1.092, D=1.061, P=146): "ativo" para o denominador é `status == 'A'`, não
    qualquer contrato sincronizado."""
    for i in range(5):
        _ticket(db_session, source_id=f"T{i}")
    for i in range(100):
        _contract(db_session, id_seq=f"ACTIVE{i}", status="A")
    for i in range(900):
        _contract(db_session, id_seq=f"INACTIVE{i}", status="I")
    db_session.commit()

    items = ixc_ticket_queries.regional_breakdown(db_session, date_from=None, date_to=None)

    assert items[0]["contract_count"] == 100
    assert items[0]["tickets_per_1000_contracts"] == 50.0


def test_regional_breakdown_returns_none_rate_without_contracts(db_session):
    _ticket(db_session, source_id="T1")
    db_session.commit()

    items = ixc_ticket_queries.regional_breakdown(db_session, date_from=None, date_to=None)

    assert items[0]["contract_count"] is None
    assert items[0]["tickets_per_1000_contracts"] is None


def test_regional_breakdown_filters_by_period(db_session):
    _ticket(db_session, source_id="T1", created_at=datetime(2026, 8, 15, tzinfo=timezone.utc))
    _ticket(db_session, source_id="T2", created_at=datetime(2026, 9, 5, tzinfo=timezone.utc))
    db_session.commit()

    items = ixc_ticket_queries.regional_breakdown(
        db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30)
    )

    assert items[0]["ticket_count"] == 1


def test_regional_breakdown_computes_deviation_vs_previous_period_of_same_length(db_session):
    """Pedido do usuário (2026-09-12): "no drill ainda está sem dados de desvio" - o drill-down
    usa um período livre (não mês-calendário), então o "histórico" comparável é a janela
    IMEDIATAMENTE ANTERIOR de mesmo tamanho em dias (mesmo padrão do `previous_period()` do OPA),
    não uma média de meses calendário como na Visão Geral."""
    # Período atual: 01/09 a 10/09 (10 dias) - 20 atendimentos.
    for i in range(20):
        _ticket(db_session, source_id=f"T{i}", created_at=datetime(2026, 9, 1 + i % 10, tzinfo=timezone.utc))
    # Período anterior de mesmo tamanho (22/08 a 31/08) - 10 atendimentos.
    for i in range(10):
        _ticket(db_session, source_id=f"H{i}", created_at=datetime(2026, 8, 22 + i % 10, tzinfo=timezone.utc))
    db_session.commit()

    items = ixc_ticket_queries.regional_breakdown(
        db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 10)
    )

    assert items[0]["ticket_count"] == 20
    assert items[0]["previous_ticket_count"] == 10
    assert items[0]["deviation_pct"] == 100.0  # (20-10)/10*100


def test_regional_breakdown_suppresses_deviation_below_minimum_sample(db_session):
    """Sem o piso de amostra mínima, 1 atendimento virando 2 no período seguinte apareceria como
    "+100%" - ruído puro, não sinal (mesmo espírito de `MIN_HISTORICAL_SAMPLE` na Visão Geral)."""
    for i in range(2):
        _ticket(db_session, source_id=f"T{i}", created_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
    _ticket(db_session, source_id="H0", created_at=datetime(2026, 8, 31, tzinfo=timezone.utc))
    db_session.commit()

    items = ixc_ticket_queries.regional_breakdown(
        db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 1)
    )

    assert items[0]["previous_ticket_count"] == 1
    assert items[0]["deviation_pct"] is None


def test_regional_breakdown_deviation_is_none_without_period(db_session):
    _ticket(db_session, source_id="T1")
    db_session.commit()

    items = ixc_ticket_queries.regional_breakdown(db_session, date_from=None, date_to=None)

    assert items[0]["previous_ticket_count"] == 0
    assert items[0]["deviation_pct"] is None


def test_city_breakdown_computes_deviation(db_session):
    # Período atual: 04-05/09 (2 dias) - período anterior de mesmo tamanho: 02-03/09.
    for i in range(15):
        _ticket(db_session, source_id=f"T{i}", city="Nova Brasilândia D'Oeste", created_at=datetime(2026, 9, 4 + i % 2, tzinfo=timezone.utc))
    for i in range(10):
        _ticket(db_session, source_id=f"H{i}", city="Nova Brasilândia D'Oeste", created_at=datetime(2026, 9, 2 + i % 2, tzinfo=timezone.utc))
    db_session.commit()

    items = ixc_ticket_queries.city_breakdown(
        db_session, regional="UNI - NOVA BRASILANDIA DOESTE", date_from=date(2026, 9, 4), date_to=date(2026, 9, 5)
    )

    by_key = {item["key"]: item for item in items}
    assert by_key["Nova Brasilândia D'Oeste"]["previous_ticket_count"] == 10
    assert by_key["Nova Brasilândia D'Oeste"]["deviation_pct"] == 50.0


def test_neighborhood_breakdown_computes_deviation(db_session):
    for i in range(15):
        _ticket(db_session, source_id=f"T{i}", neighborhood="Centro", created_at=datetime(2026, 9, 4 + i % 2, tzinfo=timezone.utc))
    for i in range(10):
        _ticket(db_session, source_id=f"H{i}", neighborhood="Centro", created_at=datetime(2026, 9, 2 + i % 2, tzinfo=timezone.utc))
    db_session.commit()

    items = ixc_ticket_queries.neighborhood_breakdown(
        db_session,
        regional="UNI - NOVA BRASILANDIA DOESTE",
        city="Nova Brasilândia D'Oeste",
        date_from=date(2026, 9, 4),
        date_to=date(2026, 9, 5),
    )

    assert items[0]["previous_ticket_count"] == 10
    assert items[0]["deviation_pct"] == 50.0


def test_reason_breakdown_computes_deviation(db_session):
    for i in range(15):
        _ticket(db_session, source_id=f"T{i}", subject_id="90", created_at=datetime(2026, 9, 4 + i % 2, tzinfo=timezone.utc))
    for i in range(10):
        _ticket(db_session, source_id=f"H{i}", subject_id="90", created_at=datetime(2026, 9, 2 + i % 2, tzinfo=timezone.utc))
    db_session.commit()

    items = ixc_ticket_queries.reason_breakdown(
        db_session,
        regional="UNI - NOVA BRASILANDIA DOESTE",
        city="Nova Brasilândia D'Oeste",
        neighborhood="Centro",
        date_from=date(2026, 9, 4),
        date_to=date(2026, 9, 5),
    )

    assert items[0]["previous_ticket_count"] == 10
    assert items[0]["deviation_pct"] == 50.0


def test_city_breakdown_scoped_to_regional(db_session):
    _ticket(db_session, source_id="T1", city="Nova Brasilândia D'Oeste")
    _ticket(db_session, source_id="T2", city="Alto Alegre dos Parecis")
    _contract(db_session, id_seq="C1", city="Nova Brasilândia D'Oeste")
    db_session.commit()

    items = ixc_ticket_queries.city_breakdown(
        db_session, regional="UNI - NOVA BRASILANDIA DOESTE", date_from=None, date_to=None
    )

    keys = {item["key"] for item in items}
    assert keys == {"Nova Brasilândia D'Oeste", "Alto Alegre dos Parecis"}
    by_key = {item["key"]: item for item in items}
    assert by_key["Nova Brasilândia D'Oeste"]["contract_count"] == 1
    assert by_key["Alto Alegre dos Parecis"]["contract_count"] is None
    # Cobertura de 100% (1 de 1 contrato ativo da regional tem cidade resolvida) - taxa confiável.
    assert by_key["Nova Brasilândia D'Oeste"]["tickets_per_1000_contracts"] is not None


def test_city_breakdown_suppresses_rate_when_regional_city_coverage_is_low(db_session):
    """Achado real em produção (2026-09-11): regional com só 4,8% dos contratos ativos com
    cidade resolvida (95 de 1.977) fazia uma cidade específica mostrar >11.000/1.000 - número
    matematicamente certo com o denominador que existe, mas enganoso, porque o denominador real
    da cidade é desconhecido. Abaixo de MIN_CITY_COVERAGE_PCT a taxa deve vir None, não um número
    que parece preciso."""
    # 100 contratos ativos na regional, só 5 com cidade resolvida (5% de cobertura).
    for i in range(5):
        _contract(db_session, id_seq=f"CIDADE{i}", regional="UNI - SAO FELIPE DOESTE", city="São Felipe D'Oeste")
    for i in range(95):
        _contract(db_session, id_seq=f"SEMCIDADE{i}", regional="UNI - SAO FELIPE DOESTE", city=None)
    _ticket(db_session, source_id="T1", regional="UNI - SAO FELIPE DOESTE", city="São Felipe D'Oeste")
    db_session.commit()

    items = ixc_ticket_queries.city_breakdown(
        db_session, regional="UNI - SAO FELIPE DOESTE", date_from=None, date_to=None
    )

    by_key = {item["key"]: item for item in items}
    row = by_key["São Felipe D'Oeste"]
    assert row["contract_count"] == 5
    assert row["coverage_pct"] == 5.0
    assert row["tickets_per_1000_contracts"] is None


def test_city_breakdown_keeps_rate_when_coverage_is_above_threshold(db_session):
    for i in range(40):
        _contract(db_session, id_seq=f"CIDADE{i}", regional="UNI - SAO FELIPE DOESTE", city="São Felipe D'Oeste")
    for i in range(10):
        _contract(db_session, id_seq=f"SEMCIDADE{i}", regional="UNI - SAO FELIPE DOESTE", city=None)
    _ticket(db_session, source_id="T1", regional="UNI - SAO FELIPE DOESTE", city="São Felipe D'Oeste")
    db_session.commit()

    items = ixc_ticket_queries.city_breakdown(
        db_session, regional="UNI - SAO FELIPE DOESTE", date_from=None, date_to=None
    )

    by_key = {item["key"]: item for item in items}
    row = by_key["São Felipe D'Oeste"]
    assert row["coverage_pct"] == 80.0
    assert row["tickets_per_1000_contracts"] is not None


def test_neighborhood_breakdown_scoped_to_regional_and_city(db_session):
    _ticket(db_session, source_id="T1", neighborhood="Centro")
    _ticket(db_session, source_id="T2", neighborhood="Setor 2")
    _ticket(db_session, source_id="T3", city="Outra Cidade", neighborhood="Centro")
    db_session.commit()

    items = ixc_ticket_queries.neighborhood_breakdown(
        db_session,
        regional="UNI - NOVA BRASILANDIA DOESTE",
        city="Nova Brasilândia D'Oeste",
        date_from=None,
        date_to=None,
    )

    keys = {item["key"] for item in items}
    assert keys == {"Centro", "Setor 2"}


def test_reason_breakdown_groups_by_subject(db_session):
    _ticket(db_session, source_id="T1", subject_id="90", subject_name="Sem conexão")
    _ticket(db_session, source_id="T2", subject_id="90", subject_name="Sem conexão")
    _ticket(db_session, source_id="T3", subject_id="91", subject_name="Lentidão")
    db_session.commit()

    items = ixc_ticket_queries.reason_breakdown(
        db_session,
        regional="UNI - NOVA BRASILANDIA DOESTE",
        city="Nova Brasilândia D'Oeste",
        neighborhood="Centro",
        date_from=None,
        date_to=None,
    )

    by_key = {item["key"]: item["ticket_count"] for item in items}
    assert by_key == {"90": 2, "91": 1}


def test_list_tickets_filters_and_paginates(db_session):
    for i in range(3):
        _ticket(db_session, source_id=f"T{i}", protocol=f"P{i}")
    db_session.commit()

    total, rows = ixc_ticket_queries.list_tickets(
        db_session, regional="UNI - NOVA BRASILANDIA DOESTE", limit=2, offset=0
    )

    assert total == 3
    assert len(rows) == 2


def test_list_tickets_filters_by_subject(db_session):
    _ticket(db_session, source_id="T1", subject_id="90")
    _ticket(db_session, source_id="T2", subject_id="91")
    db_session.commit()

    total, rows = ixc_ticket_queries.list_tickets(
        db_session, regional="UNI - NOVA BRASILANDIA DOESTE", subject_id="91"
    )

    assert total == 1
    assert rows[0].subject_id == "91"


def test_list_tickets_filters_by_sector(db_session):
    _ticket(db_session, source_id="T1", sector_id="2", sector_name="Pós Venda")
    _ticket(db_session, source_id="T2", sector_id="3", sector_name="Retenção")
    db_session.commit()

    total, rows = ixc_ticket_queries.list_tickets(
        db_session, regional="UNI - NOVA BRASILANDIA DOESTE", sector_id="3"
    )

    assert total == 1
    assert rows[0].sector_id == "3"


def test_regional_breakdown_filters_by_subject_and_sector(db_session):
    _ticket(db_session, source_id="T1", subject_id="90", sector_id="2")
    _ticket(db_session, source_id="T2", subject_id="91", sector_id="3")
    db_session.commit()

    by_subject = ixc_ticket_queries.regional_breakdown(
        db_session, date_from=None, date_to=None, subject_id="90"
    )
    assert by_subject[0]["ticket_count"] == 1

    by_sector = ixc_ticket_queries.regional_breakdown(
        db_session, date_from=None, date_to=None, sector_id="3"
    )
    assert by_sector[0]["ticket_count"] == 1


def test_city_breakdown_filters_by_subject_and_sector(db_session):
    _ticket(db_session, source_id="T1", subject_id="90", sector_id="2")
    _ticket(db_session, source_id="T2", subject_id="91", sector_id="3")
    db_session.commit()

    items = ixc_ticket_queries.city_breakdown(
        db_session,
        regional="UNI - NOVA BRASILANDIA DOESTE",
        date_from=None,
        date_to=None,
        sector_id="2",
    )
    assert items[0]["ticket_count"] == 1


def test_neighborhood_breakdown_filters_by_subject(db_session):
    _ticket(db_session, source_id="T1", subject_id="90")
    _ticket(db_session, source_id="T2", subject_id="91")
    db_session.commit()

    items = ixc_ticket_queries.neighborhood_breakdown(
        db_session,
        regional="UNI - NOVA BRASILANDIA DOESTE",
        city="Nova Brasilândia D'Oeste",
        date_from=None,
        date_to=None,
        subject_id="91",
    )
    assert sum(item["ticket_count"] for item in items) == 1


def test_reason_breakdown_filters_by_sector(db_session):
    _ticket(db_session, source_id="T1", subject_id="90", sector_id="2")
    _ticket(db_session, source_id="T2", subject_id="91", sector_id="3")
    db_session.commit()

    items = ixc_ticket_queries.reason_breakdown(
        db_session,
        regional="UNI - NOVA BRASILANDIA DOESTE",
        city="Nova Brasilândia D'Oeste",
        neighborhood="Centro",
        date_from=None,
        date_to=None,
        sector_id="3",
    )
    by_key = {item["key"]: item["ticket_count"] for item in items}
    assert by_key == {"91": 1}


def test_regional_breakdown_filters_by_multiple_subjects(db_session):
    """Pedido do usuário (2026-09-12): filtro de motivo/setor é multi-seleção, não uma escolha só
    - vários ids separados por vírgula devem funcionar como OU entre eles."""
    _ticket(db_session, source_id="T1", subject_id="90")
    _ticket(db_session, source_id="T2", subject_id="91")
    _ticket(db_session, source_id="T3", subject_id="92")
    db_session.commit()

    items = ixc_ticket_queries.regional_breakdown(
        db_session, date_from=None, date_to=None, subject_id="90,91"
    )
    assert items[0]["ticket_count"] == 2


def test_list_tickets_filters_by_multiple_sectors(db_session):
    _ticket(db_session, source_id="T1", sector_id="2")
    _ticket(db_session, source_id="T2", sector_id="3")
    _ticket(db_session, source_id="T3", sector_id="4")
    db_session.commit()

    total, rows = ixc_ticket_queries.list_tickets(
        db_session, regional="UNI - NOVA BRASILANDIA DOESTE", sector_id="2,3"
    )
    assert total == 2


def test_reason_breakdown_filters_by_multiple_subjects(db_session):
    _ticket(db_session, source_id="T1", subject_id="90", subject_name="Sem conexão")
    _ticket(db_session, source_id="T2", subject_id="91", subject_name="Lentidão")
    _ticket(db_session, source_id="T3", subject_id="92", subject_name="Outro")
    db_session.commit()

    items = ixc_ticket_queries.reason_breakdown(
        db_session,
        regional="UNI - NOVA BRASILANDIA DOESTE",
        city="Nova Brasilândia D'Oeste",
        neighborhood="Centro",
        date_from=None,
        date_to=None,
        subject_id="90,91",
    )
    by_key = {item["key"]: item["ticket_count"] for item in items}
    assert by_key == {"90": 1, "91": 1}


def test_filter_options_lists_distinct_subjects_and_sectors(db_session):
    _ticket(db_session, source_id="T1", subject_id="90", subject_name="Sem conexão", sector_id="2", sector_name="Pós Venda")
    _ticket(db_session, source_id="T2", subject_id="90", subject_name="Sem conexão", sector_id="2", sector_name="Pós Venda")
    _ticket(db_session, source_id="T3", subject_id="91", subject_name="Lentidão", sector_id="3", sector_name="Retenção")
    db_session.commit()

    options = ixc_ticket_queries.filter_options(db_session)

    assert options["subjects"] == [
        {"id": "91", "name": "Lentidão"},
        {"id": "90", "name": "Sem conexão"},
    ]
    assert options["sectors"] == [
        {"id": "2", "name": "Pós Venda"},
        {"id": "3", "name": "Retenção"},
    ]


def test_filter_options_groups_subjects_by_theme(db_session):
    """Item 10 do plano (2026-09-17): "filtrar só por assuntos de problema de internet" - o
    motivo com taxonomia agrupa em `themes` (com os `subject_ids` que ele cobre); o motivo SEM
    taxonomia (`91` aqui) não entra em tema nenhum, só continua em `subjects`."""
    _ticket(db_session, source_id="T1", subject_id="90", subject_name="Sem conexão")
    _ticket(db_session, source_id="T2", subject_id="91", subject_name="Sem taxonomia")
    db_session.add(
        SupportIxcTaxonomyMapping(
            subject_id="90", theme_id="sem_conexao_fibra", theme_label="Sem conexão (fibra)",
            category_id="operacoes", category_label="Operações", effective_from=date(2026, 1, 1),
        )
    )
    db_session.commit()

    options = ixc_ticket_queries.filter_options(db_session)

    assert options["themes"] == [
        {
            "id": "sem_conexao_fibra",
            "name": "Sem conexão (fibra)",
            "category_id": "operacoes",
            "category_name": "Operações",
            "subject_ids": ["90"],
        }
    ]
