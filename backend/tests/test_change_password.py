"""Fase 2A do Portal - troca de senha pelo próprio usuário autenticado (pedido do usuário em
2026-08-28, ver docs/portal-ciclo-vida-conta-colaborador.md seção 3). Ao contrário da Fase 1
(primeiro acesso obrigatório), essa troca é voluntária, vale para qualquer usuário do ecossistema
(não só quem tem `collaborator_id`) e nunca mexe em `must_change_password` nem
`first_access_completed_at`.
"""

from fastapi.testclient import TestClient

from app.core.security import get_current_user, hash_password, verify_password
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, User

CURRENT_PASSWORD = "SenhaAtual123"


def _client_for(db_session, user: User) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _user_with_known_password(db_session, **overrides) -> User:
    defaults = dict(
        name="Usuario Com Senha",
        email="usuario.senha@pytest.local",
        role="collaborator",
        active=True,
        password_hash=hash_password(CURRENT_PASSWORD),
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    db_session.commit()
    return user


def test_change_password_success_updates_hash_and_keeps_first_access_flags_untouched(db_session, make_collaborator):
    """Critério de aceite central da 2A: senha muda, `password_changed_at` atualiza, e os campos
    da Fase 1 (`must_change_password`, `first_access_completed_at`) permanecem exatamente como
    estavam - troca voluntária de senha não é primeiro acesso."""
    collaborator = make_collaborator(name="Troca De Senha")
    user = _user_with_known_password(
        db_session,
        collaborator_id=collaborator.id,
        must_change_password=False,
        first_access_completed_at=None,
    )
    previous_changed_at = user.password_changed_at

    with _client_for(db_session, user) as client:
        response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": CURRENT_PASSWORD,
                "new_password": "SenhaNova456",
                "confirm_password": "SenhaNova456",
            },
        )
        assert response.status_code == 200
    app.dependency_overrides.clear()

    db_session.refresh(user)
    assert verify_password("SenhaNova456", user.password_hash) is True
    assert verify_password(CURRENT_PASSWORD, user.password_hash) is False
    assert user.password_changed_at != previous_changed_at
    assert user.password_changed_at is not None
    # Não é primeiro acesso: nenhum dos dois campos da Fase 1 é afetado por uma troca voluntária.
    assert user.must_change_password is False
    assert user.first_access_completed_at is None


def test_wrong_current_password_is_rejected(db_session, make_collaborator):
    collaborator = make_collaborator(name="Senha Atual Errada")
    user = _user_with_known_password(db_session, collaborator_id=collaborator.id)

    with _client_for(db_session, user) as client:
        response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "SenhaCompletamenteErrada",
                "new_password": "SenhaNova456",
                "confirm_password": "SenhaNova456",
            },
        )
        assert response.status_code == 401
        assert "incorreta" in response.json()["detail"].lower()
    app.dependency_overrides.clear()

    db_session.refresh(user)
    assert verify_password(CURRENT_PASSWORD, user.password_hash) is True


def test_new_password_confirmation_mismatch_is_rejected(db_session, make_collaborator):
    collaborator = make_collaborator(name="Confirmacao Diferente")
    user = _user_with_known_password(db_session, collaborator_id=collaborator.id)

    with _client_for(db_session, user) as client:
        response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": CURRENT_PASSWORD,
                "new_password": "SenhaNova456",
                "confirm_password": "OutraCoisa789",
            },
        )
        assert response.status_code == 422
    app.dependency_overrides.clear()

    db_session.refresh(user)
    assert verify_password(CURRENT_PASSWORD, user.password_hash) is True


def test_new_password_equal_to_current_is_rejected(db_session, make_collaborator):
    collaborator = make_collaborator(name="Senha Igual")
    user = _user_with_known_password(db_session, collaborator_id=collaborator.id)

    with _client_for(db_session, user) as client:
        response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": CURRENT_PASSWORD,
                "new_password": CURRENT_PASSWORD,
                "confirm_password": CURRENT_PASSWORD,
            },
        )
        assert response.status_code == 422
    app.dependency_overrides.clear()


def test_weak_new_password_is_rejected(db_session, make_collaborator):
    """Mesma política mínima de 8 caracteres introduzida na Fase 1 - reaproveitada aqui, não
    recriada com um limite diferente."""
    collaborator = make_collaborator(name="Senha Fraca 2A")
    user = _user_with_known_password(db_session, collaborator_id=collaborator.id)

    with _client_for(db_session, user) as client:
        response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": CURRENT_PASSWORD,
                "new_password": "123",
                "confirm_password": "123",
            },
        )
        assert response.status_code == 422
    app.dependency_overrides.clear()

    db_session.refresh(user)
    assert verify_password(CURRENT_PASSWORD, user.password_hash) is True


def test_internal_user_without_collaborator_can_also_change_password(db_session, admin_user):
    """A 2A vale pra qualquer usuário do ecossistema, não só quem representa um colaborador - ao
    contrário do primeiro acesso da Fase 1, que só se aplica a quem tem `collaborator_id`."""
    admin_user.password_hash = hash_password(CURRENT_PASSWORD)
    db_session.commit()

    with _client_for(db_session, admin_user) as client:
        response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": CURRENT_PASSWORD,
                "new_password": "SenhaNovaAdmin456",
                "confirm_password": "SenhaNovaAdmin456",
            },
        )
        assert response.status_code == 200
    app.dependency_overrides.clear()

    db_session.refresh(admin_user)
    assert verify_password("SenhaNovaAdmin456", admin_user.password_hash) is True


def test_audit_log_never_stores_password_in_any_form(db_session, make_collaborator):
    collaborator = make_collaborator(name="Auditoria Troca Senha")
    user = _user_with_known_password(db_session, collaborator_id=collaborator.id)

    with _client_for(db_session, user) as client:
        response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": CURRENT_PASSWORD,
                "new_password": "SenhaSuperSecreta789",
                "confirm_password": "SenhaSuperSecreta789",
            },
        )
        assert response.status_code == 200
    app.dependency_overrides.clear()

    entry = db_session.query(AuditLog).filter(AuditLog.action == "change_own_password", AuditLog.entity_id == str(user.id)).one()
    payload = str(entry.before_data) + str(entry.after_data)
    assert CURRENT_PASSWORD not in payload
    assert "SenhaSuperSecreta789" not in payload
    assert user.password_hash not in payload
