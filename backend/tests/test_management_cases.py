"""Casos de gestão: motor de detecção, ciclo de vida e escopo de visibilidade."""

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import Collaborator, User
from app.modules.management import cases as cases_engine
from app.modules.management.models import ManagementCase, ManagementCaseReason, ManagementOperationalMember
from app.modules.operations.models import OperationOrder, OperationTeamModel

YEAR, MONTH = 2026, 7


def _order(responsible: str, regional: str, day: int, index: int) -> OperationOrder:
    closed = datetime(YEAR, MONTH, day, 15, 0, tzinfo=timezone.utc)
    return OperationOrder(
        source="ixc",
        source_order_id=f"OS-{responsible}-{day}-{index}",
        order_code=f"OS-{responsible}-{day}-{index}",
        regional=regional,
        os_type="Suporte",
        os_subject="Fibra",
        responsible=responsible,
        opened_at=closed,
        closed_at=closed,
        is_closed=True,
        raw_payload={},
    )


@pytest.fixture()
def operation_setup(db_session):
    """Um modelo de equipe com meta 5/dia e um membro operacional vinculado a um supervisor."""
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
    return {"supervisor": supervisor, "model": model, "member": member, "collaborator": collaborator}


def test_engine_opens_case_for_member_below_daily_target(db_session, operation_setup):
    # 6 dias trabalhados, 2 O.S./dia contra meta de 5 => desvio de 60%, severidade alta.
    for day in range(1, 7):
        for index in range(2):
            db_session.add(_order("Joao Campo", "UNI JARU", day, index))
    db_session.flush()

    result = cases_engine.generate_performance_cases(db_session, year=YEAR, month=MONTH)
    db_session.commit()

    assert result["created_cases"] == 1
    case = db_session.query(ManagementCase).one()
    assert case.case_type == cases_engine.CASE_TYPE_PRODUCTIVITY
    assert case.status == "pending"
    assert case.severity == "high"
    assert case.expected_value == 5.0
    assert case.actual_value == 2.0
    assert case.deviation_value == 60.0
    assert case.supervisor_user_id == operation_setup["supervisor"].id
    assert case.due_date is not None


def test_engine_is_idempotent(db_session, operation_setup):
    for day in range(1, 7):
        for index in range(2):
            db_session.add(_order("Joao Campo", "UNI JARU", day, index))
    db_session.flush()

    first = cases_engine.generate_performance_cases(db_session, year=YEAR, month=MONTH)
    db_session.commit()
    second = cases_engine.generate_performance_cases(db_session, year=YEAR, month=MONTH)
    db_session.commit()

    assert first["created_cases"] == 1
    assert second["created_cases"] == 0
    assert second["skipped_existing"] == 1
    assert db_session.query(ManagementCase).count() == 1


def test_engine_skips_member_meeting_target(db_session, operation_setup):
    # 6 dias com 5 O.S./dia: exatamente a meta, nenhum caso.
    for day in range(1, 7):
        for index in range(5):
            db_session.add(_order("Joao Campo", "UNI JARU", day, index))
    db_session.flush()

    result = cases_engine.generate_performance_cases(db_session, year=YEAR, month=MONTH)
    assert result["created_cases"] == 0
    assert result["evaluated_members"] == 1


def test_engine_skips_member_with_insufficient_days_worked(db_session, operation_setup):
    # Só 2 dias trabalhados (mínimo padrão é 5): média não é estatisticamente honesta, sem caso.
    # É o cenário de férias/admissão no meio do mês, que não pode virar cobrança.
    for day in range(1, 3):
        db_session.add(_order("Joao Campo", "UNI JARU", day, 0))
    db_session.flush()

    result = cases_engine.generate_performance_cases(db_session, year=YEAR, month=MONTH)
    assert result["created_cases"] == 0
    assert result["skipped_insufficient_data"] == 1


