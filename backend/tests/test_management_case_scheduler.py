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
