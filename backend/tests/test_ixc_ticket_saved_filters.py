"""Item 10 do plano de evolução analítica do Atendimento IXC (2026-09-17): visão salva SEMPRE
pessoal (ver docstring de `SupportIxcTicketSavedFilter`), com no máximo uma marcada como
`is_default` por dono ao mesmo tempo."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models import User
from app.modules.support.models import SupportIxcTicketSavedFilter
from app.modules.support.router import (
    create_ixc_ticket_saved_filter,
    delete_ixc_ticket_saved_filter,
    ixc_ticket_saved_filters,
    update_ixc_ticket_saved_filter,
)
from app.modules.support.schemas import (
    SupportIxcTicketSavedFilterCreate,
    SupportIxcTicketSavedFilterUpdate,
    SupportIxcTicketSavedFilterValues,
)


@pytest.fixture()
def other_user(db_session):
    user = User(name="Outro", email="outro@local.test", password_hash="x", role="operator", active=True)
    db_session.add(user)
    db_session.flush()
    return user


def test_saved_filter_belongs_to_its_owner(db_session, admin_user):
    created = create_ixc_ticket_saved_filter(
        SupportIxcTicketSavedFilterCreate(name="Internet", filters=SupportIxcTicketSavedFilterValues(subject_ids=["8", "9"])),
        db=db_session,
        user=admin_user,
    )

    assert created["name"] == "Internet"
    assert created["filters"] == {"subject_ids": ["8", "9"], "sector_ids": []}
    assert created["is_default"] is False


def test_listing_never_leaks_someone_elses_saved_filter(db_session, admin_user, other_user):
    db_session.add_all(
        [
            SupportIxcTicketSavedFilter(name="Do admin", filters_json={}, owner_id=admin_user.id),
            SupportIxcTicketSavedFilter(name="Do outro", filters_json={}, owner_id=other_user.id),
        ]
    )
    db_session.flush()

    visiveis = {item["name"] for item in ixc_ticket_saved_filters(db=db_session, user=admin_user)}

    assert visiveis == {"Do admin"}


def test_deleting_someone_elses_saved_filter_is_not_found(db_session, admin_user, other_user):
    alheio = SupportIxcTicketSavedFilter(name="Do outro", filters_json={}, owner_id=other_user.id)
    db_session.add(alheio)
    db_session.flush()

    with pytest.raises(HTTPException) as excinfo:
        delete_ixc_ticket_saved_filter(alheio.id, db=db_session, user=admin_user)
    assert excinfo.value.status_code == 404
    assert db_session.get(SupportIxcTicketSavedFilter, alheio.id) is not None


def test_creating_a_new_default_unmarks_the_previous_one(db_session, admin_user):
    first = create_ixc_ticket_saved_filter(
        SupportIxcTicketSavedFilterCreate(name="A", filters=SupportIxcTicketSavedFilterValues(), is_default=True),
        db=db_session,
        user=admin_user,
    )
    second = create_ixc_ticket_saved_filter(
        SupportIxcTicketSavedFilterCreate(name="B", filters=SupportIxcTicketSavedFilterValues(), is_default=True),
        db=db_session,
        user=admin_user,
    )

    assert second["is_default"] is True
    assert db_session.get(SupportIxcTicketSavedFilter, first["id"]).is_default is False


def test_setting_default_via_update_unmarks_the_previous_one(db_session, admin_user):
    first = create_ixc_ticket_saved_filter(
        SupportIxcTicketSavedFilterCreate(name="A", filters=SupportIxcTicketSavedFilterValues(), is_default=True),
        db=db_session,
        user=admin_user,
    )
    second = create_ixc_ticket_saved_filter(
        SupportIxcTicketSavedFilterCreate(name="B", filters=SupportIxcTicketSavedFilterValues()),
        db=db_session,
        user=admin_user,
    )

    updated = update_ixc_ticket_saved_filter(
        second["id"], SupportIxcTicketSavedFilterUpdate(is_default=True), db=db_session, user=admin_user
    )

    assert updated["is_default"] is True
    assert db_session.get(SupportIxcTicketSavedFilter, first["id"]).is_default is False


def test_a_users_default_does_not_affect_another_users_default(db_session, admin_user, other_user):
    create_ixc_ticket_saved_filter(
        SupportIxcTicketSavedFilterCreate(name="Do admin", filters=SupportIxcTicketSavedFilterValues(), is_default=True),
        db=db_session,
        user=admin_user,
    )
    create_ixc_ticket_saved_filter(
        SupportIxcTicketSavedFilterCreate(name="Do outro", filters=SupportIxcTicketSavedFilterValues(), is_default=True),
        db=db_session,
        user=other_user,
    )

    admin_default = db_session.query(SupportIxcTicketSavedFilter).filter_by(owner_id=admin_user.id).one()
    other_default = db_session.query(SupportIxcTicketSavedFilter).filter_by(owner_id=other_user.id).one()
    assert admin_default.is_default is True
    assert other_default.is_default is True


def test_updating_someone_elses_saved_filter_is_not_found(db_session, admin_user, other_user):
    alheio = SupportIxcTicketSavedFilter(name="Do outro", filters_json={}, owner_id=other_user.id)
    db_session.add(alheio)
    db_session.flush()

    with pytest.raises(HTTPException) as excinfo:
        update_ixc_ticket_saved_filter(alheio.id, SupportIxcTicketSavedFilterUpdate(is_default=True), db=db_session, user=admin_user)
    assert excinfo.value.status_code == 404
