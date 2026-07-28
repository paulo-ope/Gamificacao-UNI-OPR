"""Regression tests for backend/app/services/upvalue_importer.py."""
from app.services.upvalue_importer import get_or_create_collaborator


def test_reactivating_a_collaborator_by_name_does_not_reset_is_registered(db_session, make_collaborator):
    """Regression (audit finding B3): matching by name to reactivate a deactivated-but-still-
    registered collaborator (e.g. temporary leave, not a real soft-delete) must not silently
    wipe their registration - see the same regression test in test_operations_sync.py for the
    ixc_employee_id-matching path."""
    collaborator = make_collaborator(name="Tecnico De Licenca", registered=True)
    collaborator.active = False
    db_session.flush()

    resolved, created = get_or_create_collaborator(
        db_session, "Tecnico De Licenca", collaborator.regional, collaborators_cache=[collaborator]
    )

    assert created is False
    assert resolved.active is True
    assert resolved.is_registered is True, "reativar nao deveria derrubar um cadastro que ja existia"
