"""Auditoria da Estrutura Operacional Confiável (pedido do usuário em 2026-08-29) - cobre cada um
dos 13 tipos de inconsistência obrigatórios, a permissão dedicada e a garantia de que nenhum CPF
completo aparece na resposta. Cada teste isola só os dados necessários para o próprio achado -
`db_session` é um banco novo por teste (ver conftest.py), então nenhum resíduo de um teste
contamina o outro."""
from datetime import datetime, timedelta, timezone

from app.core.security import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import Collaborator, User
from app.modules.management.models import ManagementOperationalMember
from app.modules.management import structure_audit as structure_audit_module
from app.modules.management.structure_audit import run_structure_audit
from app.modules.operations.models import OperationBranchCapacity, OperationOrder, OperationResponsibleAssignment, OperationTeamModel
from fastapi.testclient import TestClient

VALID_CPF_DIGITS = "52998224725"


def _finding_types(result):
    return {item.type for item in result.findings}


def test_active_collaborator_without_ixc_id_is_flagged(db_session, make_collaborator):
    collaborator = make_collaborator(name="Sem Ixc")
    db_session.commit()

    result = run_structure_audit(db_session)

    match = next(item for item in result.findings if item.type == "collaborator_without_ixc_id")
    assert match.entity_id == collaborator.id
    assert match.blocks_capacity is True
    assert match.severity == "atencao"


def test_active_collaborator_with_ixc_id_is_not_flagged(db_session, make_collaborator):
    collaborator = make_collaborator(name="Com Ixc")
    collaborator.ixc_employee_id = 999
    db_session.commit()

    result = run_structure_audit(db_session)

    assert "collaborator_without_ixc_id" not in _finding_types(result)


def test_collaborator_without_cpf_is_informative_and_never_exposes_full_cpf(db_session, make_collaborator):
    with_cpf = make_collaborator(name="Com Cpf")
    with_cpf.cpf = VALID_CPF_DIGITS
    without_cpf = make_collaborator(name="Sem Cpf")
    db_session.commit()

    result = run_structure_audit(db_session)

    match = next(item for item in result.findings if item.type == "collaborator_without_cpf")
    assert match.entity_id == without_cpf.id
    assert match.severity == "informativo"
    assert match.blocks_capacity is False
    assert result.summary.collaborators_with_cpf == 1

    payload = "".join(f"{item.type}{item.description}{item.subject_name}" for item in result.findings)
    assert VALID_CPF_DIGITS not in payload


def test_active_collaborator_without_team_type_is_flagged(db_session, make_collaborator):
    collaborator = make_collaborator(name="Sem Tipo De Equipe")
    db_session.commit()

    result = run_structure_audit(db_session)

    match = next(item for item in result.findings if item.type == "collaborator_without_team_type")
    assert match.entity_id == collaborator.id
    assert match.blocks_capacity is True


def test_field_collaborator_without_supervisor_is_flagged(db_session, make_collaborator):
    collaborator = make_collaborator(name="Campo Sem Supervisor")
    collaborator.team_type = "field"
    db_session.commit()

    result = run_structure_audit(db_session)

    match = next(item for item in result.findings if item.type == "collaborator_without_supervisor")
    assert match.entity_id == collaborator.id


def test_non_field_collaborator_without_supervisor_is_not_flagged(db_session, make_collaborator):
    collaborator = make_collaborator(name="Administrativo")
    collaborator.team_type = "administrative"
    db_session.commit()

    result = run_structure_audit(db_session)

    assert "collaborator_without_supervisor" not in _finding_types(result)


def test_responsible_without_matching_collaborator_is_critical(db_session):
    db_session.add(
        OperationResponsibleAssignment(responsible_name="Fantasma Sem Cadastro", regional="UNI JARU")
    )
    db_session.commit()

    result = run_structure_audit(db_session)

    match = next(item for item in result.findings if item.type == "responsible_without_collaborator")
    assert match.subject_name == "Fantasma Sem Cadastro"
    assert match.severity == "critico"
    assert match.blocks_capacity is True


