"""Reagendamentos atribuídos ao técnico de campo do PRÓPRIO EVENTO - corrigido em 2026-08-25: a
versão anterior agrupava pela O.S. inteira (`first_technician_id`), então um técnico aparecia com
reagendamento mesmo quando quem de fato reagendou foi outra pessoa numa O.S. que só por acaso era
dele. Agora só conta evento tipo "10" cujo `SchedulingEvent.technician_id` é o próprio técnico -
mesmo padrão de `reschedules_by_operator`, espelhando o campo trocado."""
from datetime import date, datetime

from app.modules.management.models import ManagementOperationalMember
from app.modules.operations.models import OperationTeamModel
from app.modules.scheduling import metrics
from app.modules.scheduling.models import SchedulingEvent, SchedulingOperator, SchedulingOrder, SchedulingTechnician
from app.services.calculation_closure import PORTO_VELHO_TZ


def _dt(day: int, hour: int = 9) -> datetime:
    return datetime(2026, 7, day, hour, 0, tzinfo=PORTO_VELHO_TZ)


def _make_field_technician(db_session, *, ixc_employee_id, name):
    """Cadastra o colaborador no módulo de Gestão com um modelo de equipe de campo - só assim
    `reschedules_by_technician`/`technician_events` o reconhece como técnico de verdade (ver
    `_field_technician_ixc_ids`, achado de 2026-08-25: gente do backoffice/agendamento também tem
    `id_tecnico` no IXC, então sem esse cadastro qualquer um aparecia como "técnico")."""
    team_model = db_session.query(OperationTeamModel).filter_by(name="TECNICO 12/36H").first()
    if team_model is None:
        team_model = OperationTeamModel(name="TECNICO 12/36H", daily_target=10, median_from_quantity=5, good_from_quantity=8)
        db_session.add(team_model)
        db_session.flush()
    member = ManagementOperationalMember(
        ixc_employee_id=ixc_employee_id,
        responsible_name=name,
        regional="REGIONAL TESTE",
        team_model_id=team_model.id,
        is_active=True,
    )
    db_session.add(member)
    db_session.flush()
    return member


def _make_order(db_session, *, ixc_os_id, schedule_event_count, technician_id=None):
    order = SchedulingOrder(
        ixc_os_id=ixc_os_id,
        opened_at=_dt(1),
        setor_id="7",
        setor_name="Setor Técnico",
        filial_id="1",
        assunto_id="10",
        assunto_name="Instalação",
        status="A",
        first_scheduled_at=_dt(1, 10),
        first_operator_id=None,
        first_technician_id=technician_id,
        schedule_event_count=schedule_event_count,
    )
    db_session.add(order)
    db_session.flush()
    return order


def test_reschedules_by_technician_only_counts_events_he_generated(db_session):
    db_session.add_all([
        SchedulingTechnician(ixc_funcionario_id=10, name="Carlos"),
        SchedulingTechnician(ixc_funcionario_id=20, name="Diego"),
    ])
    db_session.flush()
    # Só Carlos está cadastrado como técnico de campo na Gestão - Diego fica de fora mesmo que
    # apareça em algum evento (simula backoffice/agendamento com id_tecnico "emprestado").
    _make_field_technician(db_session, ixc_employee_id=10, name="Carlos")

    # O.S. do Carlos, mas os reagendamentos foram gerados nele mesmo (2x).
    order_carlos = _make_order(db_session, ixc_os_id=1001, schedule_event_count=3, technician_id=10)
    # O.S. do Diego - mas quem reagendou foi o Carlos (evento com technician_id=10), não o Diego.
    order_diego = _make_order(db_session, ixc_os_id=1002, schedule_event_count=2, technician_id=20)
    db_session.add_all([
        SchedulingEvent(ixc_message_id=1, ixc_os_id=order_carlos.ixc_os_id, event_type="5", event_at=_dt(1, 9), technician_id=10),
        SchedulingEvent(ixc_message_id=2, ixc_os_id=order_carlos.ixc_os_id, event_type="10", event_at=_dt(1, 10), technician_id=10),
        SchedulingEvent(ixc_message_id=3, ixc_os_id=order_carlos.ixc_os_id, event_type="10", event_at=_dt(1, 11), technician_id=10),
        SchedulingEvent(ixc_message_id=4, ixc_os_id=order_diego.ixc_os_id, event_type="5", event_at=_dt(1, 9), technician_id=20),
        SchedulingEvent(ixc_message_id=5, ixc_os_id=order_diego.ixc_os_id, event_type="10", event_at=_dt(1, 10), technician_id=10),
    ])
    db_session.commit()

    filters = metrics.SchedulingFilters(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))
    result = metrics.reschedules_by_technician(db_session, filters)

    assert result["date_from"] == date(2026, 7, 1)
    assert result["date_to"] == date(2026, 7, 31)
    by_id = {item["technician_id"]: item for item in result["items"]}

    # Carlos gerou os 2 reagendamentos da própria O.S. + o 1 na O.S. do Diego = 3.
    carlos = by_id[10]
    assert carlos["technician_name"] == "Carlos"
    assert carlos["reschedule_events"] == 3

    # Diego não gerou nenhum reagendamento pessoalmente - não deve aparecer.
    assert 20 not in by_id

    # Ordenado do que mais reagendou pro que menos.
    assert result["items"][0]["technician_id"] == 10


