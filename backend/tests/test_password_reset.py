"""Esqueci minha senha por código de 6 dígitos enviado por e-mail (evolução da Fase 2E, ver
docs/portal-ciclo-vida-conta-colaborador.md seção 7). Rotas públicas: `POST /auth/forgot-password` e
`POST /auth/reset-password`. O envio real de e-mail é sempre substituído por um coletor em memória.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.routes import auth as auth_routes
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.main import app
from app.models import AccountActionToken, AuditLog, User
from app.services import password_reset
from app.services.email_sender import OutgoingEmail

OLD_PASSWORD = "SenhaAntiga123"
NEW_PASSWORD = "SenhaNova456"
EMAIL = "recupera@souuni.com"


@pytest.fixture(autouse=True)
def _reset_ip_limiters():
    auth_routes._forgot_limiter.reset()
    auth_routes._reset_limiter.reset()
    yield
    auth_routes._forgot_limiter.reset()
    auth_routes._reset_limiter.reset()


@pytest.fixture()
def sent_emails(monkeypatch) -> list[OutgoingEmail]:
    sent: list[OutgoingEmail] = []
    monkeypatch.setattr(password_reset, "send_email", lambda message: sent.append(message) or True)
    return sent


@contextmanager
def _client(db_session):
    """TestClient SEM `with` interno: não dispara o lifespan do app (schedulers/seed no engine
    global), que não faz parte do que estas rotas públicas exercitam."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _make_user(db_session, **overrides) -> User:
    defaults = dict(
        name="Maria Recupera",
        email=EMAIL,
        role="collaborator",
        active=True,
        password_hash=hash_password(OLD_PASSWORD),
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    db_session.commit()
    return user


def _code_from(sent: list[OutgoingEmail]) -> str:
    assert len(sent) == 1
    marker = "Seu código de verificação é: "
    line = next(line for line in sent[0].text_body.splitlines() if line.startswith(marker))
    return line.removeprefix(marker).strip()


def _request_code(client: TestClient, sent: list[OutgoingEmail], email: str = EMAIL) -> str:
    response = client.post("/api/auth/forgot-password", json={"email": email})
    assert response.status_code == 202
    return _code_from(sent)


def _reset(client: TestClient, code: str, *, email: str = EMAIL, password: str = NEW_PASSWORD):
    return client.post(
        "/api/auth/reset-password",
        json={"email": email, "code": code, "new_password": password, "confirm_password": password},
    )


def test_forgot_password_sends_six_digit_code_and_reset_changes_password(db_session, sent_emails):
    user = _make_user(db_session, must_change_password=False, first_access_completed_at=None)
    with _client(db_session) as client:
        code = _request_code(client, sent_emails)
        assert len(code) == 6 and code.isdigit()
        assert sent_emails[0].to == EMAIL
        assert code in (sent_emails[0].html_body or "")

        response = _reset(client, code)
        assert response.status_code == 204

        db_session.refresh(user)
        assert verify_password(NEW_PASSWORD, user.password_hash)
        assert not verify_password(OLD_PASSWORD, user.password_hash)
        assert user.password_changed_at is not None
        # Recuperação de senha não é reconfirmação de identidade (doc da Fase 2, seção 7).
        assert user.must_change_password is False
        assert user.first_access_completed_at is None

        login = client.post("/api/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD})
        assert login.status_code == 200


def test_forgot_password_response_is_identical_for_unknown_email(db_session, sent_emails):
    _make_user(db_session)
    with _client(db_session) as client:
        known = client.post("/api/auth/forgot-password", json={"email": EMAIL})
        unknown = client.post("/api/auth/forgot-password", json={"email": "ninguem@souuni.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    # E-mail só foi enviado para a conta que existe.
    assert len(sent_emails) == 1


def test_forgot_password_ignores_inactive_account(db_session, sent_emails):
    _make_user(db_session, active=False)
    with _client(db_session) as client:
        response = client.post("/api/auth/forgot-password", json={"email": EMAIL})
    assert response.status_code == 202
    assert sent_emails == []


def test_forgot_password_normalizes_email_case_and_spaces(db_session, sent_emails):
    _make_user(db_session)
    with _client(db_session) as client:
        response = client.post("/api/auth/forgot-password", json={"email": "  Recupera@SouUni.com "})
    assert response.status_code == 202
    assert len(sent_emails) == 1


def test_code_is_stored_only_as_salted_hash_and_never_audited(db_session, sent_emails):
    _make_user(db_session)
    with _client(db_session) as client:
        code = _request_code(client, sent_emails)

    token = db_session.query(AccountActionToken).one()
    assert token.purpose == "password_reset"
    assert code not in token.token_hash
    assert token.attempts == 0
    expires_at = token.expires_at if token.expires_at.tzinfo else token.expires_at.replace(tzinfo=timezone.utc)
    assert expires_at <= datetime.now(timezone.utc) + timedelta(minutes=password_reset.CODE_TTL_MINUTES)

    for entry in db_session.query(AuditLog).all():
        assert code not in str(entry.before_data) + str(entry.after_data)


def test_wrong_code_is_rejected_and_counts_attempts_until_revoked(db_session, sent_emails):
    user = _make_user(db_session)
    with _client(db_session) as client:
        code = _request_code(client, sent_emails)
        wrong = "000000" if code != "000000" else "111111"

        for _ in range(password_reset.MAX_CODE_ATTEMPTS):
            response = _reset(client, wrong)
            assert response.status_code == 400
            assert response.json()["detail"] == password_reset.INVALID_CODE_MESSAGE

        # Depois do limite, nem o código CERTO funciona mais - força bruta de 1 milhão de
        # combinações precisa de pedido novo a cada poucas tentativas.
        assert _reset(client, code).status_code == 400

    db_session.refresh(user)
    assert verify_password(OLD_PASSWORD, user.password_hash)
    token = db_session.query(AccountActionToken).one()
    assert token.status == "revoked"


def test_code_is_single_use(db_session, sent_emails):
    _make_user(db_session)
    with _client(db_session) as client:
        code = _request_code(client, sent_emails)
        assert _reset(client, code).status_code == 204
        assert _reset(client, code, password="OutraSenha789").status_code == 400


def test_expired_code_is_rejected(db_session, sent_emails):
    user = _make_user(db_session)
    with _client(db_session) as client:
        code = _request_code(client, sent_emails)
        token = db_session.query(AccountActionToken).one()
        token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db_session.commit()
        response = _reset(client, code)

    assert response.status_code == 400
    db_session.refresh(user)
    assert verify_password(OLD_PASSWORD, user.password_hash)


def test_invalid_code_and_unknown_email_share_the_same_error(db_session, sent_emails):
    _make_user(db_session)
    with _client(db_session) as client:
        code = _request_code(client, sent_emails)
        wrong = "000000" if code != "000000" else "111111"
        known = _reset(client, wrong)
        unknown = _reset(client, "123456", email="ninguem@souuni.com")
    assert known.status_code == unknown.status_code == 400
    assert known.json() == unknown.json()


def test_new_request_revokes_previous_code(db_session, sent_emails):
    _make_user(db_session)
    with _client(db_session) as client:
        first = _request_code(client, sent_emails)
        # Libera o intervalo mínimo entre pedidos sem esperar de verdade.
        token = db_session.query(AccountActionToken).one()
        token.created_at = datetime.now(timezone.utc) - timedelta(seconds=password_reset.RESEND_COOLDOWN_SECONDS + 5)
        db_session.commit()
        sent_emails.clear()
        second = _request_code(client, sent_emails)

        statuses = sorted(t.status for t in db_session.query(AccountActionToken).all())
        assert statuses == ["pending", "revoked"]
        if first != second:
            assert _reset(client, first).status_code == 400
        assert _reset(client, second).status_code == 204


def test_resend_cooldown_blocks_immediate_second_request_silently(db_session, sent_emails):
    _make_user(db_session)
    with _client(db_session) as client:
        assert client.post("/api/auth/forgot-password", json={"email": EMAIL}).status_code == 202
        assert client.post("/api/auth/forgot-password", json={"email": EMAIL}).status_code == 202
    assert len(sent_emails) == 1
    assert db_session.query(AccountActionToken).count() == 1


def test_hourly_request_limit_per_email(db_session, sent_emails):
    user = _make_user(db_session)
    now = datetime.now(timezone.utc)
    for minutes_ago in range(2, 2 + password_reset.MAX_REQUESTS_PER_HOUR):
        db_session.add(
            AccountActionToken(
                purpose="password_reset",
                user_id=user.id,
                email=user.email,
                token_hash=f"x${minutes_ago}",
                status="revoked",
                expires_at=now,
                created_at=now - timedelta(minutes=minutes_ago),
            )
        )
    db_session.commit()
    with _client(db_session) as client:
        assert client.post("/api/auth/forgot-password", json={"email": EMAIL}).status_code == 202
    assert sent_emails == []


def test_reset_rejects_mismatched_confirmation_and_malformed_code(db_session, sent_emails):
    _make_user(db_session)
    with _client(db_session) as client:
        code = _request_code(client, sent_emails)
        mismatch = client.post(
            "/api/auth/reset-password",
            json={"email": EMAIL, "code": code, "new_password": NEW_PASSWORD, "confirm_password": "Diferente123"},
        )
        short_code = _reset(client, "12345")
        letters = _reset(client, "12345a")
        short_password = client.post(
            "/api/auth/reset-password",
            json={"email": EMAIL, "code": code, "new_password": "curta", "confirm_password": "curta"},
        )
    assert mismatch.status_code == 422
    assert short_code.status_code == 422
    assert letters.status_code == 422
    assert short_password.status_code == 422


def test_reset_audit_has_no_password_or_code(db_session, sent_emails):
    user = _make_user(db_session)
    with _client(db_session) as client:
        code = _request_code(client, sent_emails)
        assert _reset(client, code).status_code == 204

    actions = [entry.action for entry in db_session.query(AuditLog).filter(AuditLog.entity_id == str(user.id)).all()]
    assert "password_reset.requested" in actions
    assert "password_reset.completed" in actions
    blob = " ".join(str(entry.before_data) + str(entry.after_data) for entry in db_session.query(AuditLog).all())
    assert NEW_PASSWORD not in blob and OLD_PASSWORD not in blob and code not in blob


def test_ip_rate_limit_on_forgot_password(db_session, sent_emails):
    with _client(db_session) as client:
        statuses = [client.post("/api/auth/forgot-password", json={"email": f"x{i}@souuni.com"}).status_code for i in range(11)]
    assert statuses[:10] == [202] * 10
    assert statuses[10] == 429


def test_send_email_is_a_noop_when_disabled(monkeypatch):
    from app.core.config import get_settings
    from app.services import email_sender

    monkeypatch.setenv("EMAIL_ENABLED", "false")
    get_settings.cache_clear()
    try:
        assert email_sender.send_email(OutgoingEmail(to="a@souuni.com", subject="s", text_body="b")) is False
    finally:
        get_settings.cache_clear()


def test_send_email_swallows_smtp_failure(monkeypatch):
    from app.core.config import get_settings
    from app.services import email_sender

    monkeypatch.setenv("EMAIL_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.invalido.local")
    get_settings.cache_clear()

    def boom(*args, **kwargs):
        raise OSError("sem rede")

    monkeypatch.setattr(email_sender.smtplib, "SMTP", boom)
    try:
        assert email_sender.send_email(OutgoingEmail(to="a@souuni.com", subject="s", text_body="b")) is False
    finally:
        get_settings.cache_clear()


def test_accepted_reset_code_is_marked_accepted_even_without_autoflush(db_session, sent_emails):
    """Regressão: com a sessão do app (sem autoflush), o código aceito terminava como "revoked"."""
    _make_user(db_session)
    db_session.autoflush = False
    with _client(db_session) as client:
        code = _request_code(client, sent_emails)
        assert _reset(client, code).status_code == 204
    assert db_session.query(AccountActionToken).one().status == "accepted"