def test_responsible_with_matching_collaborator_is_not_flagged_as_missing(db_session, make_collaborator):
    make_collaborator(name="Tecnico Cadastrado")
    db_session.add(
        OperationResponsibleAssignment(responsible_name="Tecnico Cadastrado", regional="UNI SUL")
    )
    db_session.commit()

    result = run_structure_audit(db_session)

    assert "responsible_without_collaborator" not in _finding_types(result)


def test_responsible_with_production_in_multiple_regionals_is_flagged(db_session):
    db_session.add_all(
        [
            OperationResponsibleAssignment(responsible_name="Multi Regional", regional="UNI JARU"),
            OperationResponsibleAssignment(responsible_name="Multi Regional", regional="UNI ARIQUEMES"),
        ]
    )
    db_session.commit()

    result = run_structure_audit(db_session)

    match = next(item for item in result.findings if item.type == "responsible_multi_regional")
    assert match.subject_name == "Multi Regional"
    assert "UNI ARIQUEMES" in match.regional and "UNI JARU" in match.regional


def test_responsible_with_single_regional_is_not_flagged_as_multi(db_session):
    db_session.add(OperationResponsibleAssignment(responsible_name="Uma Regional Só", regional="UNI JARU"))
    db_session.commit()

    result = run_structure_audit(db_session)

    assert "responsible_multi_regional" not in _finding_types(result)


def test_collaborator_regional_diverging_from_order_history_is_flagged(db_session, make_collaborator):
    collaborator = make_collaborator(name="Mudou De Base", regional="UNI JARU")
    collaborator.ixc_employee_id = 501
    db_session.flush()
    now = datetime.now(timezone.utc)
    # 3 O.S. em Ariquemes contra 1 em Jaru - regional predominante diverge da oficial (Jaru).
    for index in range(3):
        db_session.add(
            OperationOrder(
                source="ixc",
                source_order_id=f"OS-ARQ-{index}",
                order_code=f"OS-ARQ-{index}",
                regional="UNI ARIQUEMES",
                responsible="Mudou De Base",
                responsible_ixc_id=501,
                opened_at=now,
                raw_payload={},
            )
        )
    db_session.add(
        OperationOrder(
            source="ixc",
            source_order_id="OS-JARU-0",
            order_code="OS-JARU-0",
            regional="UNI JARU",
            responsible="Mudou De Base",
            responsible_ixc_id=501,
            opened_at=now,
            raw_payload={},
        )
    )
    db_session.commit()

    result = run_structure_audit(db_session)

    match = next(item for item in result.findings if item.type == "collaborator_regional_diverges_from_orders")
    assert match.entity_id == collaborator.id
    assert match.regional == "UNI JARU"
    assert "UNI ARIQUEMES" in match.description


def test_collaborator_regional_matching_order_history_is_not_flagged(db_session, make_collaborator):
    collaborator = make_collaborator(name="Regional Certa", regional="UNI JARU")
    collaborator.ixc_employee_id = 502
    db_session.flush()
    db_session.add(
        OperationOrder(
            source="ixc",
            source_order_id="OS-OK-0",
            order_code="OS-OK-0",
            regional="UNI JARU",
            responsible="Regional Certa",
            responsible_ixc_id=502,
            opened_at=datetime.now(timezone.utc),
            raw_payload={},
        )
    )
    db_session.commit()

    result = run_structure_audit(db_session)

    assert "collaborator_regional_diverges_from_orders" not in _finding_types(result)


def test_active_member_without_team_model_is_flagged(db_session):
    db_session.add(
        ManagementOperationalMember(responsible_name="Sem Modelo", regional="UNI JARU", is_active=True, status="without_team_model")
    )
    db_session.commit()

    result = run_structure_audit(db_session)

    match = next(item for item in result.findings if item.type == "member_without_team_model")
    assert match.subject_name == "Sem Modelo"
    assert match.blocks_capacity is True


def test_inactive_team_model_still_used_by_active_member_is_critical(db_session):
    model = OperationTeamModel(name="Modelo Desativado", active=False)
    db_session.add(model)
    db_session.flush()
    db_session.add(
        ManagementOperationalMember(
            responsible_name="Usa Modelo Inativo", regional="UNI JARU", is_active=True, team_model_id=model.id, status="validated_operation"
        )
    )
    db_session.commit()

    result = run_structure_audit(db_session)

    match = next(item for item in result.findings if item.type == "team_model_inactive_still_used")
    assert match.entity_id == model.id
    assert match.severity == "critico"


