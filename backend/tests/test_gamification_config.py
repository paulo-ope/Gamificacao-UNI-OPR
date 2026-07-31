"""Regression tests for backend/app/services/gamification_config.py."""
from app.models import AppSetting, Collaborator, DiagnosisPenaltyRule, LeadershipProfile, LeadershipRoleProfile
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


def test_apply_config_diagnosis_rule_prefers_name_match_over_a_stale_id(db_session):
    """Regression (incidente real em producao, 2026-07-30): um JSON reimportado de outro momento
    trazia um item com id=6 e diagnosis_name='Resolvido', mas nesse banco o id=6 ja pertencia a
    OUTRO diagnostico ('Apps: Max + Canais em funcionamento') e uma linha diferente (id=80) ja
    era a dona legitima do nome 'Resolvido'. Casar por id primeiro fazia o apply_config tentar
    renomear a linha errada para 'Resolvido', colidindo com a constraint unica de
    diagnosis_name e derrubando o import com IntegrityError. O nome (chave unica de negocio)
    deve vencer quando id e nome apontam para linhas diferentes."""
    stale_id_owner = DiagnosisPenaltyRule(diagnosis_name="Apps: Max + Canais em funcionamento", action_type="no_penalty")
    name_owner = DiagnosisPenaltyRule(diagnosis_name="Resolvido", action_type="no_penalty")
    db_session.add_all([stale_id_owner, name_owner])
    db_session.flush()
    stale_id = stale_id_owner.id

    config = _base_config(
        diagnosis_penalty_rules=[
            {
                "id": stale_id,
                "diagnosis_name": "Resolvido",
                "action_type": "no_penalty",
                "description": "Diagnostico conclusivo sem penalidade.",
                "active": True,
            }
        ]
    )

    gc.apply_config(db_session, config)
    db_session.flush()

    db_session.refresh(stale_id_owner)
    db_session.refresh(name_owner)
    assert stale_id_owner.diagnosis_name == "Apps: Max + Canais em funcionamento", "a linha do id desatualizado nao deveria ser renomeada"
    assert name_owner.diagnosis_name == "Resolvido"
    assert name_owner.description == "Diagnostico conclusivo sem penalidade.", "a atualizacao deveria ter sido aplicada na linha dona do nome"
    assert db_session.query(DiagnosisPenaltyRule).count() == 2, "nao deveria ter criado uma terceira linha"


def test_apply_config_creates_leadership_role_profile_and_profile_linked_to_collaborator(db_session):
    """Regression: liderança (perfis de cargo e lideres) nao era exportada/importada pela config
    de gamificacao - migrar de ambiente (ex.: da VM pro local) nunca levava o cadastro de
    supervisor/gerente, precisava ser recriado manualmente. Cobre o caminho feliz: perfil de
    cargo e um lider vinculado a um colaborador por ixc_employee_id (portavel entre ambientes)."""
    collaborator = Collaborator(name="Lider Um", role="Supervisor", regional="UNI SUL", ixc_employee_id=321)
    db_session.add(collaborator)
    db_session.flush()

    config = _base_config(
        leadership_role_profiles=[
            {"name": "Supervisor Padrao", "scope_type": "supervisor", "default_multiplier": 1.5, "active": True}
        ],
        leadership_profiles=[
            {
                "name": "Lider Um",
                "role_type": "supervisor",
                "role_profile_name": "Supervisor Padrao",
                "use_custom_multiplier": False,
                "average_source": "collaborators",
                "active": True,
                "collaborator_ixc_employee_id": 321,
                "regional_names": ["UNI SUL"],
            }
        ],
    )

    result = gc.apply_config(db_session, config)
    db_session.flush()

    assert not result.get("warnings")
    role_profile = db_session.query(LeadershipRoleProfile).filter_by(name="Supervisor Padrao").one()
    profile = db_session.query(LeadershipProfile).filter_by(name="Lider Um").one()
    assert profile.role_profile_id == role_profile.id
    assert profile.multiplier == 1.5, "sem multiplicador customizado, deveria herdar o default do perfil de cargo"
    assert profile.collaborator_id == collaborator.id
    assert sorted(item.regional_name for item in profile.regionals) == ["UNI SUL"]


def test_apply_config_leadership_role_profile_prefers_name_match_over_a_stale_id(db_session):
    """Regression: LeadershipRoleProfile.name e unico no banco - o mesmo bug corrigido para
    diagnosis_penalty_rules (id desatualizado de outro ambiente colidindo com o dono real do
    nome) se aplica aqui igual, pelo mesmo _resolve_by_id_or_name."""
    stale_id_owner = LeadershipRoleProfile(name="Gerente de pasta", scope_type="portfolio_manager", default_multiplier=3.0)
    name_owner = LeadershipRoleProfile(name="Supervisor Padrao", scope_type="supervisor", default_multiplier=1.5)
    db_session.add_all([stale_id_owner, name_owner])
    db_session.flush()
    stale_id = stale_id_owner.id

    config = _base_config(
        leadership_role_profiles=[
            {"id": stale_id, "name": "Supervisor Padrao", "scope_type": "supervisor", "default_multiplier": 1.8, "active": True}
        ]
    )

    gc.apply_config(db_session, config)
    db_session.flush()

    db_session.refresh(stale_id_owner)
    db_session.refresh(name_owner)
    assert stale_id_owner.name == "Gerente de pasta", "a linha do id desatualizado nao deveria ser renomeada"
    assert name_owner.default_multiplier == 1.8, "a atualizacao deveria ter sido aplicada na linha dona do nome"
    assert db_session.query(LeadershipRoleProfile).count() == 2


