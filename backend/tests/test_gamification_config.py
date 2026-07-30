"""Regression tests for backend/app/services/gamification_config.py."""
from app.models import Collaborator
from app.services import gamification_config as gc


def _base_config(**overrides):
    config = {
        "settings": {},
        "scoring_groups": [],
        "scoring_subject_rules": [],
        "diagnosis_penalty_rules": [],
        "sla_penalty_rules": [],
        "recurrence_classification_rules": [],
        "health_rules": [],
        "collaborators": [],
    }
    config.update(overrides)
    return config


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


def test_apply_config_matches_collaborator_by_ixc_employee_id_over_name(db_session):
    """Regression: importar uma config de outro ambiente (ex.: da VM) deve casar o colaborador
    pelo vinculo com o IXC quando ele existir - mais confiavel que nome, que pode ter sido
    digitado diferente entre os dois bancos. Sem isso, importar duas vezes criaria um
    colaborador duplicado a cada import."""
    existing = Collaborator(name="Nome Antigo", role="Tecnico", regional="UNI SUL", ixc_employee_id=999, is_registered=False)
    db_session.add(existing)
    db_session.flush()

    config = _base_config(
        collaborators=[
            {
                "name": "Nome Corrigido",
                "role": "Tecnico",
                "regional": "UNI SUL",
                "active": True,
                "is_registered": True,
                "ixc_employee_id": 999,
            }
        ]
    )

    gc.apply_config(db_session, config)
    db_session.flush()

    db_session.refresh(existing)
    assert existing.name == "Nome Corrigido"
    assert existing.is_registered is True, "casou pelo ixc_employee_id e atualizou o mesmo registro, nao criou um novo"
    assert db_session.query(Collaborator).count() == 1


def test_apply_config_creates_new_collaborator_when_no_match_found(db_session):
    """Um colaborador que nao existe ainda no ambiente de destino deve ser criado, nao ignorado -
    e assim que se leva o cadastro completo de um ambiente pro outro."""
    config = _base_config(
        collaborators=[
            {
                "name": "Colaborador Novo",
                "role": "Tecnico",
                "regional": "UNI SUL",
                "active": True,
                "is_registered": True,
                "ixc_employee_id": 555,
            }
        ]
    )

    gc.apply_config(db_session, config)
    db_session.flush()

    created = db_session.query(Collaborator).filter(Collaborator.name == "Colaborador Novo").one()
    assert created.ixc_employee_id == 555
    assert created.is_registered is True


def test_apply_config_matches_by_ixc_employee_id_even_when_a_different_collaborator_shares_the_name(db_session):
    """O casamento por ixc_employee_id roda ANTES do casamento por nome (decisao do usuario) -
    entao mesmo que exista outro colaborador cujo nome bata com o do JSON, quem realmente e
    atualizado e o dono verdadeiro do vinculo (o id nao pode pertencer a duas pessoas reais
    diferentes). O outro colaborador so-por-nome fica intocado."""
    owner = Collaborator(name="Dono Do Vinculo", role="Tecnico", regional="UNI SUL", ixc_employee_id=42)
    other = Collaborator(name="Outro Colaborador", role="Tecnico", regional="UNI SUL", ixc_employee_id=None)
    db_session.add_all([owner, other])
    db_session.flush()

    config = _base_config(
        collaborators=[
            {
                "name": "Outro Colaborador",
                "role": "Tecnico",
                "regional": "UNI SUL",
                "active": True,
                "is_registered": True,
                "ixc_employee_id": 42,
            }
        ]
    )

    gc.apply_config(db_session, config)
    db_session.flush()

    db_session.refresh(owner)
    db_session.refresh(other)
    assert owner.name == "Outro Colaborador", "o dono do vinculo (id=42) foi atualizado, nao criado um segundo registro"
    assert owner.ixc_employee_id == 42
    assert other.ixc_employee_id is None, "o colaborador so-por-nome nao deveria ganhar o vinculo de outro dono"
    assert db_session.query(Collaborator).count() == 2, "nao deveria ter criado um terceiro registro"


def test_serialize_current_config_includes_collaborators(db_session):
    """O JSON exportado precisa trazer o cadastro de colaboradores - sem isso, mover a config
    de um ambiente pro outro (ex.: da VM) nunca carrega quem esta cadastrado."""
    db_session.add(Collaborator(name="Fulano", role="Tecnico", regional="UNI SUL", is_registered=True, ixc_employee_id=123))
    db_session.flush()

    result = gc.serialize_current_config(db_session)

    assert "collaborators" in result
    assert any(item["name"] == "Fulano" and item["ixc_employee_id"] == 123 for item in result["collaborators"])