def test_inactive_team_model_used_only_by_inactive_member_is_not_flagged(db_session):
    model = OperationTeamModel(name="Modelo Desativado 2", active=False)
    db_session.add(model)
    db_session.flush()
    db_session.add(
        ManagementOperationalMember(
            responsible_name="Membro Inativo", regional="UNI JARU", is_active=False, team_model_id=model.id, status="inactive"
        )
    )
    db_session.commit()

    result = run_structure_audit(db_session)

    assert "team_model_inactive_still_used" not in _finding_types(result)


def test_regional_with_active_member_without_branch_capacity_is_flagged(db_session):
    db_session.add(
        ManagementOperationalMember(responsible_name="Ativo Sem Capacidade", regional="UNI JARU", is_active=True, status="validated_operation")
    )
    db_session.commit()

    result = run_structure_audit(db_session)

    match = next(item for item in result.findings if item.type == "regional_without_branch_capacity")
    assert match.regional == "UNI JARU"


def test_regional_with_branch_capacity_configured_is_not_flagged(db_session):
    db_session.add(OperationBranchCapacity(regional="UNI JARU", good_threshold=2500, great_threshold=3000, excellent_threshold=3500))
    db_session.add(
        ManagementOperationalMember(responsible_name="Com Capacidade", regional="UNI JARU", is_active=True, status="validated_operation")
    )
    db_session.commit()

    result = run_structure_audit(db_session)

    assert "regional_without_branch_capacity" not in _finding_types(result)


def test_branch_capacity_with_zeroed_threshold_is_critical(db_session):
    db_session.add(OperationBranchCapacity(regional="UNI ZERADA", good_threshold=0, great_threshold=3000, excellent_threshold=3500))
    db_session.commit()

    result = run_structure_audit(db_session)

    match = next(item for item in result.findings if item.type == "branch_capacity_invalid_thresholds")
    assert match.regional == "UNI ZERADA"
    assert match.severity == "critico"


def test_branch_capacity_with_thresholds_out_of_order_is_critical(db_session):
    db_session.add(OperationBranchCapacity(regional="UNI FORA DE ORDEM", good_threshold=3000, great_threshold=2500, excellent_threshold=3500))
    db_session.commit()

    result = run_structure_audit(db_session)

    match = next(item for item in result.findings if item.type == "branch_capacity_invalid_thresholds")
    assert match.regional == "UNI FORA DE ORDEM"


def test_branch_capacity_with_valid_thresholds_is_not_flagged(db_session):
    db_session.add(OperationBranchCapacity(regional="UNI VALIDA", good_threshold=2500, great_threshold=3000, excellent_threshold=3500))
    db_session.commit()

    result = run_structure_audit(db_session)

    assert "branch_capacity_invalid_thresholds" not in _finding_types(result)


def test_member_pending_validation_is_flagged(db_session):
    db_session.add(
        ManagementOperationalMember(responsible_name="Pendente", regional="UNI JARU", is_active=True, status="pending_validation")
    )
    db_session.commit()

    result = run_structure_audit(db_session)

    match = next(item for item in result.findings if item.type == "member_pending_validation")
    assert match.subject_name == "Pendente"
    assert match.severity == "atencao"


def test_recent_production_with_pending_structure_is_critical(db_session):
    recent = datetime.now(timezone.utc) - timedelta(days=5)
    db_session.add(
        ManagementOperationalMember(
            responsible_name="Trabalhando Sem Estrutura",
            regional="UNI JARU",
            is_active=True,
            status="pending_validation",
            last_order_at=recent,
        )
    )
    db_session.commit()

    result = run_structure_audit(db_session)

    match = next(item for item in result.findings if item.type == "recent_production_pending_structure")
    assert match.subject_name == "Trabalhando Sem Estrutura"
    assert match.severity == "critico"
    assert match.blocks_capacity is True