def test_apply_config_leadership_profile_without_required_regional_is_skipped_with_a_warning(db_session):
    """Regression: supervisor/gerente da unidade sem filial vinculada tem o bonus sempre R$ 0
    (ver validate_scope_regionals_required) - importar um perfil assim nao pode travar o import
    inteiro nem criar silenciosamente um perfil invalido; deve avisar e pular, como o resto da
    config ja faz para referencias que nao resolvem."""
    config = _base_config(
        leadership_profiles=[
            {"name": "Lider Sem Filial", "role_type": "supervisor", "active": True, "regional_names": []}
        ]
    )

    result = gc.apply_config(db_session, config)

    assert result.get("warnings")
    assert any("Lider Sem Filial" in warning for warning in result["warnings"])
    assert db_session.query(LeadershipProfile).filter_by(name="Lider Sem Filial").first() is None


def test_leadership_config_survives_a_full_export_wipe_reimport_round_trip(db_session):
    """Garantia de ponta a ponta pedida pelo usuario: o JSON de config precisa trazer a
    lideranca COMPLETA, nao so alguns campos. Em vez de checar campo por campo (o que sempre
    corre o risco de esquecer um), este teste monta um cenario realista com os 3 tipos de
    lideranca (supervisor com filial, gerente da unidade multi-filial, gerente de pasta sem
    filial), multiplicador customizado e vinculo com colaborador via ixc_employee_id - exporta,
    APAGA tudo (simulando reimportar num ambiente vazio, como da VM pro local), reimporta o
    mesmo JSON e exporta de novo. Se a segunda exportacao for identica a primeira (exceto pelos
    ids internos, que sao esperados mudar), a config e portavel de ponta a ponta de verdade."""
    from app.models import LeadershipProfileRegional
    from app.services.leadership_bonus import replace_profile_regionals

    collaborator = Collaborator(name="Lider Multi", role="Gerente", regional="UNI SUL", ixc_employee_id=456)
    db_session.add(collaborator)
    db_session.flush()

    role_profile = LeadershipRoleProfile(name="Gerente da Unidade Padrao", scope_type="regional_manager", default_multiplier=2.0, active=True)
    db_session.add(role_profile)
    db_session.flush()

    supervisor = LeadershipProfile(
        name="Supervisor Filial Unica", role_type="supervisor", percentage=0, multiplier=1.5, active=True
    )
    regional_manager = LeadershipProfile(
        name="Lider Multi",
        role_type="regional_manager",
        percentage=0,
        role_profile_id=role_profile.id,
        multiplier=2.0,
        collaborator_id=collaborator.id,
        active=True,
    )
    portfolio_manager = LeadershipProfile(
        name="Gerente De Pasta Custom",
        role_type="portfolio_manager",
        percentage=0,
        use_custom_multiplier=True,
        custom_multiplier=4.25,
        multiplier=4.25,
        average_source="collaborators_and_leaders",
        active=True,
    )
    db_session.add_all([supervisor, regional_manager, portfolio_manager])
    db_session.flush()
    replace_profile_regionals(db_session, supervisor, ["UNI SUL"])
    replace_profile_regionals(db_session, regional_manager, ["UNI SUL", "UNI NORTE"])
    db_session.flush()

    before = gc.serialize_current_config(db_session)

    db_session.query(LeadershipProfileRegional).delete()
    db_session.query(LeadershipProfile).delete()
    db_session.query(LeadershipRoleProfile).delete()
    db_session.flush()
    assert db_session.query(LeadershipProfile).count() == 0, "cenario precisa comecar zerado, como um ambiente novo"

    result = gc.apply_config(db_session, before)
    assert not result.get("warnings"), f"reimport nao deveria gerar avisos: {result.get('warnings')}"

    after = gc.serialize_current_config(db_session)

    def _without_id(items):
        return sorted((({k: v for k, v in item.items() if k != "id"}) for item in items), key=lambda item: item["name"])

    assert _without_id(after["leadership_role_profiles"]) == _without_id(before["leadership_role_profiles"])
    assert _without_id(after["leadership_profiles"]) == _without_id(before["leadership_profiles"])
    assert len(after["leadership_profiles"]) == 3, "os 3 tipos de lideranca (supervisor, gerente da unidade, gerente de pasta) precisam sobreviver ao round-trip"


