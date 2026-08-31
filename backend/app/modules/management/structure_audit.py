"""Auditoria da Estrutura Operacional Confiável (pedido do usuário em 2026-08-29, ver
docs/STATUS.md) - fase preparatória antes de "capacidade regional automática": cruza as fontes já
existentes (`Collaborator`, `OperationOrder`, `OperationResponsibleAssignment`, `OperationTeamModel`,
`OperationBranchCapacity`, `ManagementOperationalMember`) e devolve uma lista de inconsistências
estruturais, sem alterar nenhum dado. Leitura somente local - nenhuma chamada à API do IXC aqui.

Cada checagem é independente e aditiva à lista de `findings` - uma checagem que não encontra nada
simplesmente não contribui nenhuma linha. O volume de cada tabela envolvida é pequeno (algumas
centenas a poucos milhares de linhas) - processamento em memória depois de um punhado de SELECTs,
mesmo padrão já usado em `case_diagnostics` (cases.py) e `refresh_operational_members` (services.py),
não uma agregação nova em SQL por checagem."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Collaborator
from app.modules.management.models import ManagementOperationalMember
from app.modules.management.schemas import StructureAuditFinding, StructureAuditOut, StructureAuditSummary
from app.modules.management.services import _find_collaborator, _norm_name
from app.modules.operations.models import OperationBranchCapacity, OperationOrder, OperationResponsibleAssignment, OperationTeamModel
from app.modules.operations.responsible_regional import resolve_responsible_regional_candidates
from app.services.regional import normalize_regional

# Membro com produção dentro desta janela e ainda com estrutura pendente é o achado mais
# acionável (achado #13) - 30 dias é "produção do mês corrente", consistente com o ciclo mensal
# já usado pelo resto da Gestão Integrada (casos mensais, fechamento).
RECENT_PRODUCTION_DAYS = 30

_PENDING_STRUCTURE_STATUSES = {"pending_validation", "without_supervisor", "without_team_model"}

_SEVERITY_RANK = {"critico": 0, "atencao": 1, "informativo": 2}

# Limite de segurança - `manual_desenvolvimento_senior.md` proíbe devolver lista potencialmente
# ilimitada. O volume de hoje (milhares) já cabe dentro disso, mas "conforme o banco cresce" é
# exatamente o cenário que este limite existe para cobrir. NUNCA some em silêncio: os contadores
# de `StructureAuditOut` (critical_count/attention_count/informative_count/total_findings)
# sempre refletem o total real, mesmo quando `findings` é cortado por este limite.
#
# O corte é POR SEVERIDADE, não um corte global na lista já ordenada (achado real ao validar ao
# vivo: um corte global de "top N" com `critico` sempre primeiro deixava a severidade
# `informativo` inteira de fora sempre que `critico`+`atencao` já somavam mais que N - o filtro de
# severidade na tela mostrava "382" no card e "nenhum achado" na tabela ao filtrar por
# `informativo`. Cortar por severidade garante que toda severidade com achado real aparece com
# pelo menos uma amostra na lista, não só nos contadores.
MAX_FINDINGS_PER_SEVERITY = 700


def _finding(
    *,
    type: str,
    severity: str,
    description: str,
    entity_type: str,
    suggestion: str,
    blocks_capacity: bool,
    entity_id: int | None = None,
    regional: str | None = None,
    subject_name: str | None = None,
) -> StructureAuditFinding:
    return StructureAuditFinding(
        type=type,
        severity=severity,
        description=description,
        entity_type=entity_type,
        entity_id=entity_id,
        regional=regional,
        subject_name=subject_name,
        suggestion=suggestion,
        blocks_capacity=blocks_capacity,
    )


def _audit_collaborators(collaborators: list[Collaborator]) -> list[StructureAuditFinding]:
    findings: list[StructureAuditFinding] = []
    for collaborator in collaborators:
        regional = normalize_regional(collaborator.regional)

        # 1. Ativos sem vínculo com o funcionário do IXC - sem isso, O.S. e produção não têm como
        # ser casadas com precisão a este colaborador (só por nome, que pode divergir/ter typo).
        if collaborator.active and collaborator.ixc_employee_id is None:
            findings.append(
                _finding(
                    type="collaborator_without_ixc_id",
                    severity="atencao",
                    description=f'Colaborador "{collaborator.name}" está ativo mas não tem vínculo com o funcionário do IXC.',
                    entity_type="collaborator",
                    entity_id=collaborator.id,
                    regional=regional,
                    subject_name=collaborator.name,
                    suggestion="Vincular ao funcionário correspondente no IXC (busca por CPF em /admin, aba Convites).",
                    blocks_capacity=True,
                )
            )

        # 2. Sem CPF local - não bloqueia cálculo de capacidade (CPF não participa dessa conta),
        # mas é pré-requisito para o colaborador acessar o Portal.
        if not collaborator.cpf:
            findings.append(
                _finding(
                    type="collaborator_without_cpf",
                    severity="informativo",
                    description=f'Colaborador "{collaborator.name}" não tem CPF cadastrado localmente.',
                    entity_type="collaborator",
                    entity_id=collaborator.id,
                    regional=regional,
                    subject_name=collaborator.name,
                    suggestion="Cadastrar o CPF em /admin (aba Pessoas e estrutura) ou via sincronização com o IXC.",
                    blocks_capacity=False,
                )
            )

        # 3. Ativos sem tipo de equipe (mesmo campo já somado em /admin/people-structure).
        if collaborator.active and not collaborator.team_type:
            findings.append(
                _finding(
                    type="collaborator_without_team_type",
                    severity="atencao",
                    description=f'Colaborador "{collaborator.name}" está ativo mas não tem tipo de equipe definido.',
                    entity_type="collaborator",
                    entity_id=collaborator.id,
                    regional=regional,
                    subject_name=collaborator.name,
                    suggestion="Definir o tipo de equipe em /admin (aba Pessoas e estrutura).",
                    blocks_capacity=True,
                )
            )

        # 4. Campo, ativo, sem supervisor - mesmo recorte já usado em /admin/people-structure
        # (without_supervisor conta só team_type == "field").
        if collaborator.active and collaborator.team_type == "field" and collaborator.supervisor_user_id is None:
            findings.append(
                _finding(
                    type="collaborator_without_supervisor",
                    severity="atencao",
                    description=f'Colaborador de campo "{collaborator.name}" está ativo mas não tem supervisor vinculado.',
                    entity_type="collaborator",
                    entity_id=collaborator.id,
                    regional=regional,
                    subject_name=collaborator.name,
                    suggestion="Vincular um supervisor em /admin (aba Pessoas e estrutura) ou pela Gestão Integrada.",
                    blocks_capacity=True,
                )
            )
    return findings


def _audit_responsibles(db: Session, collaborators: list[Collaborator]) -> list[StructureAuditFinding]:
    findings: list[StructureAuditFinding] = []
    candidates = resolve_responsible_regional_candidates(db)

    # 5. Responsável da Operação (cadastro manual ou histórico de O.S.) sem `Collaborator`
    # correspondente - a produção existe, mas não há como atribuí-la a ninguém cadastrado.
    for candidate in candidates:
        collaborator = _find_collaborator(db, candidate.responsible_name, candidate.ixc_employee_id)
        if collaborator is None:
            findings.append(
                _finding(
                    type="responsible_without_collaborator",
                    severity="critico",
                    description=f'Responsável "{candidate.responsible_name}" tem produção registrada na Operação mas não tem colaborador correspondente cadastrado.',
                    entity_type="responsible_assignment",
                    regional=normalize_regional(candidate.regional),
                    subject_name=candidate.responsible_name,
                    suggestion="Cadastrar o colaborador em /admin ou corrigir o nome/vínculo IXC do responsável na Operação Analítica.",
                    blocks_capacity=True,
                )
            )

    # 6. Mesmo responsável com produção em mais de uma regional - a capacidade por regional
    # atribuiria a mesma pessoa duas vezes (ou de forma ambígua) sem uma decisão explícita.
    candidates_by_name: dict[str, list] = defaultdict(list)
    for candidate in candidates:
        candidates_by_name[_norm_name(candidate.responsible_name)].append(candidate)
    for group in candidates_by_name.values():
        distinct_regionals = sorted({normalize_regional(item.regional) for item in group})
        if len(distinct_regionals) > 1:
            findings.append(
                _finding(
                    type="responsible_multi_regional",
                    severity="atencao",
                    description=f'Responsável "{group[0].responsible_name}" tem produção em mais de uma regional: {", ".join(distinct_regionals)}.',
                    entity_type="responsible_assignment",
                    regional=", ".join(distinct_regionals),
                    subject_name=group[0].responsible_name,
                    suggestion="Confirmar em qual regional este responsável deve ser contado, ou registrar a mudança de base explicitamente.",
                    blocks_capacity=True,
                )
            )

    # 7. Regional oficial do colaborador (Collaborator.regional) diferente da regional
    # predominante das O.S. atribuídas a ele (via responsible_ixc_id).
    order_regional_counts = db.execute(
        select(
            OperationOrder.responsible_ixc_id,
            OperationOrder.regional,
            func.count().label("total"),
        )
        .where(OperationOrder.responsible_ixc_id.is_not(None))
        .where(OperationOrder.regional.is_not(None))
        .group_by(OperationOrder.responsible_ixc_id, OperationOrder.regional)
    ).all()
    counts_by_ixc_id: dict[int, dict[str, int]] = defaultdict(dict)
    for ixc_employee_id, regional, total in order_regional_counts:
        normalized = normalize_regional(regional)
        counts_by_ixc_id[ixc_employee_id][normalized] = counts_by_ixc_id[ixc_employee_id].get(normalized, 0) + total

    for collaborator in collaborators:
        if collaborator.ixc_employee_id is None:
            continue
        regional_counts = counts_by_ixc_id.get(collaborator.ixc_employee_id)
        if not regional_counts:
            continue
        predominant_regional = max(regional_counts.items(), key=lambda item: item[1])[0]
        official_regional = normalize_regional(collaborator.regional)
        if predominant_regional != official_regional:
            findings.append(
                _finding(
                    type="collaborator_regional_diverges_from_orders",
                    severity="atencao",
                    description=(
                        f'Colaborador "{collaborator.name}" está cadastrado na regional {official_regional}, '
                        f"mas a maior parte das O.S. atribuídas a ele foi registrada em {predominant_regional}."
                    ),
                    entity_type="collaborator",
                    entity_id=collaborator.id,
                    regional=official_regional,
                    subject_name=collaborator.name,
                    suggestion="Confirmar a regional oficial do colaborador em /admin (mudança de base real ou erro de cadastro).",
                    blocks_capacity=True,
                )
            )
    return findings


def _audit_team_models(members: list[ManagementOperationalMember], assignments: list[OperationResponsibleAssignment], team_models_by_id: dict[int, OperationTeamModel]) -> list[StructureAuditFinding]:
    findings: list[StructureAuditFinding] = []

    # 8. Membro ativo sem modelo de equipe.
    for member in members:
        if member.is_active and member.team_model_id is None:
            findings.append(
                _finding(
                    type="member_without_team_model",
                    severity="atencao",
                    description=f'Membro "{member.responsible_name}" está ativo na Gestão Integrada mas não tem modelo de equipe definido.',
                    entity_type="operational_member",
                    entity_id=member.id,
                    regional=normalize_regional(member.regional),
                    subject_name=member.responsible_name,
                    suggestion="Definir o modelo de equipe na Gestão Integrada (aba Estrutura operacional).",
                    blocks_capacity=True,
                )
            )

    # 9. Modelo de equipe inativo ainda referenciado por membro ativo ou cadastro manual.
    inactive_ids_in_use: set[int] = set()
    for member in members:
        if member.is_active and member.team_model_id is not None:
            model = team_models_by_id.get(member.team_model_id)
            if model is not None and not model.active:
                inactive_ids_in_use.add(model.id)
    for assignment in assignments:
        if assignment.team_model_id is not None:
            model = team_models_by_id.get(assignment.team_model_id)
            if model is not None and not model.active:
                inactive_ids_in_use.add(model.id)
    for model_id in sorted(inactive_ids_in_use):
        model = team_models_by_id[model_id]
        findings.append(
            _finding(
                type="team_model_inactive_still_used",
                severity="critico",
                description=f'Modelo de equipe "{model.name}" está inativo mas ainda é usado por colaboradores/cadastros ativos.',
                entity_type="team_model",
                entity_id=model.id,
                subject_name=model.name,
                suggestion="Reativar o modelo de equipe ou migrar os colaboradores/cadastros vinculados para outro modelo.",
                blocks_capacity=True,
            )
        )
    return findings


def _audit_branch_capacity(
    collaborators: list[Collaborator],
    members: list[ManagementOperationalMember],
    branch_capacities: list[OperationBranchCapacity],
) -> list[StructureAuditFinding]:
    findings: list[StructureAuditFinding] = []
    branch_capacity_by_regional = {normalize_regional(item.regional): item for item in branch_capacities}

    active_regionals: set[str] = set()
    for collaborator in collaborators:
        if collaborator.active:
            active_regionals.add(normalize_regional(collaborator.regional))
    for member in members:
        if member.is_active:
            active_regionals.add(normalize_regional(member.regional))
    active_regionals.discard("NAO IDENTIFICADO")

    # 10. Regional com colaborador/membro ativo mas sem linha de capacidade configurada -
    # sem essa linha não há como calcular percentual de capacidade nenhum pra ela (ver
    # OperationBranchCapacity, docstring do model).
    for regional in sorted(active_regionals):
        if regional not in branch_capacity_by_regional:
            findings.append(
                _finding(
                    type="regional_without_branch_capacity",
                    severity="atencao",
                    description=f"Regional {regional} tem colaboradores/estrutura ativos mas não tem capacidade configurada.",
                    entity_type="branch_capacity",
                    regional=regional,
                    suggestion="Configurar os limiares de capacidade da filial na Operação Analítica.",
                    blocks_capacity=True,
                )
            )

    # 11. Capacidade configurada mas com limiar zerado, ausente ou fora de ordem (bom < ótimo <
    # excelente é a premissa do indicador - ver OperationBranchCapacity.docstring).
    for capacity in branch_capacities:
        regional = normalize_regional(capacity.regional)
        thresholds_present = capacity.good_threshold > 0 and capacity.great_threshold > 0 and capacity.excellent_threshold > 0
        thresholds_ordered = capacity.good_threshold < capacity.great_threshold < capacity.excellent_threshold
        if not thresholds_present or not thresholds_ordered:
            findings.append(
                _finding(
                    type="branch_capacity_invalid_thresholds",
                    severity="critico",
                    description=f"Capacidade da regional {regional} tem limiares zerados, ausentes ou fora de ordem (bom/ótimo/excelente).",
                    entity_type="branch_capacity",
                    entity_id=capacity.id,
                    regional=regional,
                    suggestion="Corrigir os limiares na configuração de capacidade da filial (bom < ótimo < excelente, todos maiores que zero).",
                    blocks_capacity=True,
                )
            )
    return findings


def _audit_management_members(members: list[ManagementOperationalMember]) -> list[StructureAuditFinding]:
    findings: list[StructureAuditFinding] = []
    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(days=RECENT_PRODUCTION_DAYS)

    for member in members:
        # 12. Pendente de validação operacional.
        if member.status == "pending_validation":
            findings.append(
                _finding(
                    type="member_pending_validation",
                    severity="atencao",
                    description=f'Membro "{member.responsible_name}" está pendente de validação operacional na Gestão Integrada.',
                    entity_type="operational_member",
                    entity_id=member.id,
                    regional=normalize_regional(member.regional),
                    subject_name=member.responsible_name,
                    suggestion="Validar o cadastro na Gestão Integrada (aba Estrutura operacional).",
                    blocks_capacity=False,
                )
            )

        # 13. Produção recente (últimos 30 dias) mas status estrutural ainda pendente - é a
        # pessoa que já está trabalhando sem a estrutura resolvida, o achado mais acionável.
        last_order_at = member.last_order_at
        if last_order_at is not None and last_order_at.tzinfo is None:
            last_order_at = last_order_at.replace(tzinfo=timezone.utc)
        if last_order_at is not None and last_order_at >= recent_cutoff and member.status in _PENDING_STRUCTURE_STATUSES:
            findings.append(
                _finding(
                    type="recent_production_pending_structure",
                    severity="critico",
                    description=f'Membro "{member.responsible_name}" teve produção nos últimos {RECENT_PRODUCTION_DAYS} dias mas continua com status estrutural pendente ({member.status}).',
                    entity_type="operational_member",
                    entity_id=member.id,
                    regional=normalize_regional(member.regional),
                    subject_name=member.responsible_name,
                    suggestion="Priorizar a validação deste membro na Gestão Integrada - produção real já está acontecendo sem estrutura resolvida.",
                    blocks_capacity=True,
                )
            )
    return findings


def run_structure_audit(db: Session) -> StructureAuditOut:
    """Ponto de entrada único da auditoria - lê tudo localmente (sem chamar a API do IXC), monta a
    lista de achados e o resumo geral. Não grava nada no banco."""
    now = datetime.now(timezone.utc)

    collaborators = list(db.scalars(select(Collaborator)))
    team_models = list(db.scalars(select(OperationTeamModel)))
    team_models_by_id = {model.id: model for model in team_models}
    assignments = list(db.scalars(select(OperationResponsibleAssignment)))
    branch_capacities = list(db.scalars(select(OperationBranchCapacity)))
    members = list(db.scalars(select(ManagementOperationalMember).options(selectinload(ManagementOperationalMember.collaborator))))

    findings: list[StructureAuditFinding] = []
    findings.extend(_audit_collaborators(collaborators))
    findings.extend(_audit_responsibles(db, collaborators))
    findings.extend(_audit_team_models(members, assignments, team_models_by_id))
    findings.extend(_audit_branch_capacity(collaborators, members, branch_capacities))
    findings.extend(_audit_management_members(members))

    findings.sort(key=lambda item: (_SEVERITY_RANK.get(item.severity, 99), item.type, item.regional or "", item.subject_name or ""))
    total_findings = len(findings)
    critical_count = sum(1 for item in findings if item.severity == "critico")
    attention_count = sum(1 for item in findings if item.severity == "atencao")
    informative_count = sum(1 for item in findings if item.severity == "informativo")

    # Corte por severidade (ver MAX_FINDINGS_PER_SEVERITY acima) - preserva a ordem já definida
    # (severidade, tipo, regional, nome) dentro de cada grupo.
    returned_findings: list[StructureAuditFinding] = []
    for severity in ("critico", "atencao", "informativo"):
        returned_findings.extend([item for item in findings if item.severity == severity][:MAX_FINDINGS_PER_SEVERITY])
    findings = returned_findings

    summary = StructureAuditSummary(
        total_collaborators=len(collaborators),
        active_collaborators=sum(1 for item in collaborators if item.active),
        collaborators_with_ixc_id=sum(1 for item in collaborators if item.ixc_employee_id is not None),
        collaborators_with_cpf=sum(1 for item in collaborators if item.cpf),
        active_collaborators_without_team_type=sum(1 for item in collaborators if item.active and not item.team_type),
        responsible_assignments=len(assignments),
        responsible_assignments_with_team_model=sum(1 for item in assignments if item.team_model_id is not None),
        branch_capacity_rows=len(branch_capacities),
        management_members=len(members),
        management_members_with_team_model=sum(1 for item in members if item.team_model_id is not None),
    )

    return StructureAuditOut(
        summary=summary,
        findings=findings,
        critical_count=critical_count,
        attention_count=attention_count,
        informative_count=informative_count,
        total_findings=total_findings,
        generated_at=now,
    )
