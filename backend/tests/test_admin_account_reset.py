"""Fase 2B do Portal - reset administrativo de senha e reabertura do primeiro acesso (pedido do
usuário em 2026-08-28, ver docs/portal-ciclo-vida-conta-colaborador.md seção 4). Ao contrário da
Fase 2A (voluntária, pelo próprio usuário), aqui é um admin agindo sobre a conta de outra pessoa -
por isso os dois endpoints exigem `users:manage`, a mesma permissão de `create_user`/`update_user`.
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.security import get_current_user, verify_password
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, User

KNOWN_PASSWORD = "SenhaConhecida123"


def _client_for(db_session, user: User) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _onboarded_user(db_session, collaborator, **overrides) -> User:
    from app.core.security import hash_password

    defaults = dict(
        name=collaborator.name if collaborator else "Usuario Interno",
        email=f"{(collaborator.name if collaborator else 'interno').lower().replace(' ', '.')}@login.local",
        role="collaborator" if collaborator else "viewer",
        active=True,
        password_hash=hash_password(KNOWN_PASSWORD),
        collaborator_id=collaborator.id if collaborator else None,
        must_change_password=False,
        first_access_completed_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    db_session.commit()
    return user


def _viewer_without_admin_permission(db_session) -> User:
    from app.core.security import hash_password

    user = User(
        name="Sem Permissao Admin",
        email="sem.permissao@pytest.local",
        role="viewer",
        active=True,
        password_hash=hash_password("QualquerSenha123"),
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_admin_forces_password_reset_and_returns_working_temporary_password(db_session, make_collaborator, admin_user):
    collaborator = make_collaborator(name="Reset De Senha")
    target = _onboarded_user(db_session, collaborator)

    with _client_for(db_session, admin_user) as client:
        response = client.post(f"/api/users/{target.id}/force-password-reset")
        assert response.status_code == 200
        body = response.json()
        assert "temporary_password" in body and len(body["temporary_password"]) >= 8
        assert body["portal_first_access_required"] is True
    app.dependency_overrides.clear()

    db_session.refresh(target)
    assert target.must_change_password is True
    # O primeiro acesso (CPF/contato) NÃO é reaberto por este endpoint - só a senha.
    assert target.first_access_completed_at is not None
    assert verify_password(body["temporary_password"], target.password_hash) is True
    assert verify_password(KNOWN_PASSWORD, target.password_hash) is False


def test_password_reset_forced_blocks_portal_until_password_changed(db_session, make_collaborator, admin_user):
    """Confirma que o reset administrativo realmente reaproveita o gate da Fase 1 - o alvo cai no
    onboarding no próximo login, sem nenhuma lógica de bloqueio nova."""
    collaborator = make_collaborator(name="Bloqueio Apos Reset")
    target = _onboarded_user(db_session, collaborator)

    with _client_for(db_session, admin_user) as client:
        response = client.post(f"/api/users/{target.id}/force-password-reset")
        assert response.status_code == 200
    app.dependency_overrides.clear()

    db_session.refresh(target)
    with _client_for(db_session, target) as client:
        blocked = client.get("/api/portal/summary")
        assert blocked.status_code == 403
    app.dependency_overrides.clear()


def test_admin_forces_first_access_reset(db_session, make_collaborator, admin_user):
    collaborator = make_collaborator(name="Primeiro Acesso Reaberto")
    target = _onboarded_user(db_session, collaborator)
    original_password_hash = target.password_hash

    with _client_for(db_session, admin_user) as client:
        response = client.post(f"/api/users/{target.id}/force-first-access")
        assert response.status_code == 200
        assert response.json()["portal_first_access_required"] is True
    app.dependency_overrides.clear()

    db_session.refresh(target)
    assert target.first_access_completed_at is None
    assert target.must_change_password is True
    # A senha atual não é tocada por este endpoint - a pessoa ainda entra com a senha que já tem,
    # só é forçada a refazer o formulário completo de primeiro acesso depois de logar.
    assert target.password_hash == original_password_hash
    assert verify_password(KNOWN_PASSWORD, target.password_hash) is True


def test_force_first_access_rejects_user_without_collaborator(db_session, admin_user):
    target = _onboarded_user(db_session, None)
    assert target.collaborator_id is None

    with _client_for(db_session, admin_user) as client:
        response = client.post(f"/api/users/{target.id}/force-first-access")
        assert response.status_code == 422
    app.dependency_overrides.clear()


def test_force_password_reset_requires_users_manage_permission(db_session, make_collaborator):
    collaborator = make_collaborator(name="Sem Permissao Alvo")
    target = _onboarded_user(db_session, collaborator)
    non_admin = _viewer_without_admin_permission(db_session)

    with _client_for(db_session, non_admin) as client:
        response = client.post(f"/api/users/{target.id}/force-password-reset")
        assert response.status_code == 403
    app.dependency_overrides.clear()

    db_session.refresh(target)
    assert target.must_change_password is False  # nada mudou


def test_force_first_access_requires_users_manage_permission(db_session, make_collaborator):
    collaborator = make_collaborator(name="Sem Permissao Alvo 2")
    target = _onboarded_user(db_session, collaborator)
    non_admin = _viewer_without_admin_permission(db_session)

    with _client_for(db_session, non_admin) as client:
        response = client.post(f"/api/users/{target.id}/force-first-access")
        assert response.status_code == 403
    app.dependency_overrides.clear()

    db_session.refresh(target)
    assert target.first_access_completed_at is not None  # nada mudou


def test_force_password_reset_on_missing_user_returns_404(db_session, admin_user):
    with _client_for(db_session, admin_user) as client:
        response = client.post("/api/users/999999/force-password-reset")
        assert response.status_code == 404
    app.dependency_overrides.clear()


def test_audit_log_never_stores_temporary_password(db_session, make_collaborator, admin_user):
    collaborator = make_collaborator(name="Auditoria Reset Senha")
    target = _onboarded_user(db_session, collaborator)

    with _client_for(db_session, admin_user) as client:
        response = client.post(f"/api/users/{target.id}/force-password-reset")
        assert response.status_code == 200
        temporary_password = response.json()["temporary_password"]
    app.dependency_overrides.clear()

    entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "user.password_reset_forced", AuditLog.entity_id == str(target.id))
        .one()
    )
    payload = str(entry.before_data) + str(entry.after_data)
    assert temporary_password not in payload
    db_session.refresh(target)
    assert target.password_hash not in payload
