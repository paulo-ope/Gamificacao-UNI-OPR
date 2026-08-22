"""Geração automática de casos de gestão (app/modules/management/scheduler.py).

Mesmo padrão de test_intelligence_scheduler.py: monkeypatch de SessionLocal por um stub que
sempre devolve a MESMA sessão de teste (in-memory sqlite)."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.modules.management import cases as cases_engine
from app.modules.management import scheduler
from app.modules.management.models import ManagementCase, ManagementOperationalMember
from app.modules.operations.models import OperationOrder, OperationTeamModel
from app.models import Collaborator, User

# Segunda-feira real (verificado com date(2026, 7, 6).weekday() == 0) - a classificação diária usa
# meta diferente por dia da semana, então um teste com data fixa precisa garantir que cai num dia
# de semana "normal" (sem isso o teste ficaria dependente de qual dia do mês foi escolhido).
MONDAY = date(2026, 7, 6)


class SessionLocalStub:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture(autouse=True)
def _patch_session_local(monkeypatch, db_session):
    monkeypatch.setattr(scheduler, "SessionLocal", SessionLocalStub(db_session))


@pytest.fixture()
def operation_setup(db_session):
    """Mesmo fixture usado em test_management_cases.py: colaborador com meta 5/dia, abaixo dela."""
    supervisor = User(name="Supervisor Jaru", email="sup.jaru@pytest.local", role="operator", active=True, password_hash="x")
    model = OperationTeamModel(name="Suporte Moto", daily_target=5, active=True)
    collaborator = Collaborator(name="Joao Campo", role="Tecnico", regional="UNI JARU", active=True, is_registered=True)
    db_session.add_all([supervisor, model, collaborator])
    db_session.flush()
    member = ManagementOperationalMember(
        responsible_name="Joao Campo",
        regional="UNI JARU",
        team_model_id=model.id,
        supervisor_user_id=supervisor.id,
        collaborator_id=collaborator.id,
        status="validated_operation",
        is_active=True,
    )
    db_session.add(member)
    db_session.flush()

    year, month = scheduler.previous_closed_period(date.today())
    for day in range(1, 7):
        for index in range(2):
            closed = datetime(year, month, day, 15, 0, tzinfo=timezone.utc)
            db_session.add(
                OperationOrder(
                    source="ixc",
                    source_order_id=f"OS-{day}-{index}",
                    order_code=f"OS-{day}-{index}",
                    regional="UNI JARU",
                    os_type="Suporte",
                    os_subject="Fibra",
                    responsible="Joao Campo",
                    opened_at=closed,
                    closed_at=closed,
                    is_closed=True,
                    raw_payload={},
                )
            )
    db_session.flush()
    return {"year": year, "month": month}


def test_previous_closed_period_is_the_month_before():
    assert scheduler.previous_closed_period(date(2026, 8, 20)) == (2026, 7)
    assert scheduler.previous_closed_period(date(2026, 1, 15)) == (2025, 12)


def test_run_auto_generate_once_opens_case_for_previous_month(db_session, operation_setup):
    result = scheduler.run_auto_generate_once()

    assert result is not None
    assert result["created_cases"] == 1
    assert result["reference_year"] == operation_setup["year"]
    assert result["reference_month"] == operation_setup["month"]
    case = db_session.query(ManagementCase).one()
    assert case.case_type == cases_engine.CASE_TYPE_PRODUCTIVITY
    assert case.created_by is None


def test_run_auto_generate_once_skips_second_call_same_day(db_session, operation_setup):
    first = scheduler.run_auto_generate_once()
    second = scheduler.run_auto_generate_once()

    assert first is not None
    assert second is None
    assert db_session.query(ManagementCase).count() == 1


def test_run_auto_generate_once_respects_disabled_setting(db_session, operation_setup):
    scheduler.set_auto_generate_enabled(False)

    result = scheduler.run_auto_generate_once()

    assert result is None
    assert db_session.query(ManagementCase).count() == 0


def test_auto_generate_enabled_defaults_to_true(db_session):
    assert scheduler.auto_generate_enabled() is True


@pytest.fixture()
def daily_case_setup(db_session):
    """Colaborador com 2 O.S. numa segunda-feira contra meta de 5/dia (median=3) - fica "below" no
    mesmo critério do calendário (`classify_daily_performance`)."""
    model = OperationTeamModel(name="Suporte Moto", daily_target=5, median_from_quantity=3, good_from_quantity=4, active=True)
    db_session.add(model)
    db_session.flush()
    db_session.add(
        ManagementOperationalMember(
            responsible_name="Joao Campo",
            regional="UNI JARU",
            team_model_id=model.id,
            status="validated_operation",
            is_active=True,
        )
    )
    for index in range(2):
        closed = datetime(MONDAY.year, MONDAY.month, MONDAY.day, 15, 0, tzinfo=timezone.utc)
        db_session.add(
            OperationOrder(
                source="ixc",
                source_order_id=f"OS-daily-{index}",
                order_code=f"OS-daily-{index}",
                regional="UNI JARU",
                os_type="Suporte",
                os_subject="Fibra",
                responsible="Joao Campo",
                opened_at=closed,
                closed_at=closed,
                is_closed=True,
                raw_payload={},
            )
        )
    db_session.flush()
    return {"model": model}


def test_generate_daily_cases_for_date_opens_case_for_below_target_day(db_session, daily_case_setup):
    result = cases_engine.generate_daily_cases_for_date(db_session, day=MONDAY)

    assert result["created_cases"] == 1
    assert result["evaluated_members"] == 1
    case = db_session.query(ManagementCase).one()
    assert case.case_type == cases_engine.CASE_TYPE_DAILY_BELOW
    assert case.reference_date == MONDAY
    assert case.actual_value == 2.0
    assert case.expected_value == 3.0
    assert case.created_by is None


def test_generate_daily_cases_for_date_is_idempotent(db_session, daily_case_setup):
    first = cases_engine.generate_daily_cases_for_date(db_session, day=MONDAY)
    second = cases_engine.generate_daily_cases_for_date(db_session, day=MONDAY)

    assert first["created_cases"] == 1
    assert second["created_cases"] == 0
    assert second["already_open_cases"] == 1
    assert db_session.query(ManagementCase).count() == 1


def test_generate_daily_cases_for_date_opens_case_for_zero_production(db_session):
    """Decisão de produto: zero produção num dia com meta ativa SEMPRE abre caso, mesmo sem saber
    se foi falta, férias ou atestado - cabe ao colaborador/supervisor explicar o motivo na
    justificativa, não ao sistema adivinhar antes de abrir o caso."""
    model = OperationTeamModel(name="Suporte Moto", daily_target=5, median_from_quantity=3, good_from_quantity=4, active=True)
    db_session.add(model)
    db_session.flush()
    db_session.add(
        ManagementOperationalMember(
            responsible_name="Maria Ferias",
            regional="UNI JARU",
            team_model_id=model.id,
            status="validated_operation",
            is_active=True,
        )
    )
    db_session.flush()
    # Nenhuma OperationOrder criada para "Maria Ferias" nessa segunda-feira - zero produção.

    result = cases_engine.generate_daily_cases_for_date(db_session, day=MONDAY)

    assert result["created_cases"] == 1
    case = db_session.query(ManagementCase).one()
    assert case.responsible_name == "Maria Ferias"
    assert case.actual_value == 0.0
    assert case.expected_value == 3.0


def test_generate_daily_cases_for_date_skips_sunday_without_a_target_rule(db_session):
    """Sem regra própria para domingo, o modelo não espera produção nesse dia (mesmo fallback do
    calendário) - zero produção num domingo não é "esperado produzir" e não deve abrir caso."""
    sunday = date(2026, 7, 5)
    model = OperationTeamModel(name="Suporte Moto", daily_target=5, median_from_quantity=3, good_from_quantity=4, active=True)
    db_session.add(model)
    db_session.flush()
    db_session.add(
        ManagementOperationalMember(
            responsible_name="Joao Campo",
            regional="UNI JARU",
            team_model_id=model.id,
            status="validated_operation",
            is_active=True,
        )
    )
    db_session.flush()

    result = cases_engine.generate_daily_cases_for_date(db_session, day=sunday)

    assert result["created_cases"] == 0
    assert result["evaluated_members"] == 0
    assert db_session.query(ManagementCase).count() == 0


def test_generate_daily_cases_for_date_skips_members_at_or_above_target(db_session, daily_case_setup):
    # Sobe pra 5 O.S. (== daily_target) - não é "below" nesse critério.
    for index in range(3):
        closed = datetime(MONDAY.year, MONDAY.month, MONDAY.day, 16, index, tzinfo=timezone.utc)
        db_session.add(
            OperationOrder(
                source="ixc",
                source_order_id=f"OS-daily-extra-{index}",
                order_code=f"OS-daily-extra-{index}",
                regional="UNI JARU",
                os_type="Suporte",
                os_subject="Fibra",
                responsible="Joao Campo",
                opened_at=closed,
                closed_at=closed,
                is_closed=True,
                raw_payload={},
            )
        )
    db_session.flush()

    result = cases_engine.generate_daily_cases_for_date(db_session, day=MONDAY)

    assert result["created_cases"] == 0
    assert db_session.query(ManagementCase).count() == 0


def test_run_daily_auto_generate_once_targets_yesterday(db_session, daily_case_setup, monkeypatch):
    tuesday = datetime(MONDAY.year, MONDAY.month, MONDAY.day + 1, 12, 0, tzinfo=scheduler.MANAGEMENT_TIMEZONE)
    monkeypatch.setattr(scheduler, "datetime", type("_FixedDatetime", (), {"now": staticmethod(lambda tz=None: tuesday)}))

    result = scheduler.run_daily_auto_generate_once()

    assert result is not None
    assert result["created_cases"] == 1
    assert result["reference_date"] == MONDAY.isoformat()


def test_run_daily_auto_generate_once_skips_second_call_same_day(db_session, daily_case_setup, monkeypatch):
    tuesday = datetime(MONDAY.year, MONDAY.month, MONDAY.day + 1, 12, 0, tzinfo=scheduler.MANAGEMENT_TIMEZONE)
    monkeypatch.setattr(scheduler, "datetime", type("_FixedDatetime", (), {"now": staticmethod(lambda tz=None: tuesday)}))

    first = scheduler.run_daily_auto_generate_once()
    second = scheduler.run_daily_auto_generate_once()

    assert first is not None
    assert second is None
    assert db_session.query(ManagementCase).count() == 1


def test_run_daily_auto_generate_once_respects_disabled_setting(db_session, daily_case_setup):
    scheduler.set_auto_generate_enabled(False)

    result = scheduler.run_daily_auto_generate_once()

    assert result is None
    assert db_session.query(ManagementCase).count() == 0


# --- Recálculo diário de casos "pending" (app/modules/management/scheduler.run_refresh_pending_cases_once) ----
# Achado real de 2026-08-21: O.S. atrasadas deixavam caso "pending" congelado num número velho -
# este loop recalcula contra a produção fechada até agora, uma vez por dia.


def test_run_refresh_pending_cases_once_resolves_a_case_once_production_catches_up(db_session, daily_case_setup, monkeypatch):
    tuesday = datetime(MONDAY.year, MONDAY.month, MONDAY.day + 1, 12, 0, tzinfo=scheduler.MANAGEMENT_TIMEZONE)
    monkeypatch.setattr(scheduler, "datetime", type("_FixedDatetime", (), {"now": staticmethod(lambda tz=None: tuesday)}))

    generated = scheduler.run_daily_auto_generate_once()
    assert generated["created_cases"] == 1
    case = db_session.query(ManagementCase).one()
    assert case.status == "pending"
    assert case.actual_value == 2.0

    first_refresh = scheduler.run_refresh_pending_cases_once()
    assert first_refresh is not None
    assert first_refresh["daily_refreshed"] == 1  # ainda abaixo da meta (2 de 5), so refresh, sem resolver
    db_session.refresh(case)
    assert case.status == "pending"

    same_day_again = scheduler.run_refresh_pending_cases_once()
    assert same_day_again is None  # ja rodou hoje, nada a fazer

    # O.S. "chegou atrasada" pro mesmo dia (mesma data-alvo do caso, MONDAY).
    for index in range(2, 6):
        db_session.add(
            OperationOrder(
                source="ixc",
                source_order_id=f"OS-late-{index}",
                order_code=f"OS-late-{index}",
                regional="UNI JARU",
                os_type="Suporte",
                os_subject="Fibra",
                responsible="Joao Campo",
                opened_at=datetime(MONDAY.year, MONDAY.month, MONDAY.day, 15, 0, tzinfo=timezone.utc),
                closed_at=datetime(MONDAY.year, MONDAY.month, MONDAY.day, 15, 0, tzinfo=timezone.utc),
                is_closed=True,
                raw_payload={},
            )
        )
    db_session.commit()

    wednesday = datetime(MONDAY.year, MONDAY.month, MONDAY.day + 2, 12, 0, tzinfo=scheduler.MANAGEMENT_TIMEZONE)
    monkeypatch.setattr(scheduler, "datetime", type("_FixedDatetime", (), {"now": staticmethod(lambda tz=None: wednesday)}))

    second_refresh = scheduler.run_refresh_pending_cases_once()
    assert second_refresh is not None
    assert second_refresh["daily_resolved"] == 1
    db_session.refresh(case)
    assert case.status == "resolved"
    assert case.actual_value == 6.0


def test_run_refresh_pending_cases_once_respects_disabled_setting(db_session, daily_case_setup):
    scheduler.set_auto_generate_enabled(False)

    result = scheduler.run_refresh_pending_cases_once()

    assert result is None