def test_serialize_current_config_includes_leadership(db_session):
    """O JSON exportado precisa trazer perfis de cargo e lideres com os vinculos resolvidos por
    nome/ixc_employee_id (portaveis entre ambientes), nao so pelos ids internos."""
    collaborator = Collaborator(name="Lider Export", role="Supervisor", regional="UNI SUL", ixc_employee_id=777)
    role_profile = LeadershipRoleProfile(name="Supervisor Padrao", scope_type="supervisor", default_multiplier=1.5)
    db_session.add_all([collaborator, role_profile])
    db_session.flush()

    profile = LeadershipProfile(
        name="Lider Export",
        role_type="supervisor",
        percentage=0,
        multiplier=1.5,
        role_profile_id=role_profile.id,
        collaborator_id=collaborator.id,
    )
    db_session.add(profile)
    db_session.flush()
    from app.services.leadership_bonus import replace_profile_regionals

    replace_profile_regionals(db_session, profile, ["UNI SUL"])
    db_session.flush()

    result = gc.serialize_current_config(db_session)

    assert any(item["name"] == "Supervisor Padrao" for item in result["leadership_role_profiles"])
    exported = next(item for item in result["leadership_profiles"] if item["name"] == "Lider Export")
    assert exported["role_profile_name"] == "Supervisor Padrao"
    assert exported["collaborator_ixc_employee_id"] == 777
    assert exported["regional_names"] == ["UNI SUL"]


def test_gamification_config_schemas_do_not_drop_leadership_fields():
    """Regression: os schemas Pydantic GamificationConfigImport/GamificationConfigOut (usados
    pelas rotas /gamification/config/export e /import, via payload.model_dump()) declaram cada
    secao explicitamente - por padrao o Pydantic descarta qualquer campo nao declarado. Sem
    leadership_role_profiles/leadership_profiles aqui, o backend do apply_config estaria pronto
    mas a rota real descartaria os dois campos antes de chegar la, e a exportacao real (via
    GamificationConfigOut) nunca incluiria liderança no JSON baixado."""
    from app.schemas import GamificationConfigImport, GamificationConfigOut

    payload = GamificationConfigImport(
        leadership_role_profiles=[{"name": "Supervisor Padrao"}],
        leadership_profiles=[{"name": "Lider Um"}],
    )
    dumped = payload.model_dump()
    assert dumped["leadership_role_profiles"] == [{"name": "Supervisor Padrao"}]
    assert dumped["leadership_profiles"] == [{"name": "Lider Um"}]

    out = GamificationConfigOut(
        leadership_role_profiles=[{"name": "Supervisor Padrao"}],
        leadership_profiles=[{"name": "Lider Um"}],
    )
    assert out.model_dump()["leadership_role_profiles"] == [{"name": "Supervisor Padrao"}]


def test_serialize_current_config_includes_collaborators(db_session):
    """O JSON exportado precisa trazer o cadastro de colaboradores - sem isso, mover a config
    de um ambiente pro outro (ex.: da VM) nunca carrega quem esta cadastrado."""
    db_session.add(Collaborator(name="Fulano", role="Tecnico", regional="UNI SUL", is_registered=True, ixc_employee_id=123))
    db_session.flush()

    result = gc.serialize_current_config(db_session)

    assert "collaborators" in result
    assert any(item["name"] == "Fulano" and item["ixc_employee_id"] == 123 for item in result["collaborators"])


def test_serialize_current_config_excludes_scheduling_settings(db_session):
    """Regression (vazamento mapeado na Fase 5 do plano de administração): `app_settings` e
    compartilhada com o Agendamento (chaves scheduling_*). O export da config da Gamificacao nao
    pode carregar parametros de outro modulo."""
    db_session.add(AppSetting(key="scheduling_business_start", value="07:30"))
    db_session.add(AppSetting(key="point_value", value="3.00"))
    db_session.flush()

    result = gc.serialize_current_config(db_session)

    assert "scheduling_business_start" not in result["settings"]
    assert result["settings"]["point_value"] == "3.00"


def test_apply_config_ignores_and_warns_about_foreign_settings_keys(db_session):
    """Regression: importar um export antigo (ou de outro ambiente) da Gamificacao nao pode
    sobrescrever silenciosamente um parametro do Agendamento - a chave estranha deve ser ignorada
    e sinalizada como aviso, nao aplicada."""
    db_session.add(AppSetting(key="scheduling_business_start", value="07:30"))
    db_session.flush()

    config = _base_config(settings={"scheduling_business_start": "23:00", "point_value": "5.00"})

    result = gc.apply_config(db_session, config)

    scheduling_setting = db_session.query(AppSetting).filter_by(key="scheduling_business_start").one()
    assert scheduling_setting.value == "07:30", "valor do Agendamento nao pode ter sido sobrescrito"
    assert result["settings"]["point_value"] == "5.00"
    assert any("scheduling_business_start" in warning for warning in result["warnings"])
