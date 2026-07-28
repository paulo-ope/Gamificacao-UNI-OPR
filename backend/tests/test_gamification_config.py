"""Regression tests for backend/app/services/gamification_config.py."""
from app.services import gamification_config as gc


def test_apply_config_reports_a_warning_when_a_subject_rule_group_cannot_be_resolved(db_session):
    """Regression (audit finding B4): a scoring_subject_rules item referencing a group_id/
    group_name that doesn't exist in this environment (e.g. restoring a config exported from a
    different environment, or after the referenced group was deleted/renamed) used to be
    silently dropped - no error, no warning, no signal to whoever applied the config that the
    scoring matrix just got smaller."""
    config = {
        "settings": {},
        "scoring_groups": [],
        "scoring_subject_rules": [
            {
                "os_type": "Manutencao",
                "os_subject": "Reparo Orfao",
                "group_name": "Grupo Que Nao Existe",
                "custom_points": 10,
                "active": True,
            }
        ],
        "diagnosis_penalty_rules": [],
        "sla_penalty_rules": [],
        "recurrence_classification_rules": [],
        "health_rules": [],
    }

    result = gc.apply_config(db_session, config)

    assert result.get("warnings"), "deveria ter pelo menos um aviso sobre a regra ignorada"
    assert any("Reparo Orfao" in warning for warning in result["warnings"])
    assert not any(
        rule["os_subject"] == "Reparo Orfao" for rule in result["scoring_subject_rules"]
    ), "a regra orfa nao deveria ter sido criada"


def test_apply_config_has_no_warnings_for_a_normal_config(db_session):
    """Sanity check: a config where every subject rule resolves its group normally must not
    generate spurious warnings."""
    config = {
        "settings": {},
        "scoring_groups": [{"name": "Manutencao", "default_points": 15.0, "active": True}],
        "scoring_subject_rules": [
            {
                "os_type": "Manutencao",
                "os_subject": "Reparo",
                "group_name": "Manutencao",
                "use_group_default": True,
                "active": True,
            }
        ],
        "diagnosis_penalty_rules": [],
        "sla_penalty_rules": [],
        "recurrence_classification_rules": [],
        "health_rules": [],
    }

    result = gc.apply_config(db_session, config)

    assert not result.get("warnings")
    assert any(rule["os_subject"] == "Reparo" for rule in result["scoring_subject_rules"])
