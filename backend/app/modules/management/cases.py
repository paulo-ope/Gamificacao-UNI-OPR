"""Motor de casos de gestão: detecção de desvio, ciclo de vida e escopo de visibilidade.

Um "caso" é uma cobrança formal da matriz sobre um desvio operacional. Ele nasce de duas formas:

- **Automática** (`generate_performance_cases`): varre um mês fechado e abre um caso para cada
  colaborador que ficou abaixo da meta diária do seu modelo de equipe. O comparativo é
  `média diária realizada` vs `OperationTeamModel.daily_target` - a mesma régua que o calendário
  de performance da Operação Analítica já usa na tela, para o número cobrado ser o mesmo número
  que o supervisor vê lá.
- **Manual**: a matriz abre o caso pela tela quando o desvio não é de produtividade (conduta,
  processo, retrabalho) - por isso `metric_name` é texto livre, não um enum.

Decisão de agregação: a média diária divide pelos **dias efetivamente trabalhados** (dias com ao
menos uma O.S. fechada), não pelos dias corridos do mês. Sem isso, férias/afastamento/admissão no
meio do mês viram desvio de produtividade e o caso nasce errado - o supervisor perde a confiança na
ferramenta logo no primeiro mês. Em compensação, exige-se um mínimo de dias trabalhados
(`management_case_min_days_worked`) para a média significar alguma coisa.

O status `overdue` do vocabulário NÃO é gravado: ele é derivado na leitura (`is_overdue`) a partir
de `due_date` vs hoje. Gravar exigiria uma varredura periódica que ficaria errada entre execuções.
"""

from __future__ import annotations

import calendar as calendar_module
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import AppSetting, User
from app.modules.management.models import (
    MANAGEMENT_CASE_STATUSES,
    OPEN_CASE_STATUSES,
    ManagementCase,
    ManagementCaseComment,
    ManagementCaseReason,
    ManagementOperationalMember,
)
from app.modules.management.schemas import ManagementCaseOut
from app.modules.operations.models import OperationOrder, OperationTeamModel

# Importa o helper de data local da Operação Analítica de propósito: ele encapsula a aritmética de
# fuso que difere entre PostgreSQL (produção) e SQLite (testes). Reimplementar aqui significaria
# duas verdades sobre "que dia essa O.S. fechou" - exatamente o tipo de divergência que faria o caso
# gerado não bater com o calendário que o supervisor abre para conferir.
from app.modules.operations.queries import _local_closed_date
from app.services.regional import effective_managed_regionals, normalize_regional

CASE_TYPE_PRODUCTIVITY = "productivity_below_target"
METRIC_DAILY_AVERAGE = "Média diária de O.S. concluídas"

# Caso de um único dia "abaixo da meta" (vermelho no drill do calendário) - diferente do caso
# mensal (`CASE_TYPE_PRODUCTIVITY`), que só olha a média do mês fechado. Aberto sob demanda quando
# o supervisor clica em "Justificar" num dia vermelho, não por varredura em lote.
CASE_TYPE_DAILY_BELOW = "daily_performance_below_target"
METRIC_DAILY_COUNT = "O.S. concluídas no dia"

DEFAULT_SETTINGS = {
    # Desvio percentual mínimo abaixo da meta para abrir caso. 15% evita transformar ruído normal
    # de operação (4,3 de 5) em cobrança formal.
    "management_case_min_deviation_pct": "15",
    # A partir daqui o caso nasce com severidade alta.
    "management_case_high_severity_pct": "35",
    # Abaixo de `min_deviation_pct` não há caso; entre ele e este valor a severidade é baixa.
    "management_case_low_severity_pct": "25",
    # Mínimo de dias trabalhados no mês para a média diária ser estatisticamente honesta.
    "management_case_min_days_worked": "5",
    # Prazo (dias corridos) que o supervisor tem para justificar, contado da abertura do caso.
    "management_case_due_days": "7",
}

