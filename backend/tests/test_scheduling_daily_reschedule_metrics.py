from datetime import date, datetime, timezone

from app.modules.management.models import ManagementOperationalMember
from app.modules.scheduling import metrics
from app.modules.scheduling.models import SchedulingEvent, SchedulingOperator, SchedulingOrder
from app.services.calculation_closure import PORTO_VELHO_TZ


def _dt(day: int, hour: int = 9) -> datetime:
    return datetime(2026, 7, day, hour, 0, tzinfo=PORTO_VELHO_TZ)


def _make_order(db_session, *, ixc_os_id: int, opened_day: int = 1) -> SchedulingOrder:
    order = SchedulingOrder(
        ixc_os_id=ixc_os_id,
        opened_at=_dt(opened_day),
        setor_id="7",
        setor_name="Setor Técnico",
        filial_id="1",
        assunto_id="10",
        assunto_name="Instalação",
        status="A",
        schedule_event_count=1,
    )
    db_session.add(order)
    db_session.flush()
    return order


def _daily_point(dashboard: dict, day: str) -> dict:
    return next(item for item in dashboard["daily_series"] if item["date"] == day)


def test_daily_series_splits_first_schedule_from_reschedule(db_session):
    db_session.add(SchedulingOperator(ixc_user_id=1, name="Ana", is_team_member=True))
    db_session.flush()

    order = _make_order(db_session, ixc_os_id=3001)
    db_session.add_all([
        SchedulingEvent(ixc_message_id=1, ixc_os_id=order.ixc_os_id, event_type="5", event_at=_dt(1, 9), operator_id=1),
        SchedulingEvent(ixc_message_id=2, ixc_os_id=order.ixc_os_id, event_type="10", event_at=_dt(1, 10), operator_id=1),
        SchedulingEvent(ixc_message_id=3, ixc_os_id=order.ixc_os_id, event_type="10", event_at=_dt(1, 11), operator_id=1),
    ])
    db_session.commit()

    filters = metrics.SchedulingFilters(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))
    dashboard = metrics.build_dashboard(db_session, filters)
    point = _daily_point(dashboard, "2026-07-01")

    assert point["first_schedule_events"] == 1
    assert point["reschedule_events"] == 2
    # schedule_events preservado (5+10) para compatibilidade com quem já consumia o campo.
    assert point["schedule_events"] == 3


def test_daily_series_reschedule_by_team_member_only(db_session):
    db_session.add(SchedulingOperator(ixc_user_id=1, name="Ana", is_team_member=True))
    db_session.add(SchedulingOperator(ixc_user_id=2, name="Beto", is_team_member=False))
    db_session.add(
        ManagementOperationalMember(
            ixc_employee_id=901, responsible_name="Carlos Técnico", regional="Regional 1", team_model_id=1, is_active=True,
        )
    )
    db_session.flush()

    order = _make_order(db_session, ixc_os_id=3002)
    db_session.add_all([
        SchedulingEvent(ixc_message_id=1, ixc_os_id=order.ixc_os_id, event_type="10", event_at=_dt(1, 10), operator_id=1),
        SchedulingEvent(ixc_message_id=2, ixc_os_id=order.ixc_os_id, event_type="10", event_at=_dt(1, 11), operator_id=2, technician_id=901),
    ])
    db_session.commit()

    filters = metrics.SchedulingFilters(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))
    dashboard = metrics.build_dashboard(db_session, filters)
    point = _daily_point(dashboard, "2026-07-01")

    assert point["reschedule_events"] == 2
    assert point["team_reschedule_events"] == 1
    assert point["field_reschedule_events"] == 1
    assert point["unknown_reschedule_events"] == 0


def test_daily_series_reschedule_without_operator_counts_as_unknown(db_session):
    order = _make_order(db_session, ixc_os_id=3003)
    db_session.add(
        SchedulingEvent(ixc_message_id=1, ixc_os_id=order.ixc_os_id, event_type="10", event_at=_dt(1, 10), operator_id=None)
    )
    db_session.commit()

    filters = metrics.SchedulingFilters(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))
    dashboard = metrics.build_dashboard(db_session, filters)
    point = _daily_point(dashboard, "2026-07-01")

    # Evento não some do total nem fica sem classificação - sem operador de equipe nem técnico de
    # campo cadastrado, conta como desconhecido (não mais "campo/desconhecido" - separados agora).
    assert point["reschedule_events"] == 1
    assert point["team_reschedule_events"] == 0
    assert point["field_reschedule_events"] == 0
    assert point["unknown_reschedule_events"] == 1
    assert point["rescheduled_orders_distinct"] == 1


