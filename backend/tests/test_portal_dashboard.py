"""Regression test for services/portal_dashboard.py's _resolve_score - the identity resolution
used by every /portal/* route. Before this fix, an admin/operator/viewer user with no name/e-mail
match against any collaborator fell back to `rows[0]` (the ranking's first place), leaking that
collaborator's score to an unrelated user. Now that users can be linked directly via
`users.collaborator_id`, that link must win, and no match at all must return None instead of
leaking data."""

from datetime import datetime, timezone

from app.models import CalculationRun, CollaboratorScore, ScoringGroup, ScoringSubjectRule, User
from app.services.portal_dashboard import (
    _audit_order,
    _order_label,
    _portal_run,
    _resolve_score,
    build_portal_audit,
    build_portal_orders,
    build_portal_overview,
    build_portal_rules,
    build_portal_summary,
)

ROWS = [
    {"collaborator_id": 1, "collaborator_name": "Ana Souza", "final_points": 100},
    {"collaborator_id": 2, "collaborator_name": "Bruno Lima", "final_points": 80},
]


def _user(**overrides):
    defaults = dict(id=1, name="Sem Match", email="semmatch@pytest.local", role="viewer", active=True, password_hash="x", collaborator_id=None)
    defaults.update(overrides)
    return User(**defaults)


def test_resolve_score_prefers_direct_collaborator_link():
    user = _user(name="Nome Qualquer", email="qualquer@pytest.local", collaborator_id=2)
    result = _resolve_score(user, ROWS)
    assert result is not None
    assert result["collaborator_id"] == 2


def test_resolve_score_falls_back_to_name_match_without_link():
    user = _user(name="Ana Souza", collaborator_id=None)
    result = _resolve_score(user, ROWS)
    assert result is not None
    assert result["collaborator_id"] == 1


def test_resolve_score_returns_none_without_link_or_match_admin():
    """Security regression: an admin with no link and no name/e-mail match must NOT see rows[0]."""
    user = _user(role="admin", name="Admin Sem Colaborador", email="admin@pytest.local", collaborator_id=None)
    result = _resolve_score(user, ROWS)
    assert result is None


def test_resolve_score_returns_none_without_link_or_match_viewer():
    user = _user(role="viewer", name="Viewer Sem Colaborador", email="viewer@pytest.local", collaborator_id=None)
    result = _resolve_score(user, ROWS)
    assert result is None


def test_audit_order_preserves_diagnosis_and_recurrence_evidence():
    result = _audit_order(
        {
            "os_code": "IXC-101",
            "os_type": "Manutenção",
            "os_subject": "Retorno",
            "customer_name": "Cliente Exemplo",
            "status_label": "Anulada por diagnóstico",
            "sla_status_normalized": "NO_PRAZO",
            "diagnosis_action_type": "cancel_points",
            "diagnosis_penalty_reason": "Diagnóstico X anulou a pontuação base",
            "recurrence_related_os_code": "IXC-202",
            "recurrence_days_between": 4,
        }
    )

    assert result["diagnosis_action_type"] == "cancel_points"
    assert result["diagnosis_penalty_reason"] == "Diagnóstico X anulou a pontuação base"
    assert result["recurrence_related_os_code"] == "IXC-202"
    assert result["recurrence_days_between"] == 4
    assert result["customer_name"] == "Cliente Exemplo"
    assert result["sla_status_normalized"] == "NO_PRAZO"


def test_order_label_hides_technical_sla_import_trace():
    status_label, reason = _order_label(
        {
            "is_annulled": True,
            "scoring_status": "Anulada por diagnóstico",
            "reasons": [
                "SLA original importado: Não informado",
                "SLA normalizado: NO_PRAZO",
                "Assunto vinculado ao grupo Manutenção",
                "Diagnóstico Equipamentos: Não Removidos anulou a pontuação base",
            ],
        }
    )

    assert status_label == "Anulada por diagnóstico"
    assert reason == "Diagnóstico Equipamentos: Não Removidos anulou a pontuação base"