# Motivos que a operação usa no dia a dia. Semeados na primeira leitura para a tela nunca abrir com
# o combo vazio (o fluxo de justificativa fica inutilizável sem pelo menos um motivo).
DEFAULT_CASE_REASONS = (
    ("Ausência / afastamento", "Férias, atestado, folga ou afastamento no período.", False),
    ("Equipe incompleta", "Faltou dupla, veículo ou equipamento para executar a meta.", True),
    ("Deslocamento atípico", "Área de atendimento distante ou rota fora do padrão da regional.", True),
    ("Complexidade das O.S.", "Serviços do período exigiram tempo acima do previsto no modelo.", True),
    ("Falha de sistema / rede", "Indisponibilidade de sistema, estoque ou infraestrutura.", True),
    ("Apoio a outra frente", "Colaborador alocado em projeto, treinamento ou apoio a outra equipe.", True),
    ("Desempenho individual", "Sem causa externa identificada - exige plano de ação.", True),
    ("Outro", "Motivo não previsto na lista - descreva na justificativa.", True),
)


def load_settings(db: Session) -> dict[str, str]:
    rows = db.execute(select(AppSetting).where(AppSetting.key.in_(DEFAULT_SETTINGS.keys()))).scalars()
    stored = {row.key: row.value for row in rows}
    return {**DEFAULT_SETTINGS, **stored}


def save_settings(db: Session, values: dict[str, str]) -> dict[str, str]:
    for key, value in values.items():
        if key not in DEFAULT_SETTINGS:
            continue
        row = db.execute(select(AppSetting).where(AppSetting.key == key)).scalar_one_or_none()
        if row:
            row.value = str(value)
        else:
            db.add(AppSetting(key=key, value=str(value), description="Configuração do módulo de Gestão Integrada."))
    db.commit()
    return load_settings(db)


def _setting_float(settings: dict[str, str], key: str) -> float:
    try:
        return float(settings[key])
    except (KeyError, TypeError, ValueError):
        return float(DEFAULT_SETTINGS[key])


def seed_default_reasons(db: Session) -> int:
    """Garante os motivos padrão. Idempotente: só insere o que falta, nunca reescreve o que a
    matriz já editou."""
    existing = {name for (name,) in db.execute(select(ManagementCaseReason.name))}
    created = 0
    for name, description, requires_description in DEFAULT_CASE_REASONS:
        if name in existing:
            continue
        db.add(ManagementCaseReason(name=name, description=description, requires_description=requires_description, active=True))
        created += 1
    if created:
        db.flush()
    return created


def _norm(value: str | None) -> str:
    return " ".join((value or "").strip().casefold().split())