def test_reschedules_by_technician_excludes_backoffice_id_tecnico(db_session):
    """Achado real de 2026-08-25: o card listava "Vandesson" (operador de agendamento, não técnico
    de campo) porque um evento de reagendamento tinha `technician_id` igual ao `id_tecnico` dele no
    IXC. Sem cadastro na Gestão com modelo de equipe de campo, ele não deve aparecer."""
    db_session.add(SchedulingTechnician(ixc_funcionario_id=50, name="Vandesson (backoffice)"))
    db_session.flush()
    order = _make_order(db_session, ixc_os_id=1005, schedule_event_count=2, technician_id=50)
    db_session.add(SchedulingEvent(ixc_message_id=6, ixc_os_id=order.ixc_os_id, event_type="10", event_at=_dt(1, 10), technician_id=50))
    db_session.commit()

    filters = metrics.SchedulingFilters(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))
    result = metrics.reschedules_by_technician(db_session, filters)

    assert result["items"] == []


def test_reschedules_by_technician_endpoint(client, db_session):
    db_session.add(SchedulingTechnician(ixc_funcionario_id=30, name="Elias"))
    db_session.flush()
    _make_field_technician(db_session, ixc_employee_id=30, name="Elias")
    order = _make_order(db_session, ixc_os_id=2001, schedule_event_count=2, technician_id=30)
    db_session.add(SchedulingEvent(ixc_message_id=1, ixc_os_id=order.ixc_os_id, event_type="10", event_at=_dt(1, 10), technician_id=30))
    db_session.commit()

    response = client.get(
        "/api/scheduling/reschedules-by-technician",
        params={"date_from": "2026-07-01", "date_to": "2026-07-31"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["technician_id"] == 30
    assert body["items"][0]["reschedule_events"] == 1


def test_technician_events_only_returns_reschedules_he_generated(db_session, client):
    db_session.add_all([
        SchedulingTechnician(ixc_funcionario_id=10, name="Carlos"),
        SchedulingOperator(ixc_user_id=99, name="Helena"),
    ])
    db_session.flush()

    order = _make_order(db_session, ixc_os_id=6001, schedule_event_count=2, technician_id=10)
    other_order = _make_order(db_session, ixc_os_id=6002, schedule_event_count=2, technician_id=99)
    db_session.add_all([
        # 1o agendamento - nunca deve aparecer no drill de reagendamento.
        SchedulingEvent(ixc_message_id=1, ixc_os_id=order.ixc_os_id, event_type="5", event_at=_dt(1, 9), technician_id=10),
        # Reagendamento gerado pelo próprio Carlos - deve aparecer.
        SchedulingEvent(ixc_message_id=2, ixc_os_id=order.ixc_os_id, event_type="10", event_at=_dt(1, 10), technician_id=10, operator_id=99),
        # Reagendamento noutra O.S., mas o técnico do evento não é o Carlos - não deve aparecer.
        SchedulingEvent(ixc_message_id=3, ixc_os_id=other_order.ixc_os_id, event_type="10", event_at=_dt(1, 11), technician_id=99),
    ])
    db_session.commit()

    response = client.get(
        "/api/scheduling/technicians/10/events",
        params={"date_from": "2026-07-01", "date_to": "2026-07-31"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["ixc_os_id"] == 6001
    assert body["items"][0]["event_type"] == "10"
    assert body["items"][0]["operator_name"] == "Helena"


# --- reschedules_by_operator: contagem por AÇÃO (evento tipo "10"), não por O.S. ------------------


def test_reschedules_by_operator_counts_only_reschedule_events(db_session):
    db_session.add_all([
        SchedulingOperator(ixc_user_id=1, name="Ana", is_team_member=True),
        SchedulingOperator(ixc_user_id=2, name="Beto", is_team_member=False),
    ])
    db_session.flush()

    order_a = _make_order(db_session, ixc_os_id=3001, schedule_event_count=3)
    order_b = _make_order(db_session, ixc_os_id=3002, schedule_event_count=2)
    db_session.add_all([
        # 1o agendamento (tipo 5) - NUNCA deve contar como reagendamento.
        SchedulingEvent(ixc_message_id=1, ixc_os_id=order_a.ixc_os_id, event_type="5", event_at=_dt(1, 9), operator_id=1),
        # 2 reagendamentos da Ana na mesma O.S.
        SchedulingEvent(ixc_message_id=2, ixc_os_id=order_a.ixc_os_id, event_type="10", event_at=_dt(1, 10), operator_id=1),
        SchedulingEvent(ixc_message_id=3, ixc_os_id=order_a.ixc_os_id, event_type="10", event_at=_dt(1, 11), operator_id=1),
        # 1o agendamento + 1 reagendamento do Beto noutra O.S.
        SchedulingEvent(ixc_message_id=4, ixc_os_id=order_b.ixc_os_id, event_type="5", event_at=_dt(1, 9), operator_id=2),
        SchedulingEvent(ixc_message_id=5, ixc_os_id=order_b.ixc_os_id, event_type="10", event_at=_dt(1, 10), operator_id=2),
    ])
    db_session.commit()

    filters = metrics.SchedulingFilters(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))
    result = metrics.reschedules_by_operator(db_session, filters)

    by_id = {item["operator_id"]: item for item in result["items"]}
    assert by_id[1]["operator_name"] == "Ana"
    assert by_id[1]["is_team_member"] is True
    assert by_id[1]["reschedule_events"] == 2
    assert by_id[2]["operator_name"] == "Beto"
    assert by_id[2]["is_team_member"] is False
    assert by_id[2]["reschedule_events"] == 1
    # Ordenado do que mais reagendou pro que menos.
    assert result["items"][0]["operator_id"] == 1


def test_reschedules_by_operator_endpoint(client, db_session):
    db_session.add(SchedulingOperator(ixc_user_id=5, name="Fabio", is_team_member=True))
    db_session.flush()
    order = _make_order(db_session, ixc_os_id=4001, schedule_event_count=2)
    db_session.add(SchedulingEvent(ixc_message_id=1, ixc_os_id=order.ixc_os_id, event_type="10", event_at=_dt(1, 10), operator_id=5))
    db_session.commit()

    response = client.get(
        "/api/scheduling/reschedules-by-operator",
        params={"date_from": "2026-07-01", "date_to": "2026-07-31"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["operator_id"] == 5
    assert body["items"][0]["reschedule_events"] == 1


def test_filter_options_includes_technicians(db_session):
    db_session.add(SchedulingTechnician(ixc_funcionario_id=40, name="Gustavo"))
    db_session.flush()
    _make_order(db_session, ixc_os_id=5001, schedule_event_count=1, technician_id=40)
    db_session.commit()

    options = metrics.filter_options(db_session)
    assert {"id": 40, "name": "Gustavo"} in options["technicians"]
