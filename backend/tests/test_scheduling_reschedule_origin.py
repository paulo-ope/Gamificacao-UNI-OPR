from datetime import date, datetime

from app.modules.scheduling import metrics
from app.modules.scheduling.models import SchedulingEvent, SchedulingOperator, SchedulingOrder
from app.services.calculation_closure import PORTO_VELHO_TZ


def _dt(day: int, hour: int = 9) -> datetime:
    return datetime(2026, 7, day, hour, 0, tzinfo=PORTO_VELHO_TZ)


def _make_order(db_session, *, ixc_os_id, schedule_event_count):
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
        schedule_event_count=schedule_event_count,
    )
    db_session.add(order)
    db_session.flush()
    return order


def test_reschedule_origin_split_and_filters(db_session):
    # Operador "Ana" é membro formal da equipe (backoffice); "Beto" não é (conta como campo).
    db_session.add(SchedulingOperator(ixc_user_id=1, name="Ana", is_team_member=True))
    db_session.add(SchedulingOperator(ixc_user_id=2, name="Beto", is_team_member=False))
    db_session.flush()

    backoffice_order = _make_order(db_session, ixc_os_id=1001, schedule_event_count=2)
    campo_order = _make_order(db_session, ixc_os_id=1002, schedule_event_count=2)
    unrescheduled_order = _make_order(db_session, ixc_os_id=1003, schedule_event_count=1)

    db_session.add_all([
        SchedulingEvent(ixc_message_id=1, ixc_os_id=backoffice_order.ixc_os_id, event_type="5", event_at=_dt(1, 9), operator_id=1),
        SchedulingEvent(ixc_message_id=2, ixc_os_id=backoffice_order.ixc_os_id, event_type="10", event_at=_dt(1, 10), operator_id=1),
        SchedulingEvent(ixc_message_id=3, ixc_os_id=campo_order.ixc_os_id, event_type="5", event_at=_dt(1, 9), operator_id=2),
        SchedulingEvent(ixc_message_id=4, ixc_os_id=campo_order.ixc_os_id, event_type="10", event_at=_dt(1, 10), operator_id=2),
        SchedulingEvent(ixc_message_id=5, ixc_os_id=unrescheduled_order.ixc_os_id, event_type="5", event_at=_dt(1, 9), operator_id=1),
    ])
    db_session.commit()

    filters = metrics.SchedulingFilters(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))

    dashboard = metrics.build_dashboard(db_session, filters)
    summary = dashboard["summary"]
    assert summary["rescheduled_orders"] == 2
    assert summary["reschedule_backoffice_count"] == 1
    assert summary["reschedule_campo_count"] == 1
    assert summary["reschedule_backoffice_pct"] == 50.0
    assert summary["reschedule_campo_pct"] == 50.0

    only_rescheduled = metrics.order_details(db_session, filters, only_rescheduled=True)
    assert {item["ixc_os_id"] for item in only_rescheduled["items"]} == {1001, 1002}

    backoffice_only = metrics.order_details(db_session, filters, reschedule_origin="backoffice")
    assert [item["ixc_os_id"] for item in backoffice_only["items"]] == [1001]
    assert backoffice_only["items"][0]["reschedule_origins"] == ["backoffice"]

    campo_only = metrics.order_details(db_session, filters, reschedule_origin="campo")
    assert [item["ixc_os_id"] for item in campo_only["items"]] == [1002]
    assert campo_only["items"][0]["reschedule_origins"] == ["campo"]


def test_reschedule_origin_pct_none_when_no_reschedules(db_session):
    _make_order(db_session, ixc_os_id=2001, schedule_event_count=1)
    db_session.add(SchedulingEvent(ixc_message_id=1, ixc_os_id=2001, event_type="5", event_at=_dt(1, 9), operator_id=1))
    db_session.commit()

    filters = metrics.SchedulingFilters(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))
    summary = metrics.build_dashboard(db_session, filters)["summary"]
    assert summary["reschedule_backoffice_pct"] is None
    assert summary["reschedule_campo_pct"] is None