def test_old_production_with_pending_structure_is_not_flagged_as_recent(db_session):
    old = datetime.now(timezone.utc) - timedelta(days=200)
    db_session.add(
        ManagementOperationalMember(
            responsible_name="Pendente Antigo", regional="UNI JARU", is_active=True, status="pending_validation", last_order_at=old
        )
    )
    db_session.commit()

    result = run_structure_audit(db_session)

    assert "recent_production_pending_structure" not in _finding_types(result)


def test_validated_member_with_recent_production_is_not_flagged_as_pending(db_session):
    recent = datetime.now(timezone.utc) - timedelta(days=5)
    db_session.add(
        ManagementOperationalMember(
            responsible_name="Validado E Ativo", regional="UNI JARU", is_active=True, status="validated_operation", last_order_at=recent
        )
    )
    db_session.commit()

    result = run_structure_audit(db_session)

    assert "recent_production_pending_structure" not in _finding_types(result)


def test_summary_counters_match_raw_data(db_session, make_collaborator):
    make_collaborator(name="Ativo Com Tudo")
    inactive = make_collaborator(name="Inativo")
    inactive.active = False
    db_session.add(OperationResponsibleAssignment(responsible_name="Ativo Com Tudo", regional="UNI SUL"))
    db_session.add(ManagementOperationalMember(responsible_name="Ativo Com Tudo", regional="UNI SUL", is_active=True))
    db_session.commit()

    result = run_structure_audit(db_session)

    assert result.summary.total_collaborators == 2
    assert result.summary.active_collaborators == 1
    assert result.summary.responsible_assignments == 1
    assert result.summary.management_members == 1
    assert result.total_findings == len(result.findings)
    assert result.critical_count + result.attention_count + result.informative_count == result.total_findings


def test_low_volume_severity_still_appears_when_another_severity_is_truncated(db_session, make_collaborator, monkeypatch):
    """Regressão de um achado real ao validar ao vivo: o corte de segurança cortava a lista JÁ
    ORDENADA por severidade (crítico primeiro) - com poucas linhas de limite e muito mais
    `atencao` do que `informativo`/`critico`, a severidade `informativo` sumia inteira da lista
    (mesmo aparecendo certo no contador), fazendo o filtro por `informativo` mostrar "nenhum
    achado" apesar do card mostrar um número positivo. Corte por severidade corrige isso - toda
    severidade com achado real precisa aparecer com pelo menos uma linha na lista devolvida."""
    monkeypatch.setattr(structure_audit_module, "MAX_FINDINGS_PER_SEVERITY", 2)

    # 5 colaboradores ativos sem tipo de equipe (severidade "atencao") - mais que o limite de 2.
    for index in range(5):
        make_collaborator(name=f"Sem Tipo {index}")
    # 1 colaborador sem CPF é o único jeito de gerar severidade "informativo" aqui - os outros 5
    # também não têm CPF, então isso sozinho já basta (ver _audit_collaborators).
    db_session.commit()

    result = run_structure_audit(db_session)

    assert result.informative_count > 0
    returned_informative = [item for item in result.findings if item.severity == "informativo"]
    assert len(returned_informative) > 0, "achado de severidade informativo sumiu da lista mesmo com contador > 0"

    returned_attention = [item for item in result.findings if item.severity == "atencao"]
    assert len(returned_attention) == 2  # cortado pelo limite baixo do teste, mas presente


def test_no_permission_user_cannot_access_structure_audit(db_session):
    from app.core.security import hash_password

    non_admin = User(name="Sem Permissao", email="sem.permissao.audit@pytest.local", role="viewer", active=True, password_hash=hash_password("Qualquer123"))
    db_session.add(non_admin)
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: non_admin
    with TestClient(app) as test_client:
        response = test_client.get("/api/management/structure-audit")
        assert response.status_code == 403
    app.dependency_overrides.clear()


def test_admin_can_access_structure_audit_route(client, make_collaborator):
    make_collaborator(name="Qualquer Coisa")

    response = client.get("/api/management/structure-audit")

    assert response.status_code == 200
    body = response.json()
    assert "summary" in body
    assert "findings" in body
    assert isinstance(body["findings"], list)