def test_engine_counts_orders_closed_late_on_the_last_local_day(db_session, operation_setup):
    """O.S. fechada 22h do dia 31 (local) cai no dia 1 do mês seguinte em UTC. Ela precisa contar
    na competência de julho - senão o colaborador aparece produzindo menos do que produziu."""
    for day in range(1, 6):
        for index in range(5):
            db_session.add(_order("Joao Campo", "UNI JARU", day, index))
    # 31/07 22:00 local == 01/08 02:00 UTC.
    late = datetime(YEAR, MONTH + 1, 1, 2, 0, tzinfo=timezone.utc)
    db_session.add(
        OperationOrder(
            source="ixc",
            source_order_id="OS-borda",
            order_code="OS-borda",
            regional="UNI JARU",
            os_type="Suporte",
            os_subject="Fibra",
            responsible="Joao Campo",
            opened_at=late,
            closed_at=late,
            is_closed=True,
            raw_payload={},
        )
    )
    db_session.flush()

    # 5 dias x 5 O.S. + 1 dia com 1 O.S. = 26 O.S. em 6 dias => média 4,33 (desvio de 13,3%),
    # abaixo do limiar de 15%: nenhum caso. Se a O.S. da borda fosse perdida, a média seria 5,0 -
    # o teste falharia em silêncio sem essa asserção intermediária.
    result = cases_engine.generate_performance_cases(db_session, year=YEAR, month=MONTH)
    assert result["evaluated_members"] == 1
    assert result["created_cases"] == 0

    # Com o limiar em 10%, o desvio de 13,3% (que só existe se a O.S. da borda foi contada) vira caso.
    cases_engine.save_settings(db_session, {"management_case_min_deviation_pct": "10"})
    assert cases_engine.generate_performance_cases(db_session, year=YEAR, month=MONTH)["created_cases"] == 1
    assert db_session.query(ManagementCase).one().actual_value == pytest.approx(4.33, abs=0.01)


def test_engine_respects_configured_threshold(db_session, operation_setup):
    # 6 dias com 4,5/dia => desvio de 10%, abaixo do limiar padrão de 15%.
    for day in range(1, 7):
        for index in range(4 if day % 2 else 5):
            db_session.add(_order("Joao Campo", "UNI JARU", day, index))
    db_session.flush()

    assert cases_engine.generate_performance_cases(db_session, year=YEAR, month=MONTH)["created_cases"] == 0

    cases_engine.save_settings(db_session, {"management_case_min_deviation_pct": "5"})
    assert cases_engine.generate_performance_cases(db_session, year=YEAR, month=MONTH)["created_cases"] == 1


# --- Ciclo de vida via API ----------------------------------------------------------------------


def _make_case(db_session, **overrides) -> ManagementCase:
    defaults = dict(
        case_type=cases_engine.CASE_TYPE_PRODUCTIVITY,
        source_module="operations",
        reference_year=YEAR,
        reference_month=MONTH,
        regional="UNI JARU",
        responsible_name="Joao Campo",
        metric_name=cases_engine.METRIC_DAILY_AVERAGE,
        expected_value=5.0,
        actual_value=2.0,
        deviation_value=60.0,
        severity="high",
        status="pending",
        due_date=date.today() + timedelta(days=7),
    )
    defaults.update(overrides)
    item = ManagementCase(**defaults)
    db_session.add(item)
    db_session.flush()
    return item


def test_cannot_resolve_a_case_that_was_never_justified(client, db_session, operation_setup):
    case = _make_case(db_session, supervisor_user_id=operation_setup["supervisor"].id)
    db_session.commit()

    response = client.post(f"/api/management/cases/{case.id}/review", json={"status": "resolved"})
    assert response.status_code == 409
    assert "justificado" in response.json()["detail"]


def test_justify_then_resolve_completes_the_lifecycle(client, db_session, admin_user, operation_setup):
    case = _make_case(db_session, supervisor_user_id=operation_setup["supervisor"].id)
    reason = ManagementCaseReason(name="Ausência / afastamento", active=True, requires_description=False)
    db_session.add(reason)
    db_session.commit()

    justify = client.post(
        f"/api/management/cases/{case.id}/justify",
        json={"reason_id": reason.id, "justification_text": "Colaborador de férias em 12 dias do mês."},
    )
    assert justify.status_code == 200
    assert justify.json()["status"] == "justified"
    assert justify.json()["justified_at"] is not None

    review = client.post(
        f"/api/management/cases/{case.id}/review",
        json={"status": "resolved", "review_note": "Férias confirmadas no RH."},
    )
    assert review.status_code == 200
    body = review.json()
    assert body["status"] == "resolved"
    assert body["reviewed_by"] == admin_user.id
    # A nota da revisão vira comentário em vez de sobrescrever a justificativa do supervisor.
    assert body["justification_text"] == "Colaborador de férias em 12 dias do mês."
    assert body["comment_count"] == 1