def test_daily_series_counts_distinct_rescheduled_orders_per_day(db_session):
    order = _make_order(db_session, ixc_os_id=3004)
    db_session.add_all([
        SchedulingEvent(ixc_message_id=1, ixc_os_id=order.ixc_os_id, event_type="10", event_at=_dt(1, 9), operator_id=None),
        SchedulingEvent(ixc_message_id=2, ixc_os_id=order.ixc_os_id, event_type="10", event_at=_dt(1, 15), operator_id=None),
    ])
    db_session.commit()

    filters = metrics.SchedulingFilters(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))
    dashboard = metrics.build_dashboard(db_session, filters)
    point = _daily_point(dashboard, "2026-07-01")

    # A mesma O.S. reagendada duas vezes no mesmo dia conta 2 EVENTOS, mas só 1 O.S. distinta.
    assert point["reschedule_events"] == 2
    assert point["rescheduled_orders_distinct"] == 1


def test_reschedule_day_detail_flags_origin_per_item(db_session):
    db_session.add(SchedulingOperator(ixc_user_id=1, name="Ana", is_team_member=True))
    db_session.add(SchedulingOperator(ixc_user_id=2, name="Beto", is_team_member=False))
    db_session.add(
        ManagementOperationalMember(
            ixc_employee_id=902, responsible_name="Carlos Técnico", regional="Regional 1", team_model_id=1, is_active=True,
        )
    )
    db_session.flush()

    order_team = _make_order(db_session, ixc_os_id=3005)
    order_field = _make_order(db_session, ixc_os_id=3006)
    order_unknown = _make_order(db_session, ixc_os_id=3007)
    db_session.add_all([
        SchedulingEvent(ixc_message_id=1, ixc_os_id=order_team.ixc_os_id, event_type="10", event_at=_dt(1, 10), operator_id=1),
        SchedulingEvent(ixc_message_id=2, ixc_os_id=order_field.ixc_os_id, event_type="10", event_at=_dt(1, 11), operator_id=2, technician_id=902),
        SchedulingEvent(ixc_message_id=3, ixc_os_id=order_unknown.ixc_os_id, event_type="10", event_at=_dt(1, 12), operator_id=None),
    ])
    db_session.commit()

    filters = metrics.SchedulingFilters(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))
    result = metrics.reschedule_day_detail(db_session, filters, day=date(2026, 7, 1))
    by_os = {item["ixc_os_id"]: item for item in result["items"]}

    assert by_os[3005]["origin"] == "equipe"
    assert by_os[3006]["origin"] == "campo"
    assert by_os[3007]["origin"] == "desconhecido"


def test_build_dashboard_filters_events_by_technician(db_session):
    order_a = _make_order(db_session, ixc_os_id=3008)
    order_b = _make_order(db_session, ixc_os_id=3009)
    db_session.add_all([
        SchedulingEvent(ixc_message_id=1, ixc_os_id=order_a.ixc_os_id, event_type="10", event_at=_dt(1, 10), technician_id=501),
        SchedulingEvent(ixc_message_id=2, ixc_os_id=order_b.ixc_os_id, event_type="10", event_at=_dt(1, 11), technician_id=502),
    ])
    db_session.commit()

    filters = metrics.SchedulingFilters(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31), technician_ids=[501])
    dashboard = metrics.build_dashboard(db_session, filters)
    point = _daily_point(dashboard, "2026-07-01")

    # Achado real de 2026-08-31: filtrar por técnico não afetava o calendário/produtividade porque
    # o filtro nunca era aplicado a essa consulta - só ao backlog/SLA (via `_cohort_query`).
    assert point["reschedule_events"] == 1


