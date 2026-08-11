from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.models import User
from app.modules.ai import queries as ai_queries
from app.modules.operations.models import OperationOrder

DATE_FROM = date(2026, 7, 1)
DATE_TO = date(2026, 7, 31)


@pytest.fixture()
def ai_user(db_session):
    user = User(name="IA", email="ia-sla@pytest.local", role="admin", active=True, password_hash="x")
    db_session.add(user)
    db_session.flush()
    return user


def _make_order(db_session, *, order_code, opened_at, sla_target_hours=24, **overrides):
    defaults = dict(
        source_order_id=order_code,
        order_code=order_code,
        os_type="Manutenção",
        os_subject="Suporte Externo",
        opened_at=opened_at,
        sla_target_hours=sla_target_hours,
        is_closed=overrides.get("closed_at") is not None,
    )
    defaults.update(overrides)
    order = OperationOrder(**defaults)
    db_session.add(order)
    return order


def test_sla_stage_flags_for_order_covers_scheduled_and_unscheduled_cases():
    reference_at = datetime(2026, 7, 15, tzinfo=timezone.utc)
    opened_at = datetime(2026, 7, 10, 0, 0, tzinfo=timezone.utc)

    # Sem meta de SLA: nenhum dos dois indicadores pode ser calculado.
    no_target = SimpleNamespace(sla_target_hours=None, scheduled_at=None, opened_at=opened_at, closed_at=None)
    assert ai_queries._sla_stage_flags_for_order(no_target, reference_at) == (None, None)

    # Agendada 30h depois da abertura (meta de 24h) - agenda já veio vencida.
    scheduled_late = SimpleNamespace(
        sla_target_hours=24, scheduled_at=opened_at.replace(hour=6, day=11), opened_at=opened_at, closed_at=None
    )
    assert ai_queries._sla_stage_flags_for_order(scheduled_late, reference_at) == (True, True)

    # Agendada 10h depois da abertura (dentro da meta de 24h).
    scheduled_on_time = SimpleNamespace(
        sla_target_hours=24, scheduled_at=opened_at.replace(hour=10), opened_at=opened_at, closed_at=None
    )
    assert ai_queries._sla_stage_flags_for_order(scheduled_on_time, reference_at) == (False, False)

    # Nunca agendada, mas fechada 28h depois da abertura (meta de 24h) - scheduled_after_sla não
    # se aplica (None), mas o SLA já tinha vencido antes de qualquer agendamento acontecer.
    unscheduled_closed_late = SimpleNamespace(
        sla_target_hours=24, scheduled_at=None, opened_at=opened_at, closed_at=opened_at.replace(day=11, hour=4)
    )
    assert ai_queries._sla_stage_flags_for_order(unscheduled_closed_late, reference_at) == (None, True)

    # Nunca agendada, fechada 10h depois da abertura (dentro da meta).
    unscheduled_closed_on_time = SimpleNamespace(
        sla_target_hours=24, scheduled_at=None, opened_at=opened_at, closed_at=opened_at.replace(hour=10)
    )
    assert ai_queries._sla_stage_flags_for_order(unscheduled_closed_on_time, reference_at) == (None, False)

    # Ainda aberta, nunca agendada, aberta há mais tempo que a meta - usa reference_at (o "agora"
    # da consulta) como ponto de comparação.
    unscheduled_open_overdue = SimpleNamespace(
        sla_target_hours=24, scheduled_at=None, opened_at=datetime(2026, 7, 1, tzinfo=timezone.utc), closed_at=None
    )
    assert ai_queries._sla_stage_flags_for_order(unscheduled_open_overdue, reference_at) == (None, True)

    # Ainda aberta, nunca agendada, mas aberta há pouco tempo (dentro da meta até agora).
    unscheduled_open_fresh = SimpleNamespace(
        sla_target_hours=24, scheduled_at=None, opened_at=datetime(2026, 7, 14, 12, tzinfo=timezone.utc), closed_at=None
    )
    assert ai_queries._sla_stage_flags_for_order(unscheduled_open_fresh, reference_at) == (None, False)


def test_aggregate_orders_groups_by_scheduled_after_sla(db_session, ai_user):
    opened_at = datetime(2026, 7, 10, 0, 0, tzinfo=timezone.utc)
    _make_order(
        db_session,
        order_code="A-LATE-SCHEDULE",
        opened_at=opened_at,
        scheduled_at=opened_at.replace(day=11, hour=6),
        closed_at=opened_at.replace(day=11, hour=8),
    )
    _make_order(
        db_session,
        order_code="B-ON-TIME-SCHEDULE",
        opened_at=opened_at,
        scheduled_at=opened_at.replace(hour=10),
        closed_at=opened_at.replace(day=11, hour=2),
    )
    db_session.flush()

    result = ai_queries.aggregate_orders(
        db_session, ai_user, group_by="scheduled_after_sla", metric="quantidade_fechada",
        date_from=DATE_FROM, date_to=DATE_TO,
    )
    by_label = {item["label"]: item["quantity"] for item in result}
    assert by_label == {"Sim": 1, "Não": 1}


