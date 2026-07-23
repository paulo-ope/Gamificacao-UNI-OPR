"""Regression test for services/portal_dashboard.py's _resolve_score - the identity resolution
used by every /portal/* route. Before this fix, an admin/operator/viewer user with no name/e-mail
match against any collaborator fell back to `rows[0]` (the ranking's first place), leaking that
collaborator's score to an unrelated user. Now that users can be linked directly via
`users.collaborator_id`, that link must win, and no match at all must return None instead of
leaking data."""

from datetime import datetime, timezone

from app.models import CalculationRun, ScoringGroup, ScoringSubjectRule, User
from app.services.portal_dashboard import _audit_order, _order_label, _portal_run, _resolve_score, build_portal_rules

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


def test_audit_order_preserves_diagnosis_and_recurrence_evidence():
    result = _audit_order(
        {
            "os_code": "IXC-101",
            "os_type": "Manutenção",
            "os_subject": "Retorno",
            "customer_name": "Cliente Exemplo",
            "status_label": "Anulada por diagnóstico",
            "sla_status_normalized": "NO_PRAZO",
            "diagnosis_action_type": "cancel_points",
            "diagnosis_penalty_reason": "Diagnóstico X anulou a pontuação base",
            "recurrence_related_os_code": "IXC-202",
            "recurrence_days_between": 4,
        }
    )

    assert result["diagnosis_action_type"] == "cancel_points"
    assert result["diagnosis_penalty_reason"] == "Diagnóstico X anulou a pontuação base"
    assert result["recurrence_related_os_code"] == "IXC-202"
    assert result["recurrence_days_between"] == 4
    assert result["customer_name"] == "Cliente Exemplo"
    assert result["sla_status_normalized"] == "NO_PRAZO"


def test_order_label_hides_technical_sla_import_trace():
    status_label, reason = _order_label(
        {
            "is_annulled": True,
            "scoring_status": "Anulada por diagnóstico",
            "reasons": [
                "SLA original importado: Não informado",
                "SLA normalizado: NO_PRAZO",
                "Assunto vinculado ao grupo Manutenção",
                "Diagnóstico Equipamentos: Não Removidos anulou a pontuação base",
            ],
        }
    )

    assert status_label == "Anulada por diagnóstico"
    assert reason == "Diagnóstico Equipamentos: Não Removidos anulou a pontuação base"


def test_portal_rules_exposes_effective_points_and_source(db_session):
    group = ScoringGroup(name="Manutenção", default_points=12, active=True)
    db_session.add(group)
    db_session.flush()
    db_session.add_all(
        [
            ScoringSubjectRule(
                group_id=group.id,
                os_type="Manutenção",
                os_subject="Reparo padrão",
                use_group_default=True,
                active=True,
            ),
            ScoringSubjectRule(
                group_id=group.id,
                os_type="Manutenção",
                os_subject="Reparo especial",
                custom_points=25,
                use_group_default=False,
                active=True,
            ),
        ]
    )
    db_session.flush()

    result = build_portal_rules(db_session)
    subjects = {item["os_subject"]: item for item in result["subjects"]}

    assert subjects["Reparo padrão"]["points"] == 12
    assert subjects["Reparo padrão"]["point_source"] == "Valor padrão do grupo"
    assert subjects["Reparo especial"]["points"] == 25
    assert subjects["Reparo especial"]["point_source"] == "Valor específico deste assunto"


def test_portal_run_returns_the_latest_revision_for_the_requested_period(db_session):
    older_revision = CalculationRun(
        reference_month=6,
        reference_year=2026,
        status="approved",
        point_value=1,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    latest_revision = CalculationRun(
        reference_month=6,
        reference_year=2026,
        status="approved",
        point_value=1,
        created_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )
    other_period = CalculationRun(
        reference_month=7,
        reference_year=2026,
        status="approved",
        point_value=1,
        created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    db_session.add_all([older_revision, latest_revision, other_period])
    db_session.flush()

    result = _portal_run(db_session, reference_month=6, reference_year=2026)

    assert result is not None
    assert result.id == latest_revision.id
