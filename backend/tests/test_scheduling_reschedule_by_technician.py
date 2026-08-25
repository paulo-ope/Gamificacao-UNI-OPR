"""Reagendamentos agrupados por técnico de campo - pedido do usuário em 2026-08-24: medir
instabilidade/retrabalho por colaborador (quantas das O.S. dele precisaram de reagendamento),
diferente da "origem" do reagendamento (quem clicou em reagendar), que já existia."""
from datetime import date, datetime

from app.modules.scheduling import metrics
from app.modules.scheduling.models import SchedulingEvent, SchedulingOperator, SchedulingOrder, SchedulingTechnician
from app.services.calculation_closure import PORTO_VELHO_TZ


def _dt(day: int, hour: int = 9) -> datetime:
    return datetime(2026, 7, day, hour, 0, tzinfo=PORTO_VELHO_TZ)


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


def test_reschedules_by_technician_groups_and_ranks(db_session):
    db_session.add_all([
        SchedulingTechnician(ixc_funcionario_id=10, name="Carlos"),
        SchedulingTechnician(ixc_funcionario_id=20, name="Diego"),
    ])
    db_session.flush()

    # Carlos: 2 O.S., 1 reagendada 2x (3 dias sem tecnico).
    _make_order(db_session, ixc_os_id=1001, schedule_event_count=3, technician_id=10)
    _make_order(db_session, ixc_os_id=1002, schedule_event_count=1, technician_id=10)
    # Diego: 1 O.S., nunca reagendada.
    _make_order(db_session, ixc_os_id=1003, schedule_event_count=1, technician_id=20)
    # Sem técnico definido - ainda entra na conta, sob chave None.
    _make_order(db_session, ixc_os_id=1004, schedule_event_count=2, technician_id=None)
    db_session.commit()

    filters = metrics.SchedulingFilters(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))
    result = metrics.reschedules_by_technician(db_session, filters)

    assert result["date_from"] == date(2026, 7, 1)
    assert result["date_to"] == date(2026, 7, 31)
    by_id = {item["technician_id"]: item for item in result["items"]}

    carlos = by_id[10]
    assert carlos["technician_name"] == "Carlos"
    assert carlos["total_orders"] == 2
    assert carlos["rescheduled_orders"] == 1
    assert carlos["reschedule_events"] == 2  # schedule_event_count 3 -> 2 reagendamentos
    assert carlos["reschedule_rate"] == 50.0

    diego = by_id[20]
    assert diego["total_orders"] == 1
    assert diego["rescheduled_orders"] == 0
    assert diego["reschedule_rate"] == 0.0

    sem_tecnico = by_id[None]
    assert sem_tecnico["technician_name"] == "Sem técnico definido"
    assert sem_tecnico["rescheduled_orders"] == 1

    # Ordenado do mais reagendado pro menos.
    assert [item["technician_id"] for item in result["items"][:1]] == [10]


def test_reschedules_by_technician_endpoint(client, db_session):
    db_session.add(SchedulingTechnician(ixc_funcionario_id=30, name="Elias"))
    db_session.flush()
    _make_order(db_session, ixc_os_id=2001, schedule_event_count=2, technician_id=30)
    db_session.commit()

    response = client.get(
        "/api/scheduling/reschedules-by-technician",
        params={"date_from": "2026-07-01", "date_to": "2026-07-31"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["technician_id"] == 30
    assert body["items"][0]["rescheduled_orders"] == 1


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
