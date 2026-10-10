"""Verificação de e-mail na solicitação de acesso (Fase 2D, 2026-10-10): a pessoa recebe um código de
6 dígitos na caixa informada e precisa confirmá-lo antes de o admin poder aprovar. Reenviar a
solicitação enquanto pendente zera a verificação (fecha o achado de sobrescrita por quem só sabe o CPF).
O envio real de e-mail é sempre substituído por um coletor em memória.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.routes import access_requests as access_requests_module
from app.core.security import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import AccountActionToken, AuditLog, PortalAccessRequest, User
from app.services import portal_access_requests as service
from app.services.email_sender import OutgoingEmail
from app.services.ixc_client import IxcPage
from app.services.verification_codes import MAX_CODE_ATTEMPTS, RESEND_COOLDOWN_SECONDS

VALID_CPF = "529.982.247-25"
VALID_CPF_DIGITS = "52998224725"
OTHER_CPF = "111.444.777-35"
PASSWORD = "SenhaForte123"
EMAIL = "verifica@souuni.com"


class FakeFuncionariosClient:
    def __init__(self, records):
        self.records = records

    def list(self, table, *, grid_param=None, page=1, rp=100, sortname=None, sortorder="asc"):
        cpf_filter = next((item["P"] for item in (grid_param or []) if item["TB"] == "funcionarios.cpf_cnpj"), None)
        matches = [r for r in self.records if r.get("cpf_cnpj") == cpf_filter]
        return IxcPage(records=matches, total=len(matches), page=page)


def _funcionario(cpf=VALID_CPF_DIGITS, name="Fulano Verificado"):
    return {"id": "1", "funcionario": name, "cpf_cnpj": cpf, "email": "x@uni.com.br", "fone_celular": "69999990001", "ativo": "S"}


@pytest.fixture(autouse=True)
def _reset_limiters():
    for limiter in (
        access_requests_module._verify_limiter,
        access_requests_module._resend_limiter,
    ):
        limiter.reset()
    access_requests_module._submit_attempts.clear()
    access_requests_module._lookup_attempts.clear()
    yield
    access_requests_module._verify_limiter.reset()
    access_requests_module._resend_limiter.reset()
    access_requests_module._submit_attempts.clear()


@pytest.fixture()
def sent_emails(monkeypatch) -> list[OutgoingEmail]:
    sent: list[OutgoingEmail] = []
    monkeypatch.setattr(service, "send_email", lambda message: sent.append(message) or True)
    return sent


@contextmanager
def _public(db_session, monkeypatch, records=None):
    """TestClient SEM `with` interno: não dispara o lifespan do app (schedulers/seed no engine global)."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(access_requests_module, "get_ixc_client", lambda: FakeFuncionariosClient(records if records is not None else [_funcionario()]))
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@contextmanager
def _admin(db_session, admin_user):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


def _code_from(email: OutgoingEmail) -> str:
    marker = "Seu código de verificação é: "
    line = next(line for line in email.text_body.splitlines() if line.startswith(marker))
    return line.removeprefix(marker).strip()


def _submit(client, *, cpf=VALID_CPF, email=EMAIL):
    return client.post(
        "/api/access-requests",
        json={"cpf": cpf, "email": email, "new_password": PASSWORD, "confirm_password": PASSWORD},
    )


def _verify(client, code, *, cpf=VALID_CPF, email=EMAIL):
    return client.post("/api/access-requests/verify-email", json={"cpf": cpf, "email": email, "code": code})


def _wrong(code: str) -> str:
    return "000000" if code != "000000" else "111111"


def _free_cooldown(db_session) -> None:
    for token in db_session.query(AccountActionToken).all():
        token.created_at = datetime.now(timezone.utc) - timedelta(seconds=RESEND_COOLDOWN_SECONDS + 5)
    db_session.commit()


def test_submit_sends_code_and_request_starts_unverified(db_session, monkeypatch, sent_emails):
    with _public(db_session, monkeypatch) as client:
        response = _submit(client)
    assert response.status_code == 201
    assert response.json() == {"received": True}

    assert len(sent_emails) == 1
    assert sent_emails[0].to == EMAIL
    code = _code_from(sent_emails[0])
    assert len(code) == 6 and code.isdigit()

    request_row = db_session.query(PortalAccessRequest).one()
    assert request_row.email_verified_at is None
    token = db_session.query(AccountActionToken).one()
    assert token.purpose == "email_verification"
    assert token.access_request_id == request_row.id
    assert code not in token.token_hash


def test_verify_email_marks_request_verified_and_allows_approval(db_session, make_collaborator, admin_user, monkeypatch, sent_emails):
    collaborator = make_collaborator(name="Verificado E Aprovado")
    with _public(db_session, monkeypatch) as client:
        _submit(client)
        code = _code_from(sent_emails[0])
        response = _verify(client, code)
    assert response.status_code == 200
    assert response.json() == {"verified": True}

    request_row = db_session.query(PortalAccessRequest).one()
    assert request_row.email_verified_at is not None

    with _admin(db_session, admin_user) as client:
        listing = client.get("/api/access-requests").json()
        assert next(i for i in listing if i["id"] == request_row.id)["email_verified"] is True
        approve = client.post(f"/api/access-requests/{request_row.id}/approve", json={"collaborator_id": collaborator.id})
        assert approve.status_code == 200
    assert db_session.query(User).filter(User.email == EMAIL).one().collaborator_id == collaborator.id