def test_reschedule_day_breakdown_aggregates_by_technician_operator_and_filial(db_session):
    db_session.add_all([
        ManagementOperationalMember(ixc_employee_id=501, responsible_name="Técnico 501", regional="Regional 1", team_model_id=1, is_active=True),
        ManagementOperationalMember(ixc_employee_id=502, responsible_name="Técnico 502", regional="Regional 1", team_model_id=1, is_active=True),
    ])
    order_a = _make_order(db_session, ixc_os_id=3010)
    order_b = _make_order(db_session, ixc_os_id=3011)
    db_session.add_all([
        SchedulingEvent(ixc_message_id=1, ixc_os_id=order_a.ixc_os_id, event_type="10", event_at=_dt(1, 9), technician_id=501, operator_id=1),
        SchedulingEvent(ixc_message_id=2, ixc_os_id=order_a.ixc_os_id, event_type="10", event_at=_dt(1, 10), technician_id=501, operator_id=1),
        SchedulingEvent(ixc_message_id=3, ixc_os_id=order_b.ixc_os_id, event_type="10", event_at=_dt(1, 11), technician_id=502, operator_id=2),
    ])
    db_session.commit()

    filters = metrics.SchedulingFilters(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))
    result = metrics.reschedule_day_breakdown(db_session, filters, day=date(2026, 7, 1))

    assert result["by_technician"][0] == {"key": "501", "label": "Técnico #501", "count": 2}
    assert result["by_operator"][0] == {"key": "1", "label": "Operador IXC 1", "count": 2}
    assert result["by_filial"][0]["count"] == 3


def test_reschedule_day_breakdown_excludes_technician_id_without_field_registration(db_session):
    # Achado real de 2026-08-31: "Yasmim" (backoffice/equipe) aparecia no ranking "Técnicos - mais
    # reagendamento hoje" porque o `technician_id` dela ficou gravado em alguma O.S. no IXC, mas
    # ela nunca teve modelo de equipe de campo cadastrado na Gestão. `by_technician` só deve
    # contar IDs com registro ativo de campo (`_field_technician_ixc_ids`), igual
    # `reschedules_by_technician` já fazia.
    db_session.add(
        ManagementOperationalMember(ixc_employee_id=501, responsible_name="Técnico de campo", regional="Regional 1", team_model_id=1, is_active=True)
    )
    order_a = _make_order(db_session, ixc_os_id=3013)
    order_b = _make_order(db_session, ixc_os_id=3014)
    db_session.add_all([
        SchedulingEvent(ixc_message_id=1, ixc_os_id=order_a.ixc_os_id, event_type="10", event_at=_dt(1, 9), technician_id=501),
        SchedulingEvent(ixc_message_id=2, ixc_os_id=order_b.ixc_os_id, event_type="10", event_at=_dt(1, 10), technician_id=999),
    ])
    db_session.commit()

    filters = metrics.SchedulingFilters(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))
    result = metrics.reschedule_day_breakdown(db_session, filters, day=date(2026, 7, 1))
    keys = {item["key"] for item in result["by_technician"]}

    assert keys == {"501"}


def test_reschedule_day_breakdown_only_counts_the_given_day(db_session):
    db_session.add(
        ManagementOperationalMember(ixc_employee_id=501, responsible_name="Técnico 501", regional="Regional 1", team_model_id=1, is_active=True)
    )
    order = _make_order(db_session, ixc_os_id=3012)
    db_session.add_all([
        SchedulingEvent(ixc_message_id=1, ixc_os_id=order.ixc_os_id, event_type="10", event_at=_dt(1, 9), technician_id=501),
        SchedulingEvent(ixc_message_id=2, ixc_os_id=order.ixc_os_id, event_type="10", event_at=_dt(2, 9), technician_id=501),
    ])
    db_session.commit()

    filters = metrics.SchedulingFilters(date_from=date(2026, 7, 1), date_to=date(2026, 7, 31))
    result = metrics.reschedule_day_breakdown(db_session, filters, day=date(2026, 7, 1))

    assert result["by_technician"][0]["count"] == 1


def test_day_key_converts_aware_datetime_to_porto_velho_calendar_day():
    # 03:30 UTC de 02/07 é 23:30 de 01/07 em Porto Velho (UTC-4) - o dia calendário tem que ser o
    # local, não o UTC, senão um evento perto da meia-noite cai no card do dia errado.
    instant_utc = datetime(2026, 7, 2, 3, 30, tzinfo=timezone.utc)

    assert metrics._day_key(instant_utc) == "2026-07-01"


def test_day_key_keeps_naive_datetime_as_already_local():
    # Datetime sem tzinfo (o que o SQLite dos testes devolve) já representa o horário local
    # gravado pelo sync - não deve ser reinterpretado por `.astimezone()` (que assumiria o fuso do
    # sistema, não Porto Velho).
    naive = datetime(2026, 7, 1, 23, 30)

    assert metrics._day_key(naive) == "2026-07-01"
