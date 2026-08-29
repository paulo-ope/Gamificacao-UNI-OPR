"""Fase 2C do Portal - convite seguro com token (pedido do usuário em 2026-08-28, ver
docs/portal-ciclo-vida-conta-colaborador.md seção 5). Ao contrário da Fase 1 (a pessoa já tem
conta e confirma CPF/senha) e da Fase 2B (admin agindo sobre conta já existente), aqui a conta
ainda não existe - o convite é quem a cria, com o vínculo (`collaborator_id`) decidido pelo admin
no momento da criação do convite, nunca pela pessoa convidada.
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.security import get_current_user, verify_password
from app.db.session import get_db
from app.main import app
from app.models import AccountActionToken, AuditLog, User


def _admin_client(db_session, admin_user) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    return TestClient(app)


def _public_client(db_session) -> TestClient:
    """Cliente sem override de `get_current_user` - as rotas de aceite de convite são públicas,
    não autenticadas; usar este cliente garante que elas realmente não exigem token."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_admin_creates_invite_and_token_is_never_stored_in_clear(db_session, make_collaborator, admin_user):
    collaborator = make_collaborator(name="Convite Novo")

    with _admin_client(db_session, admin_user) as client:
        response = client.post("/api/invites", json={"email": "convidado@exemplo.com", "collaborator_id": collaborator.id})
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "pending"
        assert body["collaborator_id"] == collaborator.id
        raw_token = body["token"]
        assert len(raw_token) > 20
    app.dependency_overrides.clear()

    stored = db_session.query(AccountActionToken).filter(AccountActionToken.id == body["id"]).one()
    assert stored.token_hash != raw_token
    assert raw_token not in stored.token_hash


def test_non_admin_cannot_create_invite(db_session, make_collaborator):
    collaborator = make_collaborator(name="Sem Permissao Convite")
    from app.core.security import hash_password

    non_admin = User(name="Sem Permissao", email="sem.permissao.convite@pytest.local", role="viewer", active=True, password_hash=hash_password("Qualquer123"))
    db_session.add(non_admin)
    db_session.commit()

    with _admin_client(db_session, non_admin) as client:
        response = client.post("/api/invites", json={"email": "x@exemplo.com", "collaborator_id": collaborator.id})
        assert response.status_code == 403
    app.dependency_overrides.clear()


