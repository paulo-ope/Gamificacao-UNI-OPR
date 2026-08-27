from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.modules.support import router as support_router
from app.modules.support.models import SupportOpaSavedFilter
from app.modules.support.router import (
    create_opa_saved_filter,
    delete_opa_saved_filter,
    opa_saved_filters,
)
from app.modules.support.schemas import SupportOpaSavedFilterCreate
from app.models import User


@pytest.fixture()
def other_user(db_session):
    user = User(name="Outro", email="outro@local.test", password_hash="x", role="operator", active=True)
    db_session.add(user)
    db_session.flush()
    return user


def _without_sync_permission(monkeypatch):
    """Perfis de acesso customizados podem dar `support:read` sem
    `support:sync_opa` (os perfis embutidos dão os dois juntos), e é exatamente
    esse usuário que a barreira do filtro global precisa barrar."""
    monkeypatch.setattr(support_router, "permissions_for_user", lambda user: {"support:read"})


def test_personal_filter_belongs_to_its_owner(db_session, admin_user):
    created = create_opa_saved_filter(
        SupportOpaSavedFilterCreate(name="Meu recorte", scope="personal", filters={"bot_human": "with_bot"}),
        db=db_session,
        user=admin_user,
    )

    assert created["scope"] == "personal"
    assert created["owner_id"] == admin_user.id
    assert created["filters"] == {"bot_human": "with_bot"}


def test_global_filter_has_no_owner_so_it_survives_the_author(db_session, admin_user):
    """`owner_id` fica NULL de propósito: a FK é `ondelete=CASCADE`, então um
    recorte oficial da operação sumiria junto com o autor se ficasse amarrado
    a ele."""
    created = create_opa_saved_filter(
        SupportOpaSavedFilterCreate(name="Oficial", scope="global", filters={}),
        db=db_session,
        user=admin_user,
    )

    assert created["scope"] == "global"
    assert created["owner_id"] is None


def test_user_without_sync_permission_cannot_publish_global_filter(db_session, admin_user, monkeypatch):
    _without_sync_permission(monkeypatch)

    with pytest.raises(HTTPException) as excinfo:
        create_opa_saved_filter(
            SupportOpaSavedFilterCreate(name="Tentativa", scope="global", filters={}),
            db=db_session,
            user=admin_user,
        )
    assert excinfo.value.status_code == 403

    # O mesmo usuário continua podendo criar os próprios recortes pessoais.
    created = create_opa_saved_filter(
        SupportOpaSavedFilterCreate(name="Pessoal", scope="personal", filters={}),
        db=db_session,
        user=admin_user,
    )
    assert created["scope"] == "personal"


def test_listing_never_leaks_someone_elses_personal_filter(db_session, admin_user, other_user):
    db_session.add_all(
        [
            SupportOpaSavedFilter(name="Do admin", scope="personal", filters_json={}, owner_id=admin_user.id),
            SupportOpaSavedFilter(name="Do outro", scope="personal", filters_json={}, owner_id=other_user.id),
            SupportOpaSavedFilter(name="Da operação", scope="global", filters_json={}, owner_id=None),
        ]
    )
    db_session.flush()

    visiveis = {item["name"] for item in opa_saved_filters(db=db_session, user=admin_user)}

    assert visiveis == {"Do admin", "Da operação"}
    assert "Do outro" not in visiveis


def test_deleting_someone_elses_personal_filter_is_not_found(db_session, admin_user, other_user):
    """404 em vez de 403 de propósito: um filtro pessoal de outra pessoa não
    deve nem confirmar que existe."""
    alheio = SupportOpaSavedFilter(name="Do outro", scope="personal", filters_json={}, owner_id=other_user.id)
    db_session.add(alheio)
    db_session.flush()

    with pytest.raises(HTTPException) as excinfo:
        delete_opa_saved_filter(alheio.id, db=db_session, user=admin_user)
    assert excinfo.value.status_code == 404
    assert db_session.get(SupportOpaSavedFilter, alheio.id) is not None


def test_user_without_sync_permission_cannot_delete_global_filter(db_session, admin_user, monkeypatch):
    oficial = SupportOpaSavedFilter(name="Da operação", scope="global", filters_json={}, owner_id=None)
    db_session.add(oficial)
    db_session.flush()
    _without_sync_permission(monkeypatch)

    with pytest.raises(HTTPException) as excinfo:
        delete_opa_saved_filter(oficial.id, db=db_session, user=admin_user)
    assert excinfo.value.status_code == 403
    assert db_session.get(SupportOpaSavedFilter, oficial.id) is not None
