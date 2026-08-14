from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core.security import hash_api_key
from app.models import User
from app.modules.ai.auth import _resolve_api_key_context, enforce_token_scope
from app.modules.ai.models import ApiKeyCredential
from app.modules.ai_governance.models import AiApiToken


def _make_ai_user(db_session, email="ai-service@pytest.local"):
    user = User(name="Servico IA", email=email, role="ai_service", active=True, password_hash="x")
    db_session.add(user)
    db_session.flush()
    return user


def _make_token(db_session, user, raw_key, *, scopes=None, expires_at=None, active=True, revoked_at=None):
    token = AiApiToken(
        user_id=user.id,
        name="Token de teste",
        scopes=scopes or [],
        key_prefix=raw_key[:12],
        key_hash=hash_api_key(raw_key),
        expires_at=expires_at,
        active=active,
        revoked_at=revoked_at,
    )
    db_session.add(token)
    db_session.flush()
    return token


def _make_legacy_credential(db_session, user, raw_key):
    credential = ApiKeyCredential(
        user_id=user.id,
        name="Chave legado",
        key_prefix=raw_key[:12],
        key_hash=hash_api_key(raw_key),
    )
    db_session.add(credential)
    db_session.flush()
    return credential


def test_new_token_resolves_with_its_scopes(db_session):
    user = _make_ai_user(db_session)
    _make_token(db_session, user, "raw-key-scoped-000000000000", scopes=["orders.read"])

    context = _resolve_api_key_context("raw-key-scoped-000000000000", db_session)

    assert context.user.id == user.id
    assert context.scopes == ["orders.read"]
    assert context.token_id is not None


def test_legacy_credential_resolves_with_unrestricted_scopes(db_session):
    user = _make_ai_user(db_session, email="legacy@pytest.local")
    _make_legacy_credential(db_session, user, "raw-key-legacy-0000000000000")

    context = _resolve_api_key_context("raw-key-legacy-0000000000000", db_session)

    assert context.user.id == user.id
    assert context.scopes is None
    assert context.token_id is None


def test_expired_token_is_rejected(db_session):
    user = _make_ai_user(db_session, email="expired@pytest.local")
    past = datetime.now(timezone.utc) - timedelta(days=1)
    _make_token(db_session, user, "raw-key-expired-000000000000", expires_at=past)

    with pytest.raises(HTTPException) as exc_info:
        _resolve_api_key_context("raw-key-expired-000000000000", db_session)
    assert exc_info.value.status_code == 401


def test_future_expiration_still_valid(db_session):
    user = _make_ai_user(db_session, email="future@pytest.local")
    future = datetime.now(timezone.utc) + timedelta(days=30)
    _make_token(db_session, user, "raw-key-future-0000000000000", scopes=["orders.detail"], expires_at=future)

    context = _resolve_api_key_context("raw-key-future-0000000000000", db_session)
    assert context.scopes == ["orders.detail"]


def test_revoked_token_is_rejected(db_session):
    user = _make_ai_user(db_session, email="revoked@pytest.local")
    _make_token(db_session, user, "raw-key-revoked-000000000000", active=False, revoked_at=datetime.now(timezone.utc))

    with pytest.raises(HTTPException) as exc_info:
        _resolve_api_key_context("raw-key-revoked-000000000000", db_session)
    assert exc_info.value.status_code == 401


def test_enforce_token_scope_allows_legacy_unrestricted():
    from app.modules.ai.auth import ApiKeyContext

    context = ApiKeyContext(user=None, scopes=None, token_id=None)
    enforce_token_scope(context, "orders.read")  # não deve levantar


def test_enforce_token_scope_denies_missing_scope():
    from app.modules.ai.auth import ApiKeyContext

    context = ApiKeyContext(user=None, scopes=["orders.detail"], token_id=1)
    with pytest.raises(HTTPException) as exc_info:
        enforce_token_scope(context, "orders.read")
    assert exc_info.value.status_code == 403


def test_enforce_token_scope_allows_matching_scope():
    from app.modules.ai.auth import ApiKeyContext

    context = ApiKeyContext(user=None, scopes=["orders.read"], token_id=1)
    enforce_token_scope(context, "orders.read")  # não deve levantar
