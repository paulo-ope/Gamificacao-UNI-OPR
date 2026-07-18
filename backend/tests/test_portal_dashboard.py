"""Regression test for services/portal_dashboard.py's _resolve_score - the identity resolution
used by every /portal/* route. Before this fix, an admin/operator/viewer user with no name/e-mail
match against any collaborator fell back to `rows[0]` (the ranking's first place), leaking that
collaborator's score to an unrelated user. Now that users can be linked directly via
`users.collaborator_id`, that link must win, and no match at all must return None instead of
leaking data."""

from app.models import User
from app.services.portal_dashboard import _resolve_score

ROWS = [
    {"collaborator_id": 1, "collaborator_name": "Ana Souza", "final_points": 100},
    {"collaborator_id": 2, "collaborator_name": "Bruno Lima", "final_points": 80},
]


def _user(**overrides):
    defaults = dict(id=1, name="Sem Match", email="semmatch@pytest.local", role="viewer", active=True, password_hash="x", collaborator_id=None)
    defaults.update(overrides)
    return User(**defaults)


def test_resolve_score_prefers_direct_collaborator_link():
    user = _user(name="Nome Qualquer", email="qualquer@pytest.local", collaborator_id=2)
    result = _resolve_score(user, ROWS)
    assert result is not None
    assert result["collaborator_id"] == 2


def test_resolve_score_falls_back_to_name_match_without_link():
    user = _user(name="Ana Souza", collaborator_id=None)
    result = _resolve_score(user, ROWS)
    assert result is not None
    assert result["collaborator_id"] == 1


def test_resolve_score_returns_none_without_link_or_match_admin():
    """Security regression: an admin with no link and no name/e-mail match must NOT see rows[0]."""
    user = _user(role="admin", name="Admin Sem Colaborador", email="admin@pytest.local", collaborator_id=None)
    result = _resolve_score(user, ROWS)
    assert result is None


def test_resolve_score_returns_none_without_link_or_match_viewer():
    user = _user(role="viewer", name="Viewer Sem Colaborador", email="viewer@pytest.local", collaborator_id=None)
    result = _resolve_score(user, ROWS)
    assert result is None