def test_reason_requiring_description_rejects_a_shallow_justification(client, db_session, operation_setup):
    case = _make_case(db_session, supervisor_user_id=operation_setup["supervisor"].id)
    reason = ManagementCaseReason(name="Outro", active=True, requires_description=True)
    db_session.add(reason)
    db_session.commit()

    shallow = client.post(
        f"/api/management/cases/{case.id}/justify",
        json={"reason_id": reason.id, "justification_text": "sei la"},
    )
    assert shallow.status_code == 400
    assert "descrição detalhada" in shallow.json()["detail"]

    detailed = client.post(
        f"/api/management/cases/{case.id}/justify",
        json={"reason_id": reason.id, "justification_text": "Equipe deslocada para o mutirão de Ariquemes por 8 dias."},
    )
    assert detailed.status_code == 200


def test_justification_cannot_close_a_case(client, db_session, operation_setup):
    """O supervisor não pode se auto-absolver: encerrar é decisão da matriz, via /review."""
    case = _make_case(db_session, supervisor_user_id=operation_setup["supervisor"].id)
    db_session.commit()

    response = client.post(
        f"/api/management/cases/{case.id}/justify",
        json={"justification_text": "Resolvido por mim mesmo.", "status": "resolved"},
    )
    assert response.status_code == 422


def test_overdue_is_derived_from_due_date(client, db_session, operation_setup):
    _make_case(db_session, supervisor_user_id=operation_setup["supervisor"].id, due_date=date.today() - timedelta(days=3))
    db_session.commit()

    body = client.get("/api/management/cases").json()
    assert body["items"][0]["is_overdue"] is True
    assert body["summary"]["overdue_cases"] == 1


# --- Escopo de visibilidade ---------------------------------------------------------------------


def _client_as(db_session, user: User) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_supervisor_only_sees_own_cases(db_session, operation_setup):
    """Sem `management:review`, o supervisor enxerga só o que é dele - o caso da outra regional
    não pode nem aparecer na lista, nem ser alcançável por ID."""
    other_supervisor = User(name="Supervisor Ariquemes", email="sup.ari@pytest.local", role="operator", active=True, password_hash="x")
    db_session.add(other_supervisor)
    db_session.flush()

    mine = _make_case(db_session, supervisor_user_id=operation_setup["supervisor"].id)
    theirs = _make_case(db_session, supervisor_user_id=other_supervisor.id, regional="UNI ARIQUEMES", responsible_name="Maria Campo")
    db_session.commit()

    try:
        client = _client_as(db_session, operation_setup["supervisor"])
        listing = client.get("/api/management/cases").json()
        assert [item["id"] for item in listing["items"]] == [mine.id]
        assert listing["total"] == 1
        # Fora do escopo responde 404, não 403: não vaza nem a existência do caso.
        assert client.get(f"/api/management/cases/{theirs.id}").status_code == 404
        assert client.post(f"/api/management/cases/{theirs.id}/justify", json={"justification_text": "tentativa"}).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_supervisor_cannot_review(db_session, operation_setup):
    case = _make_case(db_session, supervisor_user_id=operation_setup["supervisor"].id, status="justified")
    db_session.commit()

    try:
        client = _client_as(db_session, operation_setup["supervisor"])
        assert client.post(f"/api/management/cases/{case.id}/review", json={"status": "resolved"}).status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_admin_sees_every_regional(client, db_session, operation_setup):
    _make_case(db_session, supervisor_user_id=operation_setup["supervisor"].id)
    _make_case(db_session, regional="UNI ARIQUEMES", responsible_name="Maria Campo", severity="low")
    db_session.commit()

    body = client.get("/api/management/cases").json()
    assert body["total"] == 2
    # Fila ordenada por severidade real (high antes de low), não pela ordem alfabética do texto.
    assert [item["severity"] for item in body["items"]] == ["high", "low"]


def test_case_reasons_are_seeded_on_first_read(client, db_session):
    assert db_session.query(ManagementCaseReason).count() == 0
    body = client.get("/api/management/case-reasons").json()
    assert len(body) == len(cases_engine.DEFAULT_CASE_REASONS)
    assert all(item["active"] for item in body)


# --- Caso de um dia (drill do calendário) --------------------------------------------------------


