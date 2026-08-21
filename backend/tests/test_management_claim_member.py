"""Reivindicação de colaborador pra própria base (organograma de campo do supervisor/gerente de
base) - pedido do usuário em 2026-08-20."""
from __future__ import annotations

from app.core.security import get_current_user, permissions_for_user
from app.db.session import get_db
from app.main import app
from app.models import User
from app.modules.management import services as management_services
from app.modules.management.models import ManagementOperationalMember


def _make_supervisor(db_session, role: str = "operator") -> User:
    supervisor = User(name="Supervisor Campo", email=f"supervisor-{role}@pytest.local", role=role, active=True, password_hash="x")
    db_session.add(supervisor)
    db_session.flush()
    return supervisor


def _make_member(db_session, **overrides) -> ManagementOperationalMember:
    defaults = dict(
        responsible_name="Colaborador Novo",
        regional="UNI JARU",
        status="pending_validation",
        is_active=True,
    )
    defaults.update(overrides)
    member = ManagementOperationalMember(**defaults)
    db_session.add(member)
    db_session.flush()
    return member


def test_operator_role_has_claim_member_permission():
    operator = User(name="Op", email="op@pytest.local", role="operator", active=True, password_hash="x")
    base_manager = User(name="Gerente", email="gerente@pytest.local", role="base_manager", active=True, password_hash="x")
    viewer = User(name="V", email="v@pytest.local", role="viewer", active=True, password_hash="x")

    assert "management:claim_member" in permissions_for_user(operator)
    assert "management:claim_member" in permissions_for_user(base_manager)
    assert "management:claim_member" not in permissions_for_user(viewer)


def test_claim_member_assigns_supervisor_and_advances_status(db_session):
    supervisor = _make_supervisor(db_session)
    member = _make_member(db_session, status="without_supervisor")
    db_session.commit()

    management_services.claim_member(db_session, member=member, claimer=supervisor)
    db_session.commit()

    assert member.supervisor_user_id == supervisor.id
    assert member.status == "without_team_model"


def test_claim_member_rejects_when_already_owned_by_someone_else(db_session):
    original_supervisor = _make_supervisor(db_session, role="operator")
    other_supervisor = User(name="Outro Supervisor", email="outro@pytest.local", role="operator", active=True, password_hash="x")
    db_session.add(other_supervisor)
    db_session.flush()
    member = _make_member(db_session, supervisor_user_id=original_supervisor.id, status="validated_operation")
    db_session.commit()

    try:
        management_services.claim_member(db_session, member=member, claimer=other_supervisor)
        assert False, "deveria ter levantado MemberAlreadyClaimedError"
    except management_services.MemberAlreadyClaimedError:
        pass

    assert member.supervisor_user_id == original_supervisor.id


def test_claim_member_is_idempotent_for_the_same_claimer(db_session):
    supervisor = _make_supervisor(db_session)
    member = _make_member(db_session, supervisor_user_id=supervisor.id, status="validated_operation")
    db_session.commit()

    management_services.claim_member(db_session, member=member, claimer=supervisor)
    db_session.commit()

    assert member.supervisor_user_id == supervisor.id


def test_claim_member_endpoint_lets_a_plain_supervisor_claim_an_unassigned_collaborator(client, db_session):
    supervisor = _make_supervisor(db_session)
    member = _make_member(db_session)
    db_session.commit()

    def override_user():
        return supervisor

    app.dependency_overrides[get_current_user] = override_user
    try:
        response = client.post(f"/api/management/members/{member.id}/claim")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    body = response.json()
    assert body["supervisor_user_id"] == supervisor.id


def test_claim_member_endpoint_rejects_a_user_without_the_permission(client, db_session):
    viewer = User(name="Leitor", email="leitor@pytest.local", role="viewer", active=True, password_hash="x")
    db_session.add(viewer)
    db_session.flush()
    member = _make_member(db_session)
    db_session.commit()

    def override_user():
        return viewer

    app.dependency_overrides[get_current_user] = override_user
    try:
        response = client.post(f"/api/management/members/{member.id}/claim")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403


def test_claim_member_endpoint_returns_409_when_already_owned(client, db_session):
    original_supervisor = _make_supervisor(db_session, role="operator")
    challenger = User(name="Desafiante", email="desafiante@pytest.local", role="operator", active=True, password_hash="x")
    db_session.add(challenger)
    db_session.flush()
    member = _make_member(db_session, supervisor_user_id=original_supervisor.id, status="validated_operation")
    db_session.commit()

    def override_user():
        return challenger

    app.dependency_overrides[get_current_user] = override_user
    try:
        response = client.post(f"/api/management/members/{member.id}/claim")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 409