def test_admin_cannot_approve_unverified_request(db_session, make_collaborator, admin_user, monkeypatch, sent_emails):
    collaborator = make_collaborator(name="Nao Verificado")
    with _public(db_session, monkeypatch) as client:
        _submit(client)
    request_row = db_session.query(PortalAccessRequest).one()

    with _admin(db_session, admin_user) as client:
        listing = client.get("/api/access-requests").json()
        assert next(i for i in listing if i["id"] == request_row.id)["email_verified"] is False
        response = client.post(f"/api/access-requests/{request_row.id}/approve", json={"collaborator_id": collaborator.id})
    assert response.status_code == 409
    assert "verificado" in response.json()["detail"]
    assert db_session.query(User).filter(User.email == EMAIL).first() is None
    db_session.refresh(request_row)
    assert request_row.status == "pending"


def test_legacy_pending_request_without_verification_stays_blocked(db_session, make_collaborator, admin_user):
    """Decisão do usuário (2026-10-10): pedidos anteriores à regra exigem verificação, sem exceção do admin."""
    from app.core.security import hash_password

    collaborator = make_collaborator(name="Pedido Antigo")
    legacy = PortalAccessRequest(
        name="Pedido Antigo",
        cpf=VALID_CPF_DIGITS,
        phone="(69) 99999-0001",
        email="antigo@souuni.com",
        password_hash=hash_password(PASSWORD),
        status="pending",
    )
    db_session.add(legacy)
    db_session.commit()

    with _admin(db_session, admin_user) as client:
        response = client.post(f"/api/access-requests/{legacy.id}/approve", json={"collaborator_id": collaborator.id})
    assert response.status_code == 409


def test_wrong_code_counts_attempts_and_is_revoked_at_the_limit(db_session, monkeypatch, sent_emails):
    with _public(db_session, monkeypatch) as client:
        _submit(client)
        code = _code_from(sent_emails[0])
        for _ in range(MAX_CODE_ATTEMPTS):
            response = _verify(client, _wrong(code))
            assert response.status_code == 400
            assert response.json()["detail"] == service.INVALID_CODE_MESSAGE
        # Depois do limite, nem o código CERTO funciona mais.
        assert _verify(client, code).status_code == 400

    assert db_session.query(PortalAccessRequest).one().email_verified_at is None
    assert db_session.query(AccountActionToken).one().status == "revoked"


def test_verify_failures_are_indistinguishable(db_session, monkeypatch, sent_emails):
    with _public(db_session, monkeypatch) as client:
        _submit(client)
        code = _code_from(sent_emails[0])
        wrong_code = _verify(client, _wrong(code))
        unknown_cpf = _verify(client, code, cpf=OTHER_CPF)
        other_email = _verify(client, code, email="outro@souuni.com")
    assert wrong_code.status_code == unknown_cpf.status_code == other_email.status_code == 400
    assert wrong_code.json() == unknown_cpf.json() == other_email.json()
    assert db_session.query(PortalAccessRequest).one().email_verified_at is None


def test_code_is_single_use_and_expires(db_session, monkeypatch, sent_emails):
    with _public(db_session, monkeypatch) as client:
        _submit(client)
        code = _code_from(sent_emails[0])
        token = db_session.query(AccountActionToken).one()
        token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db_session.commit()
        assert _verify(client, code).status_code == 400
        assert db_session.query(PortalAccessRequest).one().email_verified_at is None

    with _public(db_session, monkeypatch) as client:
        db_session.query(PortalAccessRequest).delete()
        db_session.query(AccountActionToken).delete()
        db_session.commit()
        sent_emails.clear()
        _submit(client)
        fresh = _code_from(sent_emails[0])
        assert _verify(client, fresh).status_code == 200
        assert _verify(client, fresh).status_code == 400


def test_resubmitting_resets_verification_and_invalidates_previous_code(db_session, make_collaborator, admin_user, monkeypatch, sent_emails):
    """O achado de segurança: quem só sabe o CPF reenvia a solicitação com outro e-mail/senha. A
    verificação é zerada e o código antigo deixa de valer - a solicitação não fica aprovável."""
    collaborator = make_collaborator(name="Sequestro")
    with _public(db_session, monkeypatch) as client:
        _submit(client)
        original_code = _code_from(sent_emails[0])
        assert _verify(client, original_code).status_code == 200
        assert db_session.query(PortalAccessRequest).one().email_verified_at is not None

        _free_cooldown(db_session)
        sent_emails.clear()
        hijack = _submit(client, email="intruso@souuni.com")
        assert hijack.status_code == 201
        assert hijack.json() == {"received": True}

    request_row = db_session.query(PortalAccessRequest).one()
    assert request_row.email == "intruso@souuni.com"
    assert request_row.email_verified_at is None
    # O novo código foi para o e-mail NOVO, não para o dono original.
    assert [m.to for m in sent_emails] == ["intruso@souuni.com"]

    with _public(db_session, monkeypatch) as client:
        assert _verify(client, original_code, email="intruso@souuni.com").status_code == 400

    with _admin(db_session, admin_user) as client:
        response = client.post(f"/api/access-requests/{request_row.id}/approve", json={"collaborator_id": collaborator.id})
    assert response.status_code == 409


