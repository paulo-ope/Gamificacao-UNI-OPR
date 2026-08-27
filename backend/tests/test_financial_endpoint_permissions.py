"""Regressao da auditoria financeira 2026-08-26 (achados C2 e A8, lado de permissao).

Dois endpoints financeiros estavam abertos demais:

- `POST /leadership/bonus-results/calculate` exigia so `calculation:run` (nao administrador) e
  NAO checava o status do fechamento - dava pra alterar o `result_summary` de um fechamento JA
  PAGO, e cada chamada somava o bonus de lideranca de novo em `cost_by_regional` (achado C2).
- `GET /collaborators/{id}/statement.pdf` exigia so `audit:read`, que os perfis `viewer` e
  `operator` tem - qualquer leitor operacional baixava o extrato de pagamento individual de
  qualquer pessoa da empresa.
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import (
    AccessProfile,
    AccessProfilePermission,
    CalculationRun,
    CollaboratorScore,
    User,
    UserAccessProfile,
)


def _client_for(db_session, user: User) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def closure_runner(db_session):
    """Usuario com `calculation:run` por perfil de acesso, mas SEM ser administrador - o caso
    real que a checagem precisa barrar (nenhum papel legado tem `calculation:run` sem ser admin,
    mas um perfil customizado pode conceder)."""
    profile = AccessProfile(name="Operador de Fechamento", active=True)
    profile.permissions.append(AccessProfilePermission(permission="calculation:run"))
    profile.permissions.append(AccessProfilePermission(permission="audit:read"))
    profile.permissions.append(AccessProfilePermission(permission="dashboard:read"))
    db_session.add(profile)
    user = User(name="Fechador", email="fechador@pytest.local", role="operator", active=True, password_hash="x")
    db_session.add(user)
    db_session.flush()
    db_session.add(UserAccessProfile(user_id=user.id, profile_id=profile.id))
    db_session.flush()
    db_session.refresh(user)
    return user


@pytest.fixture()
def viewer(db_session):
    user = User(name="Leitor", email="leitor@pytest.local", role="viewer", active=True, password_hash="x")
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture()
def paid_run(db_session, make_collaborator):
    collaborator = make_collaborator(name="Tecnico Pago")
    run = CalculationRun(
        reference_month=7,
        reference_year=2026,
        regional=None,
        point_value=0.35,
        status="paid",
        paid_at=datetime(2026, 8, 5, tzinfo=timezone.utc),
        result_summary={"cost_by_regional": [{"regional": collaborator.regional, "orders": 1, "estimated_payment": 70.0}]},
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        CollaboratorScore(
            calculation_run_id=run.id,
            collaborator_id=collaborator.id,
            service_orders_count=1,
            gross_points=200.0,
            net_points=200.0,
            final_points=200.0,
            estimated_payment=70.0,
            health_multiplier=1.0,
        )
    )
    db_session.commit()
    return run, collaborator


def test_leadership_recalculation_is_refused_on_a_paid_run(db_session, admin_user, paid_run):
    """Um fechamento pago e um registro do que foi pago - nem o administrador pode recalcular o
    bonus por cima dele e mexer no `result_summary`."""
    run, _ = paid_run
    client = _client_for(db_session, admin_user)

    response = client.post("/api/leadership/bonus-results/calculate", params={"calculation_run_id": run.id})

    assert response.status_code == 409
    assert "pago" in response.json()["detail"].lower()


def test_leadership_recalculation_requires_admin(db_session, closure_runner, make_collaborator):
    """`calculation:run` sozinho nao basta: este endpoint reescreve valores financeiros gravados."""
    collaborator = make_collaborator(name="Tecnico Rascunho")
    run = CalculationRun(reference_month=7, reference_year=2026, regional=None, point_value=0.35, status="draft")
    db_session.add(run)
    db_session.flush()
    db_session.add(
        CollaboratorScore(
            calculation_run_id=run.id,
            collaborator_id=collaborator.id,
            service_orders_count=1,
            final_points=100.0,
            estimated_payment=35.0,
            health_multiplier=1.0,
        )
    )
    db_session.commit()
    client = _client_for(db_session, closure_runner)

    response = client.post("/api/leadership/bonus-results/calculate", params={"calculation_run_id": run.id})

    assert response.status_code == 403


def test_statement_pdf_is_not_open_to_every_reader(db_session, viewer, paid_run):
    """`audit:read` e concedida a `viewer` e `operator`. O extrato de pagamento individual e dado
    financeiro pessoal e nao pode sair por essa porta."""
    run, collaborator = paid_run
    client = _client_for(db_session, viewer)

    response = client.get(f"/api/collaborators/{collaborator.id}/statement.pdf", params={"calculation_run_id": run.id})

    assert response.status_code == 403


def test_statement_pdf_still_works_for_admin(db_session, admin_user, paid_run):
    """Contraprova: quem tem que emitir o extrato continua emitindo."""
    run, collaborator = paid_run
    client = _client_for(db_session, admin_user)

    response = client.get(f"/api/collaborators/{collaborator.id}/statement.pdf", params={"calculation_run_id": run.id})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"


def test_statement_pdf_works_for_the_collaborator_themselves(db_session, paid_run, make_collaborator):
    """O proprio colaborador pode baixar o proprio extrato pelo portal - o vinculo direto
    (`users.collaborator_id`) e o que autoriza, nao uma permissao ampla."""
    run, collaborator = paid_run
    owner = User(
        name=collaborator.name,
        email="dono@pytest.local",
        role="collaborator",
        active=True,
        password_hash="x",
        collaborator_id=collaborator.id,
    )
    db_session.add(owner)
    db_session.commit()
    client = _client_for(db_session, owner)

    response = client.get(f"/api/collaborators/{collaborator.id}/statement.pdf", params={"calculation_run_id": run.id})

    assert response.status_code == 200