def test_portal_rules_exposes_effective_points_and_source(db_session):
    group = ScoringGroup(name="Manutenção", default_points=12, active=True)
    db_session.add(group)
    db_session.flush()
    db_session.add_all(
        [
            ScoringSubjectRule(
                group_id=group.id,
                os_type="Manutenção",
                os_subject="Reparo padrão",
                use_group_default=True,
                active=True,
            ),
            ScoringSubjectRule(
                group_id=group.id,
                os_type="Manutenção",
                os_subject="Reparo especial",
                custom_points=25,
                use_group_default=False,
                active=True,
            ),
        ]
    )
    db_session.flush()

    result = build_portal_rules(db_session)
    subjects = {item["os_subject"]: item for item in result["subjects"]}

    assert subjects["Reparo padrão"]["points"] == 12
    assert subjects["Reparo padrão"]["point_source"] == "Valor padrão do grupo"
    assert subjects["Reparo especial"]["points"] == 25
    assert subjects["Reparo especial"]["point_source"] == "Valor específico deste assunto"


def test_portal_run_returns_the_latest_revision_for_the_requested_period(db_session):
    older_revision = CalculationRun(
        reference_month=6,
        reference_year=2026,
        status="approved",
        point_value=1,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    latest_revision = CalculationRun(
        reference_month=6,
        reference_year=2026,
        status="approved",
        point_value=1,
        created_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )
    other_period = CalculationRun(
        reference_month=7,
        reference_year=2026,
        status="approved",
        point_value=1,
        created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    db_session.add_all([older_revision, latest_revision, other_period])
    db_session.flush()

    result = _portal_run(db_session, reference_month=6, reference_year=2026)

    assert result is not None
    assert result.id == latest_revision.id


# --------------------------------------------------------------------------------------------
# Escopo da lista de O.S. do portal (validação de 2026-08-28)
#
# `build_portal_orders` filtrava as O.S. pela regional DO COLABORADOR, mas o card que aparece ao
# lado da lista vem do fechamento, que usa `run.regional`. Em fechamento global (`regional is
# None`, o caso de 100% da base) o cálculo conta toda O.S. da pessoa e agrupa por
# `collaborator_id` - a lista descartava tudo que estava em outra regional ou com regional
# `NAO IDENTIFICADO`. Medido na base real em 08/2026: 18 dos 107 colaboradores cadastrados tinham
# card != lista, somando 81 O.S. e 818 pontos base invisíveis (pior caso: card 68, lista 49).
# --------------------------------------------------------------------------------------------


def _linked_user(db_session, collaborator, email="colab@pytest.local"):
    user = User(
        name=collaborator.name,
        email=email,
        role="collaborator",
        active=True,
        password_hash="x",
        collaborator_id=collaborator.id,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _run_for(db_session, *, regional=None, month=6, year=2026):
    run = CalculationRun(
        reference_month=month,
        reference_year=year,
        regional=regional,
        point_value=2.0,
        status="draft",
        created_at=datetime(year, month, 28, tzinfo=timezone.utc),
    )
    db_session.add(run)
    db_session.flush()
    return run


def _score_for(db_session, run, collaborator, *, service_orders_count, gross_points):
    score = CollaboratorScore(
        calculation_run_id=run.id,
        collaborator_id=collaborator.id,
        service_orders_count=service_orders_count,
        gross_points=gross_points,
        penalty_points=0.0,
        net_points=gross_points,
        health_multiplier=1.0,
        health_status="Boa",
        final_points=gross_points,
        estimated_payment=gross_points * 2.0,
    )
    db_session.add(score)
    db_session.flush()
    return score


def test_portal_orders_lists_every_order_the_closure_counted(
    db_session, make_collaborator, make_service_order, scoring_setup
):
    """O caso real: fechamento global conta as 3 O.S., inclusive a de fora da regional e a
    `NAO IDENTIFICADO`. A lista precisa mostrar as 3, senão o colaborador soma a lista e não chega
    no número do próprio card."""
    collaborator = make_collaborator(name="Lucas", regional="UNI SUL")
    user = _linked_user(db_session, collaborator)
    make_service_order(collaborator, os_code="OS-CASA", regional="UNI SUL")
    make_service_order(collaborator, os_code="OS-OUTRA-REGIONAL", regional="UNI NORTE")
    make_service_order(collaborator, os_code="OS-SEM-REGIONAL", regional="NAO IDENTIFICADO")
    run = _run_for(db_session, regional=None)
    _score_for(db_session, run, collaborator, service_orders_count=3, gross_points=45.0)

    orders = build_portal_orders(db_session, user)

    assert {order["os_code"] for order in orders} == {"OS-CASA", "OS-OUTRA-REGIONAL", "OS-SEM-REGIONAL"}


def test_portal_orders_sum_matches_the_card_of_the_same_period(
    db_session, make_collaborator, make_service_order, scoring_setup
):
    """A prova que interessa pro colaborador: somar a lista tem que dar o total do card."""
    collaborator = make_collaborator(name="Lucas", regional="UNI SUL")
    user = _linked_user(db_session, collaborator)
    for index, regional in enumerate(("UNI SUL", "UNI SUL", "NAO IDENTIFICADO"), start=1):
        make_service_order(collaborator, os_code=f"OS-{index}", regional=regional)
    run = _run_for(db_session, regional=None)
    _score_for(db_session, run, collaborator, service_orders_count=3, gross_points=45.0)

    summary = build_portal_summary(db_session, user)
    orders = build_portal_orders(db_session, user)

    assert len(orders) == summary["score"]["service_orders_count"]
    assert round(sum(order["base_points"] for order in orders), 2) == summary["score"]["gross_points"]


def test_portal_orders_respects_a_regional_scoped_closure(
    db_session, make_collaborator, make_service_order, scoring_setup
):
    """O escopo vem do fechamento, não do colaborador: num fechamento POR REGIONAL, a lista tem que
    respeitar a mesma regional que o cálculo respeitou - a correção não é "nunca filtrar"."""
    collaborator = make_collaborator(name="Lucas", regional="UNI SUL")
    user = _linked_user(db_session, collaborator)
    make_service_order(collaborator, os_code="OS-DENTRO", regional="UNI SUL")
    make_service_order(collaborator, os_code="OS-FORA", regional="UNI NORTE")
    run = _run_for(db_session, regional="UNI SUL")
    _score_for(db_session, run, collaborator, service_orders_count=1, gross_points=15.0)

    orders = build_portal_orders(db_session, user)

    assert [order["os_code"] for order in orders] == ["OS-DENTRO"]


def test_portal_orders_never_leaks_another_collaborator(
    db_session, make_collaborator, make_service_order, scoring_setup
):
    """Isolamento: quem garante que a pessoa só vê O.S. dela é `collaborator_id`, não a regional.
    Tirar o filtro de regional não pode abrir a lista de um colega da mesma regional."""
    mine = make_collaborator(name="Lucas", regional="UNI SUL")
    theirs = make_collaborator(name="Colega", regional="UNI SUL")
    user = _linked_user(db_session, mine)
    make_service_order(mine, os_code="OS-MINHA", regional="UNI SUL")
    make_service_order(theirs, os_code="OS-DO-COLEGA", regional="UNI SUL")
    run = _run_for(db_session, regional=None)
    _score_for(db_session, run, mine, service_orders_count=1, gross_points=15.0)
    _score_for(db_session, run, theirs, service_orders_count=1, gross_points=15.0)

    orders = build_portal_orders(db_session, user)

    assert [order["os_code"] for order in orders] == ["OS-MINHA"]


def test_portal_audit_sla_bands_add_up_to_the_total(
    db_session, make_collaborator, make_service_order, scoring_setup
):
    """As três faixas de SLA saem da mesma lista e do mesmo predicado oficial, então somam o total.
    Antes, `sla_out` vinha do contador do fechamento e `sla_on_time` era recontado pelo rótulo de
    exibição - duas fontes e dois predicados que não fechavam entre si nem com o total."""
    collaborator = make_collaborator(name="Lucas", regional="UNI SUL")
    user = _linked_user(db_session, collaborator)
    # As três O.S. ficam retidas em variável de propósito: o identity map do SQLAlchemy usa
    # referência fraca, e o SQLite (só neste teste - Postgres real preserva timezone) devolve
    # datetime NAIVE ao recarregar um objeto que o GC coletou. Sem a referência aqui, um objeto
    # descartado sem querer reaparece sem tzinfo e quebra a comparação com os outros dois.
    order_in_time = make_service_order(collaborator, os_code="OS-NO-PRAZO", sla_status="Dentro do prazo")
    order_out_of_time = make_service_order(
        collaborator, os_code="OS-FORA", sla_status="Fora do prazo", regional="NAO IDENTIFICADO"
    )
    unmeasurable = make_service_order(collaborator, os_code="OS-SEM-PRAZO", sla_status="")
    # `sla_hours`/`closing_time_hours` têm default de coluna (24/0) que o SQLAlchemy reaplica em
    # QUALQUER flush enquanto o valor for None - passar `None` no construtor não sobrevive ao
    # primeiro flush da fixture. Zera os dois depois, num UPDATE, pra simular a O.S. sem meta de
    # horas configurada (o caso real de "não mensurável").
    unmeasurable.sla_hours = None
    unmeasurable.closing_time_hours = None
    db_session.flush()
    run = _run_for(db_session, regional=None)
    _score_for(db_session, run, collaborator, service_orders_count=3, gross_points=45.0)
    assert order_in_time.id and order_out_of_time.id  # mantém a referência viva até aqui

    audit = build_portal_audit(db_session, user)

    bands = (
        audit["sla_on_time_service_orders"]
        + audit["sla_out_service_orders"]
        + audit["sla_unidentified_service_orders"]
    )
    assert bands == audit["service_orders_count"] == 3
    # A O.S. fora do prazo está em regional `NAO IDENTIFICADO`: antes ela sumia da lista e o
    # contador de SLA fora divergia do oficial (5 vs 4 no colaborador 180 da base real).
    assert audit["sla_out_service_orders"] == 1
    assert audit["sla_unidentified_service_orders"] == 1


def test_portal_overview_reports_collaborators_excluded_from_the_ranking(
    db_session, make_collaborator, scoring_setup
):
    """Achado da crítica de design de 2026-08-28 (item 5): a Visão Geral conta só ativo+cadastrado
    (o ranking não pode comparar a pessoa contra um cadastro incompleto), mas o fechamento inteiro
    (aba Gamificação) conta todo mundo com O.S. - na base real isso divergia 107 vs 224
    colaboradores sem nenhuma explicação na tela. `excluded_collaborators`/`excluded_service_orders`
    tornam esse recorte explícito, sem entrar em nenhuma soma de pontos ou pagamento."""
    registered = make_collaborator(name="Cadastrado", registered=True)
    unregistered = make_collaborator(name="Sem Cadastro", registered=False)
    run = _run_for(db_session, regional=None)
    _score_for(db_session, run, registered, service_orders_count=10, gross_points=100.0)
    _score_for(db_session, run, unregistered, service_orders_count=4, gross_points=40.0)

    overview = build_portal_overview(db_session)

    assert overview["total_collaborators"] == 1
    assert overview["total_service_orders"] == 10
    assert overview["excluded_collaborators"] == 1
    assert overview["excluded_service_orders"] == 4


def test_portal_overview_excludes_nothing_when_everyone_is_registered(
    db_session, make_collaborator, scoring_setup
):
    """Caso comum: sem colaborador de fora, os contadores de exclusão ficam zerados - a nota na
    tela só aparece quando há algo real para explicar."""
    registered = make_collaborator(name="Cadastrado", registered=True)
    run = _run_for(db_session, regional=None)
    _score_for(db_session, run, registered, service_orders_count=10, gross_points=100.0)

    overview = build_portal_overview(db_session)

    assert overview["total_collaborators"] == 1
    assert overview["excluded_collaborators"] == 0
    assert overview["excluded_service_orders"] == 0