def test_resend_respects_cooldown_and_replaces_previous_code(db_session, monkeypatch, sent_emails):
    with _public(db_session, monkeypatch) as client:
        _submit(client)
        first = _code_from(sent_emails[0])

        early = client.post("/api/access-requests/resend-code", json={"cpf": VALID_CPF, "email": EMAIL})
        assert early.status_code == 202
        assert len(sent_emails) == 1  # dentro do intervalo mínimo: nada novo é enviado

        _free_cooldown(db_session)
        later = client.post("/api/access-requests/resend-code", json={"cpf": VALID_CPF, "email": EMAIL})
        assert later.status_code == 202
        assert len(sent_emails) == 2
        second = _code_from(sent_emails[1])

        if first != second:
            assert _verify(client, first).status_code == 400
        assert _verify(client, second).status_code == 200


def test_resend_response_is_identical_for_unknown_request(db_session, monkeypatch, sent_emails):
    with _public(db_session, monkeypatch) as client:
        _submit(client)
        known = client.post("/api/access-requests/resend-code", json={"cpf": VALID_CPF, "email": EMAIL})
        unknown = client.post("/api/access-requests/resend-code", json={"cpf": OTHER_CPF, "email": "ninguem@souuni.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(sent_emails) == 1


def test_resend_does_nothing_once_verified(db_session, monkeypatch, sent_emails):
    with _public(db_session, monkeypatch) as client:
        _submit(client)
        assert _verify(client, _code_from(sent_emails[0])).status_code == 200
        _free_cooldown(db_session)
        sent_emails.clear()
        response = client.post("/api/access-requests/resend-code", json={"cpf": VALID_CPF, "email": EMAIL})
    assert response.status_code == 202
    assert sent_emails == []


def test_hourly_limit_stops_new_codes(db_session, monkeypatch, sent_emails):
    with _public(db_session, monkeypatch) as client:
        _submit(client)
        request_row = db_session.query(PortalAccessRequest).one()
        now = datetime.now(timezone.utc)
        for minutes_ago in range(2, 6):
            db_session.add(
                AccountActionToken(
                    purpose="email_verification",
                    access_request_id=request_row.id,
                    email=EMAIL,
                    token_hash=f"x${minutes_ago}",
                    status="revoked",
                    expires_at=now,
                    created_at=now - timedelta(minutes=minutes_ago),
                )
            )
        db_session.commit()
        sent_emails.clear()
        response = client.post("/api/access-requests/resend-code", json={"cpf": VALID_CPF, "email": EMAIL})
    assert response.status_code == 202
    assert sent_emails == []


def test_audit_never_stores_code_or_full_cpf(db_session, monkeypatch, sent_emails):
    with _public(db_session, monkeypatch) as client:
        _submit(client)
        code = _code_from(sent_emails[0])
        assert _verify(client, code).status_code == 200

    actions = [entry.action for entry in db_session.query(AuditLog).all()]
    assert "portal_access_request.email_verified" in actions
    blob = " ".join(str(entry.before_data) + str(entry.after_data) for entry in db_session.query(AuditLog).all())
    assert code not in blob
    assert VALID_CPF_DIGITS not in blob
    assert PASSWORD not in blob


def test_verify_rejects_malformed_code(db_session, monkeypatch, sent_emails):
    with _public(db_session, monkeypatch) as client:
        _submit(client)
        assert _verify(client, "12345").status_code == 422
        assert _verify(client, "12345a").status_code == 422


def test_ip_rate_limit_on_verify(db_session, monkeypatch, sent_emails):
    with _public(db_session, monkeypatch) as client:
        statuses = [_verify(client, "123456", cpf=OTHER_CPF).status_code for _ in range(16)]
    assert statuses[:15] == [400] * 15
    assert statuses[15] == 429


def test_accepted_code_is_marked_accepted_even_without_autoflush(db_session, monkeypatch, sent_emails):
    """A sessão do app não faz autoflush; o status final do código tem que ser "accepted", não
    "revoked" (regressão: revogar os pendentes depois de aceitar sobrescrevia o status)."""
    db_session.autoflush = False
    with _public(db_session, monkeypatch) as client:
        _submit(client)
        assert _verify(client, _code_from(sent_emails[0])).status_code == 200
    assert db_session.query(AccountActionToken).one().status == "accepted"