def _as_date(value) -> date | None:
    """A data local de fechamento volta como `date` no PostgreSQL e como texto no SQLite (testes)."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def is_overdue(item: ManagementCase, today: date | None = None) -> bool:
    if item.due_date is None or item.status not in OPEN_CASE_STATUSES:
        return False
    return item.due_date < (today or date.today())


def severity_for(deviation_pct: float, settings: dict[str, str]) -> str:
    high = _setting_float(settings, "management_case_high_severity_pct")
    low = _setting_float(settings, "management_case_low_severity_pct")
    if deviation_pct >= high:
        return "high"
    if deviation_pct >= low:
        return "medium"
    return "low"


def generate_performance_cases(
    db: Session,
    *,
    year: int,
    month: int,
    created_by: int | None = None,
) -> dict:
    """Abre casos de produtividade para o mês informado.

    Idempotente por (tipo, responsável, regional, competência): rodar duas vezes no mesmo mês não
    duplica caso. Um caso já existente não é reaberto nem tem os valores reescritos - se a matriz já
    resolveu, resolvido fica; o histórico do que foi cobrado na época é o registro.
    """
    settings = load_settings(db)
    min_deviation = _setting_float(settings, "management_case_min_deviation_pct")
    min_days_worked = int(_setting_float(settings, "management_case_min_days_worked"))
    due_days = int(_setting_float(settings, "management_case_due_days"))

    month_start = date(year, month, 1)
    month_end = date(year, month, calendar_module.monthrange(year, month)[1])
    # A competência é um recorte de dias LOCAIS (Rondônia, UTC-4), mas `closed_at` é gravado em UTC.
    # A janela SQL é alargada em um dia de cada lado e o recorte exato é aplicado depois sobre a
    # data local já convertida - sem isso, as O.S. fechadas nas últimas 4h do último dia do mês
    # (que em UTC já caem no mês seguinte) ficariam de fora e o colaborador apareceria produzindo
    # menos do que produziu, gerando caso indevido.
    start = datetime(month_start.year, month_start.month, month_start.day, tzinfo=timezone.utc) - timedelta(days=1)
    end = datetime(month_end.year, month_end.month, month_end.day, 23, 59, 59, tzinfo=timezone.utc) + timedelta(days=1)

    closed_day = _local_closed_date(db)
    rows = db.execute(
        select(
            OperationOrder.responsible,
            OperationOrder.regional,
            closed_day,
            func.count(OperationOrder.id),
        )
        .where(
            OperationOrder.closed_at.is_not(None),
            OperationOrder.closed_at.between(start, end),
            OperationOrder.responsible.is_not(None),
            OperationOrder.responsible != "",
        )
        .group_by(OperationOrder.responsible, OperationOrder.regional, closed_day)
    ).all()

    # (nome normalizado, regional normalizada) -> {"total": n de O.S., "days": n de dias com O.S.}
    produced: dict[tuple[str, str], dict] = {}
    for responsible, regional, day, quantity in rows:
        local_day = _as_date(day)
        if local_day is None or local_day < month_start or local_day > month_end:
            continue
        key = (_norm(responsible), _norm(normalize_regional(str(regional or ""))))
        bucket = produced.setdefault(key, {"total": 0, "days": 0})
        bucket["total"] += int(quantity or 0)
        bucket["days"] += 1

    members = db.scalars(
        select(ManagementOperationalMember).where(
            ManagementOperationalMember.is_active.is_(True),
            ManagementOperationalMember.team_model_id.is_not(None),
            ManagementOperationalMember.status.not_in(("outside_operation", "inactive")),
        )
    ).all()
    team_models = {model.id: model for model in db.scalars(select(OperationTeamModel)).all()}

    existing_keys = {
        (case_type, _norm(responsible_name), _norm(regional))
        for case_type, responsible_name, regional in db.execute(
            select(ManagementCase.case_type, ManagementCase.responsible_name, ManagementCase.regional).where(
                ManagementCase.case_type == CASE_TYPE_PRODUCTIVITY,
                ManagementCase.reference_year == year,
                ManagementCase.reference_month == month,
            )
        )
    }

    created = 0
    skipped_existing = 0
    skipped_insufficient_data = 0
    evaluated = 0

    for member in members:
        model = team_models.get(member.team_model_id)
        if model is None or not model.daily_target:
            continue
        key = (_norm(member.responsible_name), _norm(member.regional))
        bucket = produced.get(key)
        if bucket is None or bucket["days"] < min_days_worked:
            skipped_insufficient_data += 1
            continue
        evaluated += 1
        expected = float(model.daily_target)
        actual = bucket["total"] / bucket["days"]
        if actual >= expected:
            continue
        deviation_pct = (expected - actual) / expected * 100
        if deviation_pct < min_deviation:
            continue
        if (CASE_TYPE_PRODUCTIVITY, key[0], key[1]) in existing_keys:
            skipped_existing += 1
            continue
        db.add(
            ManagementCase(
                case_type=CASE_TYPE_PRODUCTIVITY,
                source_module="operations",
                reference_date=month_end,
                reference_month=month,
                reference_year=year,
                regional=member.regional,
                collaborator_id=member.collaborator_id,
                responsible_name=member.responsible_name,
                supervisor_user_id=member.supervisor_user_id,
                team_model_id=member.team_model_id,
                metric_name=METRIC_DAILY_AVERAGE,
                expected_value=round(expected, 2),
                actual_value=round(actual, 2),
                deviation_value=round(deviation_pct, 1),
                severity=severity_for(deviation_pct, settings),
                status="pending",
                due_date=date.today() + timedelta(days=due_days),
                created_by=created_by,
            )
        )
        created += 1

    db.flush()
    return {
        "created_cases": created,
        "evaluated_members": evaluated,
        "skipped_existing": skipped_existing,
        "skipped_insufficient_data": skipped_insufficient_data,
        "reference_year": year,
        "reference_month": month,
    }


def get_or_create_daily_case(
    db: Session,
    *,
    responsible_name: str,
    regional: str,
    reference_date: date,
    expected_value: float | None,
    actual_value: float,
    created_by: int | None = None,
) -> tuple[ManagementCase, bool]:
    """Abre (ou devolve, se já existir) o caso de um dia específico marcado abaixo da meta no
    drill do calendário. Idempotente por (tipo, responsável, regional, data) - clicar em
    "Justificar" duas vezes no mesmo dia não duplica caso, só devolve o que já existe (podendo já
    estar justificado ou até resolvido). Devolve `(caso, foi_criado_agora)` - o chamador usa o
    segundo valor pra so registrar auditoria/side-effects na primeira vez.

    Diferente de `generate_performance_cases` (varredura em lote do mês fechado), este é criado
    sob demanda, um dia de cada vez, a partir do que o supervisor está vendo no drill."""
    normalized_regional = normalize_regional(regional)
    target_key = (_norm(responsible_name), _norm(normalized_regional))
    # Compara em Python (via `_norm`, que casefold + colapsa espaços) em vez de SQL - mesmo
    # criterio de idempotencia que `generate_performance_cases` ja usa para este mesmo par de
    # campos, para as duas formas de abrir caso nunca divergirem sobre o que conta como "o mesmo"
    # responsavel/regional.
    same_day_cases = db.scalars(
        select(ManagementCase).where(
            ManagementCase.case_type == CASE_TYPE_DAILY_BELOW,
            ManagementCase.reference_date == reference_date,
        )
    ).all()
    for candidate in same_day_cases:
        if (_norm(candidate.responsible_name), _norm(candidate.regional)) == target_key:
            return candidate, False

    settings = load_settings(db)
    due_days = int(_setting_float(settings, "management_case_due_days"))
    deviation_pct = None
    severity = "medium"
    if expected_value:
        deviation_pct = round(max(0.0, (expected_value - actual_value) / expected_value * 100), 1)
        severity = severity_for(deviation_pct, settings)

    member = next(
        (
            candidate
            for candidate in db.scalars(select(ManagementOperationalMember)).all()
            if (_norm(candidate.responsible_name), _norm(candidate.regional)) == target_key
        ),
        None,
    )

    item = ManagementCase(
        case_type=CASE_TYPE_DAILY_BELOW,
        source_module="operations_calendar",
        reference_date=reference_date,
        reference_month=reference_date.month,
        reference_year=reference_date.year,
        regional=normalized_regional,
        collaborator_id=member.collaborator_id if member else None,
        responsible_name=responsible_name,
        supervisor_user_id=member.supervisor_user_id if member else None,
        team_model_id=member.team_model_id if member else None,
        metric_name=METRIC_DAILY_COUNT,
        expected_value=expected_value,
        actual_value=actual_value,
        deviation_value=deviation_pct,
        severity=severity,
        status="pending",
        due_date=date.today() + timedelta(days=due_days),
        created_by=created_by,
    )
    db.add(item)
    db.flush()
    return item, True


# --- Escopo de visibilidade -------------------------------------------------------------------
#
# Regra de produto: o supervisor só enxerga o que é dele. Sem isso, dar
# `management:write_justification` a um perfil operacional exporia a operação inteira da empresa
# para qualquer supervisor de regional.


def can_review(user: User) -> bool:
    from app.core.security import permissions_for_user

    return "management:review" in permissions_for_user(user)


def case_scope_conditions(user: User) -> list:
    """Condições SQL que limitam os casos visíveis ao usuário.

    Quem tem `management:review` (matriz) enxerga tudo. Os demais enxergam os casos em que são o
    supervisor responsável, mais os casos das regionais que gerenciam.
    """
    if can_review(user):
        return []
    allowed_regionals = effective_managed_regionals(user.managed_regional, user.managed_regionals)
    visibility = [ManagementCase.supervisor_user_id == user.id]
    if allowed_regionals:
        visibility.append(ManagementCase.regional.in_(allowed_regionals))
    return [or_(*visibility)]


def member_scope_conditions(user: User) -> list:
    """Mesma regra do escopo de casos, aplicada à estrutura operacional."""
    if can_review(user):
        return []
    allowed_regionals = effective_managed_regionals(user.managed_regional, user.managed_regionals)
    visibility = [ManagementOperationalMember.supervisor_user_id == user.id]
    if allowed_regionals:
        visibility.append(ManagementOperationalMember.regional.in_(allowed_regionals))
    return [or_(*visibility)]


@dataclass
class ManagementCaseFilters:
    status: str | None = None
    severity: str | None = None
    regional: str | None = None
    supervisor_user_id: int | None = None
    case_type: str | None = None
    reference_year: int | None = None
    reference_month: int | None = None
    only_overdue: bool = False
    search: str | None = None
    statuses: list[str] = field(default_factory=list)


def case_filter_conditions(filters: ManagementCaseFilters) -> list:
    conditions: list = []
    if filters.status:
        conditions.append(ManagementCase.status == filters.status)
    if filters.statuses:
        conditions.append(ManagementCase.status.in_(filters.statuses))
    if filters.severity:
        conditions.append(ManagementCase.severity == filters.severity)
    if filters.regional:
        conditions.append(ManagementCase.regional == normalize_regional(filters.regional))
    if filters.supervisor_user_id:
        conditions.append(ManagementCase.supervisor_user_id == filters.supervisor_user_id)
    if filters.case_type:
        conditions.append(ManagementCase.case_type == filters.case_type)
    if filters.reference_year:
        conditions.append(ManagementCase.reference_year == filters.reference_year)
    if filters.reference_month:
        conditions.append(ManagementCase.reference_month == filters.reference_month)
    if filters.only_overdue:
        conditions.append(ManagementCase.status.in_(OPEN_CASE_STATUSES))
        conditions.append(ManagementCase.due_date.is_not(None))
        conditions.append(ManagementCase.due_date < date.today())
    if filters.search:
        pattern = f"%{filters.search.strip()}%"
        conditions.append(
            or_(
                ManagementCase.responsible_name.ilike(pattern),
                ManagementCase.regional.ilike(pattern),
                ManagementCase.metric_name.ilike(pattern),
            )
        )
    return conditions


def case_out(item: ManagementCase, *, comment_count: int = 0) -> ManagementCaseOut:
    return ManagementCaseOut(
        id=item.id,
        case_type=item.case_type,
        source_module=item.source_module,
        reference_date=item.reference_date,
        reference_month=item.reference_month,
        reference_year=item.reference_year,
        regional=item.regional,
        collaborator_id=item.collaborator_id,
        collaborator_name=item.collaborator.name if item.collaborator else None,
        responsible_name=item.responsible_name,
        supervisor_user_id=item.supervisor_user_id,
        supervisor_name=item.supervisor.name if item.supervisor else None,
        team_model_id=item.team_model_id,
        team_model_name=item.team_model.name if item.team_model else None,
        metric_name=item.metric_name,
        expected_value=item.expected_value,
        actual_value=item.actual_value,
        deviation_value=item.deviation_value,
        severity=item.severity,
        status=item.status,
        is_overdue=is_overdue(item),
        reason_id=item.reason_id,
        reason_name=item.reason.name if item.reason else None,
        justification_text=item.justification_text,
        action_plan=item.action_plan,
        due_date=item.due_date,
        comment_count=comment_count,
        created_at=item.created_at,
        updated_at=item.updated_at,
        justified_at=item.justified_at,
        reviewed_by=item.reviewed_by,
        reviewed_at=item.reviewed_at,
    )


def comment_counts(db: Session, case_ids: list[int]) -> dict[int, int]:
    if not case_ids:
        return {}
    rows = db.execute(
        select(ManagementCaseComment.case_id, func.count(ManagementCaseComment.id))
        .where(ManagementCaseComment.case_id.in_(case_ids))
        .group_by(ManagementCaseComment.case_id)
    ).all()
    return {case_id: int(total) for case_id, total in rows}


def summarize_cases(db: Session, base_conditions: list) -> dict:
    """Contadores do painel de casos, sempre sob o MESMO recorte da lista - números que não batem
    com a tabela logo abaixo destroem a confiança no painel."""
    today = date.today()
    rows = db.execute(
        select(ManagementCase.status, ManagementCase.severity, ManagementCase.due_date).where(*base_conditions)
    ).all()
    total = len(rows)
    open_cases = sum(1 for status, _, _ in rows if status in OPEN_CASE_STATUSES)
    pending = sum(1 for status, _, _ in rows if status == "pending")
    justified = sum(1 for status, _, _ in rows if status == "justified")
    resolved = sum(1 for status, _, _ in rows if status == "resolved")
    overdue = sum(
        1 for status, _, due_date in rows if status in OPEN_CASE_STATUSES and due_date is not None and due_date < today
    )
    high_severity = sum(1 for status, severity, _ in rows if severity == "high" and status in OPEN_CASE_STATUSES)
    return {
        "total_cases": total,
        "open_cases": open_cases,
        "pending_cases": pending,
        "justified_cases": justified,
        "resolved_cases": resolved,
        "overdue_cases": overdue,
        "high_severity_open": high_severity,
    }


def validate_case_status(value: str) -> str:
    if value not in MANAGEMENT_CASE_STATUSES:
        raise ValueError(f"Status de caso inválido: {value!r}.")
    return value