def test_aggregate_orders_groups_by_sla_expired_before_schedule_for_never_scheduled_orders(db_session, ai_user):
    opened_at = datetime(2026, 7, 10, 0, 0, tzinfo=timezone.utc)
    _make_order(
        db_session,
        order_code="E-UNSCHEDULED-LATE",
        opened_at=opened_at,
        scheduled_at=None,
        closed_at=opened_at.replace(day=11, hour=4),
    )
    _make_order(
        db_session,
        order_code="F-UNSCHEDULED-ON-TIME",
        opened_at=opened_at,
        scheduled_at=None,
        closed_at=opened_at.replace(hour=10),
    )
    db_session.flush()

    result = ai_queries.aggregate_orders(
        db_session, ai_user, group_by="sla_expired_before_schedule", metric="quantidade_fechada",
        date_from=DATE_FROM, date_to=DATE_TO,
    )
    by_label = {item["label"]: item["quantity"] for item in result}
    assert by_label == {"Sim": 1, "Não": 1}


def test_aggregate_orders_filters_by_sla_stage_booleans(db_session, ai_user):
    opened_at = datetime(2026, 7, 10, 0, 0, tzinfo=timezone.utc)
    _make_order(
        db_session,
        order_code="A-LATE-SCHEDULE-2",
        opened_at=opened_at,
        scheduled_at=opened_at.replace(day=11, hour=6),
        closed_at=opened_at.replace(day=11, hour=8),
        regional="UNI - REGIONAL A",
    )
    _make_order(
        db_session,
        order_code="B-ON-TIME-SCHEDULE-2",
        opened_at=opened_at,
        scheduled_at=opened_at.replace(hour=10),
        closed_at=opened_at.replace(day=11, hour=2),
        regional="UNI - REGIONAL A",
    )
    db_session.flush()

    only_late = ai_queries.aggregate_orders(
        db_session, ai_user, group_by="regional", metric="quantidade_fechada",
        date_from=DATE_FROM, date_to=DATE_TO, scheduled_after_sla=True,
    )
    assert sum(item["quantity"] for item in only_late) == 1

    only_on_time = ai_queries.aggregate_orders(
        db_session, ai_user, group_by="regional", metric="quantidade_fechada",
        date_from=DATE_FROM, date_to=DATE_TO, scheduled_after_sla=False,
    )
    assert sum(item["quantity"] for item in only_on_time) == 1


def test_aggregate_orders_computes_average_hours_per_sla_stage(db_session, ai_user):
    opened_at = datetime(2026, 7, 10, 0, 0, tzinfo=timezone.utc)
    _make_order(
        db_session,
        order_code="STAGE-DURATIONS",
        opened_at=opened_at,
        scheduled_at=opened_at.replace(day=11, hour=6),  # +30h
        execution_started_at=opened_at.replace(day=11, hour=7),  # +1h após agendado
        closed_at=opened_at.replace(day=11, hour=8),  # +1h após execução, +32h da abertura
        regional="UNI - REGIONAL A",
    )
    db_session.flush()

    def _metric_value(metric):
        result = ai_queries.aggregate_orders(
            db_session, ai_user, group_by="regional", metric=metric,
            date_from=DATE_FROM, date_to=DATE_TO,
        )
        assert len(result) == 1
        return result[0]["metric_value"]

    assert _metric_value("horas_abertura_agenda") == 30.0
    assert _metric_value("horas_agenda_execucao") == 1.0
    assert _metric_value("horas_execucao_fechamento") == 1.0
    assert _metric_value("horas_abertura_fechamento") == 32.0


def test_search_orders_exposes_sla_stage_fields_and_service_address(db_session, ai_user):
    opened_at = datetime(2026, 7, 10, 0, 0, tzinfo=timezone.utc)
    _make_order(
        db_session,
        order_code="SEARCH-SLA-STAGE",
        opened_at=opened_at,
        scheduled_at=opened_at.replace(day=11, hour=6),
        displacement_started_at=opened_at.replace(day=11, hour=6, minute=30),
        execution_started_at=opened_at.replace(day=11, hour=7),
        closed_at=opened_at.replace(day=11, hour=8),
        raw_payload={"endereco": "Rua das Flores, 123", "complemento": "Fundos"},
    )
    db_session.flush()

    result = ai_queries.search_orders(db_session, ai_user, date_from=DATE_FROM, date_to=DATE_TO)
    assert result["total_encontrado"] == 1
    item = result["items"][0]

    assert item["service_address"] == "Rua das Flores, 123\nComplemento: Fundos"
    # SQLite (usado nos testes) devolve o datetime sem tzinfo mesmo em coluna DateTime(timezone=True)
    # - compara só os componentes de data/hora, não a presença do fuso.
    assert item["displacement_started_at"].replace(tzinfo=None) == opened_at.replace(day=11, hour=6, minute=30, tzinfo=None)
    assert item["scheduled_after_sla"] is True
    assert item["sla_expired_before_schedule"] is True
    assert item["hours_open_to_schedule"] == 30.0
    assert item["hours_schedule_to_execution"] == 1.0
    assert item["hours_execution_to_close"] == 1.0
    assert item["hours_open_to_close"] == 32.0
