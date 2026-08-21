"""Motor de casos de gestão: detecção de desvio, ciclo de vida e escopo de visibilidade.

Um "caso" é uma cobrança formal da matriz sobre um desvio operacional. Ele nasce de duas formas:

- **Automática** (`generate_performance_cases`): varre um mês fechado e abre um caso para cada
  colaborador que ficou abaixo da meta diária do seu modelo de equipe. O comparativo é
  `média diária realizada` vs `OperationTeamModel.median_from_quantity` (o piso da faixa "boa",
  não o teto que separa "boa" de "excelente") - decisão do usuário em 2026-08-20, pra não cobrar
  como se a régua fosse a performance excelente.
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
# gerado não bater com o calendário que o supervisor acessa para conferir.
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
        if model is None or not model.median_from_quantity:
            continue
        key = (_norm(member.responsible_name), _norm(member.regional))
        bucket = produced.get(key)
        if bucket is None or bucket["days"] < min_days_worked:
            skipped_insufficient_data += 1
            continue
        evaluated += 1
        # "Esperado" usa o piso da faixa "boa" (median_from_quantity), não o teto do modelo
        # (daily_target/target_quantity, que separa "boa" de "excelente") - decisão do usuário em
        # 2026-08-20: cobrar como se o piso da média fosse a régua justa, não a régua da
        # performance excelente, que inflava desvio e severidade de quem só estava "na média".
        expected = float(model.median_from_quantity)
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


def _resolve_member_for_case(db: Session, responsible_name: str) -> ManagementOperationalMember | None:
    """Acha o `ManagementOperationalMember` de uma pessoa só pelo NOME - não pela regional que a
    tela de origem (calendário) estava mostrando no momento do clique. Achado real da auditoria de
    2026-08-21: casar por (nome, regional recebida) fazia o caso nascer sem member/collaborator_id/
    supervisor_user_id sempre que a regional do calendário divergia da regional canônica do membro
    (ex.: pessoa com cadastro manual numa regional mas histórico de O.S. recente noutra).

    Uma pessoa pode ter mais de uma linha (uma por regional em que teve cadastro/atividade, ver
    `resolve_responsible_regional_candidates`) - entre elas, prioriza a que vem de cadastro manual
    (`source="assignment"`) sobre a inferida por histórico de O.S.; entre iguais, a mais recente
    por `last_order_at`."""
    normalized_name = _norm(responsible_name)
    candidates = [
        candidate
        for candidate in db.scalars(select(ManagementOperationalMember)).all()
        if _norm(candidate.responsible_name) == normalized_name
    ]
    if not candidates:
        return None

    def sort_key(candidate: ManagementOperationalMember) -> tuple[int, float]:
        is_manual = 0 if candidate.source == "assignment" else 1
        recency = -(candidate.last_order_at.timestamp() if candidate.last_order_at else 0)
        return (is_manual, recency)

    candidates.sort(key=sort_key)
    return candidates[0]


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
    # Regional CANÔNICA (do membro, quando existir) em vez da regional que o calendário estava
    # mostrando no clique - decisão do usuário em 2026-08-21: o caso reflete a regional oficial do
    # colaborador, mesmo que divirja do que a tela de origem exibia naquele momento (ver
    # generic-riding-petal.md, Fase 3). A idempotência abaixo usa a mesma chave canônica, então
    # duas aberturas da mesma pessoa/dia nunca duplicam caso só por causa de drift na tela.
    member = _resolve_member_for_case(db, responsible_name)
    canonical_regional = member.regional if member else normalize_regional(regional)
    target_key = (_norm(responsible_name), _norm(canonical_regional))
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

    item = ManagementCase(
        case_type=CASE_TYPE_DAILY_BELOW,
        source_module="operations_calendar",
        reference_date=reference_date,
        reference_month=reference_date.month,
        reference_year=reference_date.year,
        regional=canonical_regional,
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


def get_or_create_monthly_case(
    db: Session,
    *,
    responsible_name: str,
    regional: str,
    reference_year: int,
    reference_month: int,
    expected_value: float | None,
    actual_value: float,
    created_by: int | None = None,
) -> tuple[ManagementCase, bool]:
    """Abre (ou devolve, se já existir) o caso mensal de produtividade de UM colaborador, sob
    demanda, a partir do detalhe mensal do calendário - mesmo espírito de `get_or_create_daily_case`,
    mas para `CASE_TYPE_PRODUCTIVITY`. Antes desta função, o caso mensal só nascia em lote (clique
    em "Gerar casos do mês" pela matriz, ou o loop automático) - não havia como abrir o caso de UM
    colaborador específico direto de onde o supervisor já está vendo o desvio.

    `reference_year`/`reference_month` precisam ser um mês já fechado (mês corrente em diante é
    rejeitado pelo chamador antes de chegar aqui - ver router). Idempotente pela MESMA chave de
    `generate_performance_cases` (tipo, responsável normalizado, regional normalizada,
    competência): rodar a geração em lote depois de um caso já aberto por aqui nunca duplica, e
    vice-versa."""
    # Ver comentário equivalente em `get_or_create_daily_case` - regional canônica do membro em
    # vez da regional que o calendário mostrava no clique.
    member = _resolve_member_for_case(db, responsible_name)
    canonical_regional = member.regional if member else normalize_regional(regional)
    target_key = (_norm(responsible_name), _norm(canonical_regional))
    same_month_cases = db.scalars(
        select(ManagementCase).where(
            ManagementCase.case_type == CASE_TYPE_PRODUCTIVITY,
            ManagementCase.reference_year == reference_year,
            ManagementCase.reference_month == reference_month,
        )
    ).all()
    for candidate in same_month_cases:
        if (_norm(candidate.responsible_name), _norm(candidate.regional)) == target_key:
            return candidate, False

    settings = load_settings(db)
    due_days = int(_setting_float(settings, "management_case_due_days"))
    deviation_pct = None
    severity = "medium"
    if expected_value:
        deviation_pct = round(max(0.0, (expected_value - actual_value) / expected_value * 100), 1)
        severity = severity_for(deviation_pct, settings)

    month_end = date(reference_year, reference_month, calendar_module.monthrange(reference_year, reference_month)[1])
    item = ManagementCase(
        case_type=CASE_TYPE_PRODUCTIVITY,
        source_module="operations_calendar",
        reference_date=month_end,
        reference_month=reference_month,
        reference_year=reference_year,
        regional=canonical_regional,
        collaborator_id=member.collaborator_id if member else None,
        responsible_name=responsible_name,
        supervisor_user_id=member.supervisor_user_id if member else None,
        team_model_id=member.team_model_id if member else None,
        metric_name=METRIC_DAILY_AVERAGE,
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


def _team_model_dict(model: OperationTeamModel) -> dict:
    """Serializa só o que `classify_daily_performance` precisa - a mesma forma que
    `operations.services.monthly_calendar` monta para o calendário, para as duas nunca lerem os
    campos de jeitos diferentes."""
    return {
        "daily_target": model.daily_target,
        "median_from_quantity": model.median_from_quantity,
        "good_from_quantity": model.good_from_quantity,
        "target_rules": [
            {
                "period_type": rule.period_type,
                "enabled": rule.enabled,
                "median_from_quantity": rule.median_from_quantity,
                "good_from_quantity": rule.good_from_quantity,
                "target_quantity": rule.target_quantity,
            }
            for rule in model.target_rules
        ],
    }


def _rule_for_day(model_dict: dict, day: date) -> dict | None:
    """Regra de meta aplicavel ao dia da semana de `day`, ou `None` quando o modelo nao espera
    produção nesse período (ex.: fim de semana sem regra própria) - mesmo critério de
    `lib/operations-calendar-helpers.ts:dayTarget`."""
    period_type = "sunday" if day.weekday() == 6 else "saturday" if day.weekday() == 5 else "weekday"
    rule = next((item for item in model_dict["target_rules"] if item["period_type"] == period_type), None)
    if rule is not None:
        return rule if rule["enabled"] else None
    if day.weekday() < 5:
        return {
            "enabled": True,
            "median_from_quantity": model_dict["median_from_quantity"],
            "good_from_quantity": model_dict["good_from_quantity"],
            "target_quantity": model_dict["daily_target"],
        }
    return None


def is_scheduled_workday(member: ManagementOperationalMember, day: date) -> bool:
    """`False` quando `day` cai na folga da escala alternada (12x36 etc.) desse colaborador - ver
    `MEMBER_SHIFT_PATTERNS`. Sem escala configurada (`shift_pattern` nulo/"standard", ou dados
    incompletos), sempre `True` - mesmo comportamento de antes desta função existir, pra não
    quebrar quem já funcionava certo com a régua padrão de segunda a sexta."""
    if member.shift_pattern != "alternating":
        return True
    if not member.shift_anchor_date or not member.shift_cycle_days_on or not member.shift_cycle_days_off:
        return True
    cycle_length = member.shift_cycle_days_on + member.shift_cycle_days_off
    if cycle_length <= 0:
        return True
    # `%` do Python sempre devolve resultado no sinal do divisor (positivo aqui), então funciona
    # tanto pra `day` depois quanto antes de `shift_anchor_date`.
    offset = (day - member.shift_anchor_date).days % cycle_length
    return offset < member.shift_cycle_days_on


# Janela de dias corridos usada pra sugerir a escala 12x36 a partir da produção real. Só a ponta
# mais recente entra na análise (não os 45 dias inteiros) porque a produção de um técnico pode
# mudar de padrão no meio do caminho (trocou de turma, voltou de férias) - olhar só os últimos dias
# reflete a realidade atual, que é o que o supervisor precisa confirmar.
SHIFT_SUGGESTION_WINDOW_DAYS = 21
# Sequência de dias seguidos sem nenhuma O.S. fechada, terminando hoje, que faz a sugestão desistir
# de propor uma escala alternada e virar só um aviso. Numa 12x36 real o maior "buraco" possível é 1
# dia (a folga) - uma sequência bem maior que isso é sinal de afastamento/desligamento, não de
# escala, e sugerir "dia sim, dia não" nesse caso mascararia um caso real (achado da auditoria de
# 2026-08-21 com Diolvane/Thalison: 17-18 dias corridos sem produção).
SHIFT_SUGGESTION_MAX_TRAILING_GAP_DAYS = 4
# Fração mínima de dias da janela que precisa bater com o padrão dia-sim/dia-não candidato pra a
# sugestão ser considerada confiável o bastante pra preencher o formulário.
SHIFT_SUGGESTION_MIN_MATCH_RATIO = 0.8


@dataclass
class ShiftPatternSuggestion:
    suggested_pattern: str  # "alternating" | "inconclusive"
    suggested_cycle_days_on: int | None
    suggested_cycle_days_off: int | None
    suggested_anchor_date: date | None
    confidence: float
    message: str
    daily_production: list[dict]  # [{"date": date, "quantity": int}, ...] - evidência p/ o supervisor conferir


def suggest_shift_pattern(db: Session, member: ManagementOperationalMember, *, today: date | None = None) -> ShiftPatternSuggestion:
    """Analisa a produção real dos últimos `SHIFT_SUGGESTION_WINDOW_DAYS` dias desse colaborador e
    propõe uma escala alternada 1x1 (dia sim, dia não) quando o padrão bate de forma consistente.

    Decisão de produto (pedido do usuário em 2026-08-21, "sistema sugere, supervisor confirma"): a
    função NUNCA grava nada - só devolve uma sugestão pra o formulário de edição vir pré-preenchido.
    O supervisor ainda precisa clicar em salvar (que passa pela validação normal de
    `services.validate_shift_pattern_for_team_model`). Também nunca infere "folga" a partir de uma
    sequência longa de dias sem produção - isso é tratado como possível afastamento e devolvido como
    aviso (`suggested_pattern="inconclusive"`), não como sugestão de escala.
    """
    reference = today or date.today()
    window_start = reference - timedelta(days=SHIFT_SUGGESTION_WINDOW_DAYS - 1)

    start = datetime(window_start.year, window_start.month, window_start.day, tzinfo=timezone.utc) - timedelta(days=1)
    end = datetime(reference.year, reference.month, reference.day, 23, 59, 59, tzinfo=timezone.utc) + timedelta(days=1)

    closed_day = _local_closed_date(db)
    target_name = _norm(member.responsible_name)
    rows = db.execute(
        select(OperationOrder.responsible, closed_day, func.count(OperationOrder.id))
        .where(
            OperationOrder.closed_at.is_not(None),
            OperationOrder.closed_at.between(start, end),
            OperationOrder.responsible.is_not(None),
            OperationOrder.responsible != "",
        )
        .group_by(OperationOrder.responsible, closed_day)
    ).all()

    # Normaliza em Python (não no SQL) pra usar exatamente a mesma função `_norm` já usada em
    # `generate_performance_cases` pra casar responsável - mantém as duas rotas consistentes.
    quantities_by_day: dict[date, int] = {}
    for responsible, day, quantity in rows:
        if _norm(responsible) != target_name:
            continue
        local_day = _as_date(day)
        if local_day is None or local_day < window_start or local_day > reference:
            continue
        quantities_by_day[local_day] = quantities_by_day.get(local_day, 0) + int(quantity or 0)

    daily_production = [
        {"date": window_start + timedelta(days=offset), "quantity": quantities_by_day.get(window_start + timedelta(days=offset), 0)}
        for offset in range(SHIFT_SUGGESTION_WINDOW_DAYS)
    ]
    worked = [entry["quantity"] > 0 for entry in daily_production]

    trailing_gap = 0
    for has_production in reversed(worked):
        if has_production:
            break
        trailing_gap += 1
    if trailing_gap >= SHIFT_SUGGESTION_MAX_TRAILING_GAP_DAYS:
        return ShiftPatternSuggestion(
            suggested_pattern="inconclusive",
            suggested_cycle_days_on=None,
            suggested_cycle_days_off=None,
            suggested_anchor_date=None,
            confidence=0.0,
            message=(
                f"Sem nenhuma O.S. fechada nos últimos {trailing_gap} dias corridos - isso é maior do "
                "que uma folga normal de 12x36 e pode ser afastamento, desligamento ou troca de função. "
                "Confirme a situação do colaborador antes de configurar a escala manualmente."
            ),
            daily_production=daily_production,
        )

    best_offset, best_ratio = 0, -1.0
    for offset in (0, 1):
        matches = sum(1 for index, has_production in enumerate(worked) if has_production == (index % 2 == offset))
        ratio = matches / len(worked)
        if ratio > best_ratio:
            best_offset, best_ratio = offset, ratio

    if best_ratio < SHIFT_SUGGESTION_MIN_MATCH_RATIO:
        return ShiftPatternSuggestion(
            suggested_pattern="inconclusive",
            suggested_cycle_days_on=None,
            suggested_cycle_days_off=None,
            suggested_anchor_date=None,
            confidence=best_ratio,
            message=(
                "A produção dos últimos dias não mostra um padrão de dia sim/dia não consistente. "
                "Configure a escala manualmente conferindo o histórico abaixo."
            ),
            daily_production=daily_production,
        )

    anchor_date = window_start + timedelta(days=best_offset)
    return ShiftPatternSuggestion(
        suggested_pattern="alternating",
        suggested_cycle_days_on=1,
        suggested_cycle_days_off=1,
        suggested_anchor_date=anchor_date,
        confidence=best_ratio,
        message=(
            f"Produção dos últimos {SHIFT_SUGGESTION_WINDOW_DAYS} dias bate com escala 12x36 (dia sim, "
            f"dia não) em {round(best_ratio * 100)}% dos dias, ancorada em {anchor_date.isoformat()}. "
            "Confira o histórico abaixo e salve pra confirmar."
        ),
        daily_production=daily_production,
    )


def generate_daily_cases_for_date(
    db: Session,
    *,
    day: date,
    created_by: int | None = None,
) -> dict:
    """Abre automaticamente o caso "dia abaixo da meta" (`CASE_TYPE_DAILY_BELOW`) para todo
    responsável/regional com meta ativa no dia informado (segundo o modelo de equipe e o dia da
    semana) que produziu abaixo do limiar "below" - **incluindo produção zero**. Decisão de
    produto: ao contrário de `classify_daily_performance` (usado pelo calendário, que trata 0 como
    "neutro" para não pintar de vermelho quem estava de férias/atestado), aqui zero SEMPRE conta -
    o caso nasce e cabe ao colaborador/supervisor justificar o motivo (inclusive "estava de
    férias"), em vez de o sistema tentar adivinhar antes de abrir o caso.

    Antes desta função, esse caso só nascia quando o supervisor clicava em "Justificar dia" no
    drill do calendário - nenhum caso nascia sozinho, nem para quem produziu abaixo da meta nem
    para quem não produziu nada num dia esperado.

    Respeita a escala alternada (12x36 etc.) de quem tem uma configurada - dia de folga não é
    avaliado (ver `is_scheduled_workday`), achado real 2026-08-20: sem essa checagem, a folga de
    equipes 12x36 virava caso de "produção zero num dia esperado" indevidamente.

    Idempotente via `get_or_create_daily_case`: rodar de novo para o mesmo dia nunca duplica caso,
    e um caso já justificado/resolvido não é reaberto."""
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) - timedelta(days=1)
    end = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=timezone.utc) + timedelta(days=1)
    closed_day = _local_closed_date(db)
    rows = db.execute(
        select(OperationOrder.responsible, OperationOrder.regional, closed_day, func.count(OperationOrder.id))
        .where(
            OperationOrder.closed_at.is_not(None),
            OperationOrder.closed_at.between(start, end),
            OperationOrder.responsible.is_not(None),
            OperationOrder.responsible != "",
        )
        .group_by(OperationOrder.responsible, OperationOrder.regional, closed_day)
    ).all()

    produced: dict[tuple[str, str], dict] = {}
    for responsible, regional, closed_date, quantity in rows:
        local_day = _as_date(closed_date)
        if local_day != day:
            continue
        normalized_regional = normalize_regional(str(regional or ""))
        key = (_norm(responsible), _norm(normalized_regional))
        # Mesmo (responsavel, regional) pode aparecer em mais de uma linha se o recorte de fuso
        # de `_local_closed_date` colidir por acaso com outra regional grafada diferente antes da
        # normalizacao - soma em vez de sobrescrever, mesmo tratamento do agregado mensal.
        bucket = produced.setdefault(key, {"responsible": responsible, "regional": normalized_regional, "quantity": 0})
        bucket["quantity"] += int(quantity or 0)

    # Base é a estrutura operacional ativa, não quem produziu algo no dia - só assim um dia com
    # produção ZERO (ninguém aparece nas linhas de `produced`) também é avaliado.
    members = db.scalars(
        select(ManagementOperationalMember).where(
            ManagementOperationalMember.is_active.is_(True),
            ManagementOperationalMember.team_model_id.is_not(None),
            ManagementOperationalMember.status.not_in(("outside_operation", "inactive")),
        )
    ).all()
    team_models = {model.id: model for model in db.scalars(select(OperationTeamModel)).all() if model.active}

    created = 0
    already_open = 0
    evaluated = 0
    for member in members:
        if not is_scheduled_workday(member, day):
            continue
        model = team_models.get(member.team_model_id)
        if model is None:
            continue
        model_dict = _team_model_dict(model)
        rule = _rule_for_day(model_dict, day)
        if rule is None:
            continue
        key = (_norm(member.responsible_name), _norm(member.regional))
        info = produced.get(key)
        quantity = info["quantity"] if info else 0
        evaluated += 1
        if quantity >= int(rule["median_from_quantity"]):
            continue
        _, was_created = get_or_create_daily_case(
            db,
            responsible_name=info["responsible"] if info else member.responsible_name,
            regional=info["regional"] if info else member.regional,
            reference_date=day,
            # "Esperado" é o piso da faixa "boa" (median_from_quantity), não o teto do dia
            # (target_quantity) - mesma decisão do agregado mensal, acima.
            expected_value=float(rule["median_from_quantity"]),
            actual_value=float(quantity),
            created_by=created_by,
        )
        if was_created:
            created += 1
        else:
            already_open += 1

    db.flush()
    return {
        "created_cases": created,
        "already_open_cases": already_open,
        "evaluated_members": evaluated,
        "reference_date": day.isoformat(),
    }


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
    if filters.status and filters.statuses and filters.status not in filters.statuses:
        # status="resolved"/"rejected" + only_open=true (que popula `statuses` com os status
        # abertos) é uma contradição lógica: o AND das duas condições é sempre vazio. Sem esse
        # aviso, a chamada "tem sucesso" com 0 casos e quem chamou (humano ou IA) lê isso como
        # "não há casos", quando na verdade o filtro está mal formado.
        raise ValueError(
            f"Filtro contraditório: status={filters.status!r} não está entre os status abertos "
            f"{sorted(filters.statuses)!r} exigidos por only_open=true. Remova only_open ou "
            "escolha um status aberto (pending/justified/in_progress)."
        )
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


def bulk_review_cases(
    db: Session,
    *,
    case_ids: list[int],
    status: str,
    review_note: str | None,
    reviewer_id: int,
    scope_conditions: list,
) -> dict:
    """Aplica a MESMA decisão (`review_case`, um por um) a vários casos de uma vez - pedido do
    usuário em 2026-08-20: matriz não quer abrir caso por caso pra aprovar em lote quando o motivo
    é o mesmo pra todos. Casos fora do escopo do revisor ou ainda "pending" (sem justificativa -
    mesma regra do endpoint individual, não dá pra resolver o que não foi justificado) são
    pulados, não erram a chamada inteira."""
    rows = db.scalars(
        select(ManagementCase).where(ManagementCase.id.in_(case_ids), *scope_conditions)
    ).all()
    found_ids = {item.id for item in rows}
    not_found = len(set(case_ids)) - len(found_ids)

    updated = 0
    skipped_pending = 0
    now = datetime.now(timezone.utc)
    for item in rows:
        if item.status == "pending" and status == "resolved":
            skipped_pending += 1
            continue
        item.status = status
        item.reviewed_by = reviewer_id
        item.reviewed_at = now
        if review_note:
            db.add(ManagementCaseComment(case_id=item.id, user_id=reviewer_id, comment=review_note.strip()))
        updated += 1

    return {"updated_cases": updated, "skipped_pending": skipped_pending, "not_found": not_found}


_DIAGNOSTICS_TOP_N = 15


def _diagnostics_bucket(rows: list[tuple[str, str, date | None]]) -> list[dict]:
    """`rows` é uma lista de (chave, status, due_date) já filtrada por uma dimensão (regional,
    responsável ou motivo) - agrega em memória em vez de uma query agregada por dimensão, porque o
    volume de casos é pequeno (nunca mais que alguns milhares) e assim as três dimensões
    compartilham a MESMA leitura do banco (ver `case_diagnostics`)."""
    today = date.today()
    buckets: dict[str, dict] = {}
    for key, status, due_date in rows:
        bucket = buckets.setdefault(key, {"key": key, "total": 0, "open_cases": 0, "overdue_cases": 0})
        bucket["total"] += 1
        if status in OPEN_CASE_STATUSES:
            bucket["open_cases"] += 1
            if due_date is not None and due_date < today:
                bucket["overdue_cases"] += 1
    ordered = sorted(buckets.values(), key=lambda item: (-item["total"], item["key"]))
    return ordered[:_DIAGNOSTICS_TOP_N]


def case_diagnostics(db: Session, conditions: list) -> dict:
    """Diagnóstico agregado dos casos no recorte filtrado - "quem mais falha, por regional/
    motivo", pedido do usuário em 2026-08-20 pra matriz não precisar contar caso por caso na
    tabela. Mesmo recorte (`conditions`) da listagem/resumo, pra os três nunca divergirem."""
    rows = db.execute(
        select(
            ManagementCase.regional,
            ManagementCase.responsible_name,
            ManagementCaseReason.name,
            ManagementCase.status,
            ManagementCase.due_date,
        )
        .outerjoin(ManagementCaseReason, ManagementCaseReason.id == ManagementCase.reason_id)
        .where(*conditions)
    ).all()
    total = len(rows)
    by_regional = _diagnostics_bucket(
        [(regional or "Não identificada", status, due_date) for regional, _, _, status, due_date in rows]
    )
    by_responsible = _diagnostics_bucket(
        [(responsible or "Não identificado", status, due_date) for _, responsible, _, status, due_date in rows]
    )
    by_reason = _diagnostics_bucket(
        [(reason, status, due_date) for _, _, reason, status, due_date in rows if reason]
    )
    return {
        "total_cases": total,
        "by_regional": [{**bucket, "label": bucket["key"]} for bucket in by_regional],
        "by_responsible": [{**bucket, "label": bucket["key"]} for bucket in by_responsible],
        "by_reason": [{**bucket, "label": bucket["key"]} for bucket in by_reason],
    }


def validate_case_status(value: str) -> str:
    if value not in MANAGEMENT_CASE_STATUSES:
        raise ValueError(f"Status de caso inválido: {value!r}.")
    return value