def test_create_invite_rejects_missing_collaborator(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        response = client.post("/api/invites", json={"email": "x@exemplo.com", "collaborator_id": 999999})
        assert response.status_code == 404
    app.dependency_overrides.clear()


def test_create_invite_rejects_collaborator_already_linked(db_session, make_collaborator, admin_user):
    from app.core.security import hash_password

    collaborator = make_collaborator(name="Ja Vinculado")
    existing = User(name="Ja Tem Conta", email="ja.tem.conta@pytest.local", role="collaborator", active=True, password_hash=hash_password("Qualquer123"), collaborator_id=collaborator.id)
    db_session.add(existing)
    db_session.commit()

    with _admin_client(db_session, admin_user) as client:
        response = client.post("/api/invites", json={"email": "outro@exemplo.com", "collaborator_id": collaborator.id})
        assert response.status_code == 409
    app.dependency_overrides.clear()


def test_create_invite_rejects_duplicate_pending_invite(db_session, make_collaborator, admin_user):
    collaborator = make_collaborator(name="Convite Duplicado")

    with _admin_client(db_session, admin_user) as client:
        first = client.post("/api/invites", json={"email": "primeiro@exemplo.com", "collaborator_id": collaborator.id})
        assert first.status_code == 201
        second = client.post("/api/invites", json={"email": "segundo@exemplo.com", "collaborator_id": collaborator.id})
        assert second.status_code == 409
    app.dependency_overrides.clear()


def test_accept_invite_creates_user_with_exact_collaborator_link_and_own_password(db_session, make_collaborator, admin_user):
    collaborator = make_collaborator(name="Convite Aceito")

    with _admin_client(db_session, admin_user) as client:
        created = client.post("/api/invites", json={"email": "novo.colaborador@exemplo.com", "collaborator_id": collaborator.id, "role": "collaborator"})
        assert created.status_code == 201
        raw_token = created.json()["token"]
    app.dependency_overrides.clear()

    with _public_client(db_session) as client:
        status_response = client.get("/api/invites/accept", params={"token": raw_token})
        assert status_response.status_code == 200
        assert status_response.json()["valid"] is True
        assert status_response.json()["collaborator_name"] == "Convite Aceito"

        accept_response = client.post(
            "/api/invites/accept",
            json={"token": raw_token, "new_password": "MinhaSenhaPropria123", "confirm_password": "MinhaSenhaPropria123"},
        )
        assert accept_response.status_code == 200
        body = accept_response.json()
        assert body["access_token"]
        assert body["user"]["collaborator_id"] == collaborator.id
        # First access continua pendente de propósito - convite só resolve a senha, CPF/contato
        # ainda passam pelo onboarding já existente da Fase 1.
        assert body["user"]["portal_first_access_required"] is True
    app.dependency_overrides.clear()

    created_user = db_session.query(User).filter(User.email == "novo.colaborador@exemplo.com").one()
    assert created_user.collaborator_id == collaborator.id
    assert verify_password("MinhaSenhaPropria123", created_user.password_hash) is True
    assert created_user.must_change_password is False
    assert created_user.first_access_completed_at is None


def test_accept_invite_blocks_portal_until_first_access_completed(db_session, make_collaborator, admin_user):
    collaborator = make_collaborator(name="Bloqueio Pos Convite")

    with _admin_client(db_session, admin_user) as client:
        created = client.post("/api/invites", json={"email": "bloqueado@exemplo.com", "collaborator_id": collaborator.id})
        raw_token = created.json()["token"]
    app.dependency_overrides.clear()

    with _public_client(db_session) as client:
        accept_response = client.post(
            "/api/invites/accept",
            json={"token": raw_token, "new_password": "SenhaForte123", "confirm_password": "SenhaForte123"},
        )
        token = accept_response.json()["access_token"]
    app.dependency_overrides.clear()

    created_user = db_session.query(User).filter(User.email == "bloqueado@exemplo.com").one()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: created_user
    with TestClient(app) as client:
        blocked = client.get("/api/portal/summary")
        assert blocked.status_code == 403
    app.dependency_overrides.clear()


def test_accept_invite_rejects_password_confirmation_mismatch(db_session, make_collaborator, admin_user):
    collaborator = make_collaborator(name="Confirmacao Convite")

    with _admin_client(db_session, admin_user) as client:
        created = client.post("/api/invites", json={"email": "confirmacao@exemplo.com", "collaborator_id": collaborator.id})
        raw_token = created.json()["token"]
    app.dependency_overrides.clear()

    with _public_client(db_session) as client:
        response = client.post(
            "/api/invites/accept",
            json={"token": raw_token, "new_password": "SenhaForte123", "confirm_password": "OutraCoisa456"},
        )
        assert response.status_code == 422
    app.dependency_overrides.clear()

    assert db_session.query(User).filter(User.email == "confirmacao@exemplo.com").first() is None


def test_expired_or_used_token_cannot_be_reused(db_session, make_collaborator, admin_user):
    collaborator = make_collaborator(name="Convite Reuso")

    with _admin_client(db_session, admin_user) as client:
        created = client.post("/api/invites", json={"email": "reuso@exemplo.com", "collaborator_id": collaborator.id})
        raw_token = created.json()["token"]
    app.dependency_overrides.clear()

    with _public_client(db_session) as client:
        first_accept = client.post(
            "/api/invites/accept",
            json={"token": raw_token, "new_password": "SenhaForte123", "confirm_password": "SenhaForte123"},
        )
        assert first_accept.status_code == 200

        second_accept = client.post(
            "/api/invites/accept",
            json={"token": raw_token, "new_password": "OutraSenha456", "confirm_password": "OutraSenha456"},
        )
        assert second_accept.status_code == 409
    app.dependency_overrides.clear()


def test_expired_invite_is_rejected(db_session, make_collaborator, admin_user):
    collaborator = make_collaborator(name="Convite Expirado")

    with _admin_client(db_session, admin_user) as client:
        created = client.post("/api/invites", json={"email": "expirado@exemplo.com", "collaborator_id": collaborator.id})
        raw_token = created.json()["token"]
        invite_id = created.json()["id"]
    app.dependency_overrides.clear()

    invite = db_session.query(AccountActionToken).filter(AccountActionToken.id == invite_id).one()
    invite.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    with _public_client(db_session) as client:
        status_response = client.get("/api/invites/accept", params={"token": raw_token})
        assert status_response.json()["valid"] is False

        accept_response = client.post(
            "/api/invites/accept",
            json={"token": raw_token, "new_password": "SenhaForte123", "confirm_password": "SenhaForte123"},
        )
        assert accept_response.status_code == 409
    app.dependency_overrides.clear()


def test_listing_shows_expired_as_display_status_without_writing_it(db_session, make_collaborator, admin_user):
    """`status` na coluna só muda por ação explícita - expirado é sempre calculado na leitura (ver
    `_display_status`), pra uma consulta GET não ter efeito colateral."""
    collaborator = make_collaborator(name="Convite Listagem Expirado")

    with _admin_client(db_session, admin_user) as client:
        created = client.post("/api/invites", json={"email": "listagem.expirado@exemplo.com", "collaborator_id": collaborator.id})
        invite_id = created.json()["id"]
    app.dependency_overrides.clear()

    invite = db_session.query(AccountActionToken).filter(AccountActionToken.id == invite_id).one()
    invite.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    with _admin_client(db_session, admin_user) as client:
        listing = client.get("/api/invites")
        item = next(i for i in listing.json() if i["id"] == invite_id)
        assert item["status"] == "expired"
    app.dependency_overrides.clear()

    db_session.refresh(invite)
    assert invite.status == "pending"  # coluna real não foi alterada pela listagem


def test_admin_revokes_pending_invite_and_it_can_no_longer_be_accepted(db_session, make_collaborator, admin_user):
    collaborator = make_collaborator(name="Convite Revogado")

    with _admin_client(db_session, admin_user) as client:
        created = client.post("/api/invites", json={"email": "revogado@exemplo.com", "collaborator_id": collaborator.id})
        raw_token = created.json()["token"]
        invite_id = created.json()["id"]

        revoke_response = client.post(f"/api/invites/{invite_id}/revoke")
        assert revoke_response.status_code == 200
        assert revoke_response.json()["status"] == "revoked"

        revoke_again = client.post(f"/api/invites/{invite_id}/revoke")
        assert revoke_again.status_code == 409
    app.dependency_overrides.clear()

    with _public_client(db_session) as client:
        accept_response = client.post(
            "/api/invites/accept",
            json={"token": raw_token, "new_password": "SenhaForte123", "confirm_password": "SenhaForte123"},
        )
        assert accept_response.status_code == 409
    app.dependency_overrides.clear()


def test_audit_log_never_stores_token_or_password(db_session, make_collaborator, admin_user):
    collaborator = make_collaborator(name="Auditoria Convite")

    with _admin_client(db_session, admin_user) as client:
        created = client.post("/api/invites", json={"email": "auditoria.convite@exemplo.com", "collaborator_id": collaborator.id})
        raw_token = created.json()["token"]
        invite_id = created.json()["id"]
    app.dependency_overrides.clear()

    with _public_client(db_session) as client:
        client.post(
            "/api/invites/accept",
            json={"token": raw_token, "new_password": "SenhaSuperSecreta789", "confirm_password": "SenhaSuperSecreta789"},
        )
    app.dependency_overrides.clear()

    entries = db_session.query(AuditLog).filter(AuditLog.action.in_(["portal_invite.created", "portal_invite.accepted", "portal_invite.account_created"])).all()
    payload = "".join(str(entry.before_data) + str(entry.after_data) for entry in entries)
    assert raw_token not in payload
    assert "SenhaSuperSecreta789" not in payload

    invite = db_session.query(AccountActionToken).filter(AccountActionToken.id == invite_id).one()
    assert invite.token_hash not in payload