def test_get_or_create_daily_case_opens_a_new_case(db_session, operation_setup):
    case, was_created = cases_engine.get_or_create_daily_case(
        db_session,
        responsible_name="Joao Campo",
        regional="UNI JARU",
        reference_date=date(2026, 7, 15),
        expected_value=5.0,
        actual_value=2.0,
    )
    db_session.commit()

    assert was_created is True
    assert case.case_type == cases_engine.CASE_TYPE_DAILY_BELOW
    assert case.source_module == "operations_calendar"
    assert case.metric_name == cases_engine.METRIC_DAILY_COUNT
    assert case.reference_date == date(2026, 7, 15)
    assert case.expected_value == 5.0
    assert case.actual_value == 2.0
    assert case.deviation_value == 60.0
    assert case.severity == "high"
    assert case.status == "pending"
    # Herda supervisor/modelo/colaborador do cadastro operacional, igual ao caso mensal.
    assert case.supervisor_user_id == operation_setup["supervisor"].id
    assert case.team_model_id == operation_setup["model"].id
    assert case.collaborator_id == operation_setup["collaborator"].id


def test_get_or_create_daily_case_is_idempotent_for_the_same_day(db_session, operation_setup):
    first, first_created = cases_engine.get_or_create_daily_case(
        db_session, responsible_name="Joao Campo", regional="UNI JARU",
        reference_date=date(2026, 7, 15), expected_value=5.0, actual_value=2.0,
    )
    db_session.commit()
    second, second_created = cases_engine.get_or_create_daily_case(
        db_session, responsible_name="Joao Campo", regional="UNI JARU",
        reference_date=date(2026, 7, 15), expected_value=5.0, actual_value=2.0,
    )
    db_session.commit()

    assert first_created is True
    assert second_created is False
    assert first.id == second.id
    assert db_session.query(ManagementCase).filter_by(case_type=cases_engine.CASE_TYPE_DAILY_BELOW).count() == 1


def test_daily_case_endpoint_lets_supervisor_open_and_justify_their_own_day(client, db_session, operation_setup):
    response = client.post(
        "/api/management/cases/daily",
        json={
            "responsible_name": "Joao Campo",
            "regional": "UNI JARU",
            "reference_date": "2026-07-15",
            "expected_value": 5.0,
            "actual_value": 2.0,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["case_type"] == cases_engine.CASE_TYPE_DAILY_BELOW
    assert body["status"] == "pending"

    justify = client.post(
        f"/api/management/cases/{body['id']}/justify",
        json={"justification_text": "Equipe reduzida por afastamento médico de um dos técnicos."},
    )
    assert justify.status_code == 200
    assert justify.json()["status"] == "justified"

    # Clicar de novo no mesmo dia devolve o MESMO caso, já justificado - não reabre pendente.
    reopened = client.post(
        "/api/management/cases/daily",
        json={
            "responsible_name": "Joao Campo",
            "regional": "UNI JARU",
            "reference_date": "2026-07-15",
            "expected_value": 5.0,
            "actual_value": 2.0,
        },
    )
    assert reopened.status_code == 200
    assert reopened.json()["id"] == body["id"]
    assert reopened.json()["status"] == "justified"


def test_daily_case_endpoint_hides_case_outside_supervisor_scope(db_session, operation_setup):
    """Um supervisor não pode usar o endpoint pra descobrir/abrir o caso de outra regional."""
    other_supervisor = User(name="Supervisor Ariquemes", email="sup.ari.daily@pytest.local", role="operator", active=True, password_hash="x")
    other_model = OperationTeamModel(name="Suporte Ariquemes", daily_target=5, active=True)
    db_session.add_all([other_supervisor, other_model])
    db_session.flush()
    db_session.add(
        ManagementOperationalMember(
            responsible_name="Maria Campo", regional="UNI ARIQUEMES", team_model_id=other_model.id,
            supervisor_user_id=other_supervisor.id, status="validated_operation", is_active=True,
        )
    )
    db_session.commit()

    try:
        client = _client_as(db_session, operation_setup["supervisor"])
        response = client.post(
            "/api/management/cases/daily",
            json={
                "responsible_name": "Maria Campo",
                "regional": "UNI ARIQUEMES",
                "reference_date": "2026-07-15",
                "expected_value": 5.0,
                "actual_value": 1.0,
            },
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
