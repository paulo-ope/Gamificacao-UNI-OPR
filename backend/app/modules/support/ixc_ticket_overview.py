"""Visão Geral do atendimento IXC: KPIs com corte alinhado por dia-do-mês, série diária de
incidência e "Prioridades detectadas" (regionais fora da curva). Referência visual: 2 prints do
usuário em 2026-09-11 (ver memória de projeto `atendimento_ixc_indicador_preditivo`).

Definições assumidas nesta primeira versão, marcadas para calibração/confirmação:
- "Média histórica" usa os `history_months` meses anteriores, **no mesmo corte de dia** do mês
  corrente (ex.: mês corrente só tem dado até dia 11 -> os 3 meses anteriores também são cortados
  no dia 11) - comparação "maçã com maçã" entre mês parcial e mês completo.
- O denominador (contratos ativos) usa sempre a base ATUAL (`OperationCustomerContract` não tem
  histórico por mês) - a incidência histórica reaproveita o mesmo denominador de hoje, não o real
  da época. Aceitável como aproximação; documentar se algum dia isso importar de verdade.
- Severidade (CRÍTICO/DENTRO DA CURVA/EM MELHORA) e os limiares (+20%/-10%) foram calibrados só
  visualmente contra o mockup do usuário, não são regra de negócio validada - primeira versão,
  espera ajuste.
- "Categoria" de cada prioridade = motivo (`subject_name`) mais frequente da regional no período -
  simplificação: o mockup sugere uma categoria "dominante"/mais anômala, não necessariamente a de
  maior volume; refinar depois se o usuário notar divergência.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.operations.models import OperationCustomerContract
from app.services.regional import REGIONAL_CODE_MAP, is_valid_regional

from .ixc_ticket_queries import ACTIVE_CONTRACT_STATUS, selected_ids
from .ixc_ticket_taxonomy import taxonomy_coverage_pct
from .models import SupportIxcTicket

# Recalibrado pra +15%/-15% a pedido do usuário (2026-09-15, depois de usar o painel único com
# dado real) - era +20%/-10%; a versão anterior pegava sinal tarde demais e reagia mais rápido a
# melhora do que a piora, o que não fazia sentido (o objetivo é ANTECIPAR incidente, não confirmar
# um já grande).
CRITICAL_DEVIATION_PCT = 15.0
IMPROVING_DEVIATION_PCT = -15.0
DEFAULT_HISTORY_MONTHS = 3

# Amostra mínima de atendimentos no histórico (soma dos meses anteriores, mesmo corte de dia)
# para o desvio ser considerado sinal, não ruído - mesmo espírito de
# `intelligence/monitors/sla_deterioration.MIN_BASELINE_MEASURABLE` (=10).
MIN_HISTORICAL_SAMPLE = 10


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _clamp_day(month_start: date, day: int) -> date:
    last_day = calendar.monthrange(month_start.year, month_start.month)[1]
    return month_start.replace(day=min(day, last_day))


def _ticket_count(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    regional: str | None = None,
    city: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
) -> int:
    query = select(func.count(SupportIxcTicket.id)).where(
        func.date(SupportIxcTicket.created_at) >= date_from,
        func.date(SupportIxcTicket.created_at) <= date_to,
    )
    if regional:
        query = query.where(SupportIxcTicket.regional == regional)
    if city:
        query = query.where(SupportIxcTicket.city == city)
    if values := selected_ids(subject_id):
        query = query.where(SupportIxcTicket.subject_id.in_(values))
    if values := selected_ids(sector_id):
        query = query.where(SupportIxcTicket.sector_id.in_(values))
    return int(db.scalar(query) or 0)


def _active_contract_count(db: Session, *, regional: str | None = None, city: str | None = None) -> int:
    query = select(func.count(OperationCustomerContract.id)).where(
        OperationCustomerContract.status == ACTIVE_CONTRACT_STATUS
    )
    if regional:
        query = query.where(OperationCustomerContract.regional == regional)
    if city:
        query = query.where(OperationCustomerContract.city == city)
    return int(db.scalar(query) or 0)


def _coverage_pct(db: Session, *, regional: str | None = None, city: str | None = None) -> float | None:
    """Sem filtro nenhum: % de contratos ativos com regional identificada (não
    "NAO IDENTIFICADO"). Com regional (sem cidade): % de contratos ativos daquela regional com
    cidade resolvida - achado real em produção (2026-09-11): 87% dos contratos ativos de uma
    regional real (Rolim de Moura) não têm cidade cadastrada no IXC (`cidade=0`), então "clientes
    ativos" quebrado por cidade sempre vai ser uma fração da base total - esta métrica existe pra
    deixar isso visível, não escondido. Com cidade: % de contratos ativos daquela cidade com bairro
    resolvido (mesmo raciocínio, um nível mais fundo)."""
    base_query = select(func.count(OperationCustomerContract.id)).where(
        OperationCustomerContract.status == ACTIVE_CONTRACT_STATUS
    )
    if city:
        base_query = base_query.where(OperationCustomerContract.city == city)
        matched_query = base_query.where(OperationCustomerContract.neighborhood.is_not(None))
    elif regional:
        base_query = base_query.where(OperationCustomerContract.regional == regional)
        matched_query = base_query.where(OperationCustomerContract.city.is_not(None))
    else:
        matched_query = base_query.where(OperationCustomerContract.regional.in_(REGIONAL_CODE_MAP.values()))

    total = int(db.scalar(base_query) or 0)
    if not total:
        return None
    matched = int(db.scalar(matched_query) or 0)
    return round(matched / total * 100, 1)


def _taxonomy_coverage_pct(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    regional: str | None = None,
    city: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
) -> float | None:
    """% dos atendimentos do recorte (mesmos filtros do KPI, não distinto por motivo) com tema de
    taxonomia mapeado (item 8 do plano de evolução analítica: revisão dos `NAO_MAPEADO` deixa de
    ser só um `grep` manual no banco - fica visível pra quem opera a tela). Pondera por
    atendimento, não por `subject_id` distinto: um motivo raro sem mapeamento não deve pesar igual
    a um motivo de alto volume também sem mapeamento."""
    query = select(SupportIxcTicket.subject_id).where(
        func.date(SupportIxcTicket.created_at) >= date_from,
        func.date(SupportIxcTicket.created_at) <= date_to,
    )
    if regional:
        query = query.where(SupportIxcTicket.regional == regional)
    if city:
        query = query.where(SupportIxcTicket.city == city)
    if values := selected_ids(subject_id):
        query = query.where(SupportIxcTicket.subject_id.in_(values))
    if values := selected_ids(sector_id):
        query = query.where(SupportIxcTicket.sector_id.in_(values))
    subject_ids = [row[0] for row in db.execute(query).all()]
    return taxonomy_coverage_pct(db, subject_ids)


def _classify_severity(deviation_pct: float | None) -> str:
    if deviation_pct is None:
        return "sem_dado"
    if deviation_pct >= CRITICAL_DEVIATION_PCT:
        return "critico"
    if deviation_pct <= IMPROVING_DEVIATION_PCT:
        return "em_melhora"
    return "dentro_da_curva"


def overview_kpis(
    db: Session,
    *,
    month: date,
    regional: str | None = None,
    city: str | None = None,
    history_months: int = DEFAULT_HISTORY_MONTHS,
    today: date | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
    day: date | None = None,
) -> dict[str, Any]:
    """KPIs do topo da Visão Geral: incidência parcial do mês corrente, média histórica no mesmo
    corte de dia, desvio entre as duas e base ativa comparável (com % de cobertura).

    `regional` e `city` são independentes - passar só `city` mede a cidade em si (sem restringir
    a uma regional), usado pela heurística de pares por cidade (`city_priorities`, ver
    docs/STATUS.md 2026-09-11: pares de cidade comparam contra TODAS as cidades do sistema, não só
    as da mesma regional).

    `subject_id`/`sector_id` (pedido do usuário, 2026-09-12: o filtro de motivo/setor não pode
    valer só no drill-down, tem que refletir também nos KPIs/gráfico/prioridades) restringem tanto
    o mês corrente quanto TODOS os meses históricos ao mesmo recorte - senão o desvio compararia
    "atendimentos de X" contra "todos os atendimentos", número sem sentido.

    `day` (pedido do usuário, 2026-09-12: "ver só um dia específico"): quando informado, os KPIs
    deixam de ser acumulados do início do mês até o corte - passam a contar só AQUELE dia, e a
    "média histórica" também vira a contagem do mesmo dia-do-mês nos meses anteriores (não a soma
    cumulativa até ele). `month` continua definindo em que mês `day` cai, pra achar o dia
    equivalente nos meses históricos."""
    today = today or date.today()
    month_start = _month_start(month)
    is_current_month = month_start == _month_start(today)
    cutoff = min(today, _clamp_day(month_start, calendar.monthrange(month_start.year, month_start.month)[1])) if is_current_month else _clamp_day(month_start, 31)
    cutoff_day = day.day if day is not None else cutoff.day

    current_date_from = day if day is not None else month_start
    current_date_to = day if day is not None else cutoff

    ticket_count = _ticket_count(
        db,
        date_from=current_date_from,
        date_to=current_date_to,
        regional=regional,
        city=city,
        subject_id=subject_id,
        sector_id=sector_id,
    )
    contract_count = _active_contract_count(db, regional=regional, city=city)
    incidencia_parcial = round(ticket_count / contract_count * 1000, 1) if contract_count else None

    historical_counts: list[int] = []
    for offset in range(1, history_months + 1):
        past_month_start = _add_months(month_start, -offset)
        past_point = _clamp_day(past_month_start, cutoff_day)
        past_date_from = past_point if day is not None else past_month_start
        historical_counts.append(
            _ticket_count(
                db,
                date_from=past_date_from,
                date_to=past_point,
                regional=regional,
                city=city,
                subject_id=subject_id,
                sector_id=sector_id,
            )
        )

    media_historica = None
    if historical_counts and contract_count:
        avg_count = sum(historical_counts) / len(historical_counts)
        media_historica = round(avg_count / contract_count * 1000, 1)

    desvio_pct = None
    # Amostra histórica mínima antes de calcular desvio - mesmo espírito de
    # `intelligence/monitors/sla_deterioration.MIN_BASELINE_MEASURABLE`: um histórico de 1-2
    # atendimentos vira +200%/-90% por ruído puro, não sinal real. Sem isso, regional pequena
    # dispararia CRÍTICO por acaso estatístico, não por anomalia de verdade.
    historical_sample_size = sum(historical_counts)
    if incidencia_parcial is not None and media_historica and historical_sample_size >= MIN_HISTORICAL_SAMPLE:
        desvio_pct = round((incidencia_parcial - media_historica) / media_historica * 100, 1)

    return {
        "month": month_start.isoformat(),
        "cutoff_day": cutoff_day,
        "incidencia_parcial": incidencia_parcial,
        "ticket_count": ticket_count,
        "media_historica": media_historica,
        "history_months_used": len(historical_counts),
        "desvio_pct": desvio_pct,
        "severity": _classify_severity(desvio_pct),
        "contract_count": contract_count,
        "coverage_pct": _coverage_pct(db, regional=regional, city=city),
        "taxonomy_coverage_pct": _taxonomy_coverage_pct(
            db,
            date_from=current_date_from,
            date_to=current_date_to,
            regional=regional,
            city=city,
            subject_id=subject_id,
            sector_id=sector_id,
        ),
    }


def daily_incidence_series(
    db: Session,
    *,
    month: date,
    regional: str | None = None,
    history_months: int = DEFAULT_HISTORY_MONTHS,
    today: date | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
) -> list[dict[str, Any]]:
    """Série diária pra o gráfico "Curva diária de incidência": contagem do mês corrente, do mês
    anterior, média histórica por dia-do-mês e média móvel de 7 dias do mês corrente.

    `subject_id`/`sector_id`: mesmo filtro de motivo/setor do drill-down, aplicado aqui também
    (pedido do usuário, 2026-09-12) - o gráfico é uma decomposição diária do mesmo recorte dos
    KPIs, não um cálculo à parte."""
    today = today or date.today()
    month_start = _month_start(month)
    is_current_month = month_start == _month_start(today)
    days_in_month = calendar.monthrange(month_start.year, month_start.month)[1]
    last_day = today.day if is_current_month else days_in_month

    previous_month_start = _add_months(month_start, -1)
    history_month_starts = [_add_months(month_start, -offset) for offset in range(1, history_months + 1)]

    def _daily_counts(base_month_start: date, up_to_day: int) -> dict[int, int]:
        base_days = calendar.monthrange(base_month_start.year, base_month_start.month)[1]
        capped = min(up_to_day, base_days)
        query = (
            select(func.date(SupportIxcTicket.created_at), func.count(SupportIxcTicket.id))
            .where(
                func.date(SupportIxcTicket.created_at) >= base_month_start,
                func.date(SupportIxcTicket.created_at) <= base_month_start.replace(day=capped),
            )
            .group_by(func.date(SupportIxcTicket.created_at))
        )
        if regional:
            query = query.where(SupportIxcTicket.regional == regional)
        if values := selected_ids(subject_id):
            query = query.where(SupportIxcTicket.subject_id.in_(values))
        if values := selected_ids(sector_id):
            query = query.where(SupportIxcTicket.sector_id.in_(values))
        # Postgres devolve `date` de verdade; SQLite (testes) devolve string "YYYY-MM-DD" -
        # normaliza os dois antes de extrair o dia.
        return {
            (row[0] if isinstance(row[0], date) else date.fromisoformat(row[0])).day: row[1]
            for row in db.execute(query).all()
        }

    current_counts = _daily_counts(month_start, days_in_month)
    previous_counts = _daily_counts(previous_month_start, days_in_month)
    history_counts_by_month = [_daily_counts(m, days_in_month) for m in history_month_starts]

    series: list[dict[str, Any]] = []
    for day in range(1, days_in_month + 1):
        current_value = current_counts.get(day) if day <= last_day else None
        history_values = [counts.get(day, 0) for counts in history_counts_by_month]
        historical_avg = round(sum(history_values) / len(history_values), 1) if history_values else None

        window = [current_counts.get(d, 0) for d in range(max(1, day - 6), day + 1) if d <= last_day]
        moving_avg_7d = round(sum(window) / len(window), 1) if window and day <= last_day else None

        series.append({
            "day": day,
            "current": current_value,
            "previous_month": previous_counts.get(day),
            "historical_avg": historical_avg,
            "moving_avg_7d": moving_avg_7d,
        })

    return series


def _category_deltas(
    db: Session,
    *,
    month_start: date,
    cutoff: date,
    history_month_starts: list[date],
    regional: str | None = None,
    city: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
    day: date | None = None,
) -> dict[str, dict[str, float]]:
    """Base compartilhada de `_dominant_category` e `driver_decomposition` (Fase 1 do plano de
    evolução analítica, 2026-09-14 - extraída pra não duplicar as mesmas idas ao banco em duas
    funções). Por `subject_name`: `current` (contagem no período atual) e `expected` (média do
    mesmo motivo nos meses históricos, no mesmo corte de dia - 0.0 se o motivo nunca apareceu no
    histórico). `{}` quando não há nenhum atendimento no período atual."""
    def _scoped(query):
        if regional:
            query = query.where(SupportIxcTicket.regional == regional)
        if city:
            query = query.where(SupportIxcTicket.city == city)
        if values := selected_ids(subject_id):
            query = query.where(SupportIxcTicket.subject_id.in_(values))
        if values := selected_ids(sector_id):
            query = query.where(SupportIxcTicket.sector_id.in_(values))
        return query

    current_date_from = day if day is not None else month_start
    current_date_to = day if day is not None else cutoff
    cutoff_day = day.day if day is not None else cutoff.day

    current_rows = db.execute(
        _scoped(
            select(SupportIxcTicket.subject_name, func.count(SupportIxcTicket.id)).where(
                func.date(SupportIxcTicket.created_at) >= current_date_from,
                func.date(SupportIxcTicket.created_at) <= current_date_to,
            )
        ).group_by(SupportIxcTicket.subject_name)
    ).all()
    current_counts = {(name or "Não informado"): count for name, count in current_rows}
    if not current_counts:
        return {}

    historical_counts: dict[str, list[int]] = {name: [] for name in current_counts}
    for past_month_start in history_month_starts:
        past_point = _clamp_day(past_month_start, cutoff_day)
        past_date_from = past_point if day is not None else past_month_start
        rows = db.execute(
            _scoped(
                select(SupportIxcTicket.subject_name, func.count(SupportIxcTicket.id)).where(
                    func.date(SupportIxcTicket.created_at) >= past_date_from,
                    func.date(SupportIxcTicket.created_at) <= past_point,
                )
            ).group_by(SupportIxcTicket.subject_name)
        ).all()
        past_counts = {(name or "Não informado"): count for name, count in rows}
        for name in current_counts:
            historical_counts[name].append(past_counts.get(name, 0))

    return {
        name: {
            "current": current_counts[name],
            "expected": (sum(historical_counts[name]) / len(historical_counts[name])) if historical_counts[name] else 0.0,
        }
        for name in current_counts
    }


def _dominant_category(
    db: Session,
    *,
    month_start: date,
    cutoff: date,
    history_month_starts: list[date],
    regional: str | None = None,
    city: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
    day: date | None = None,
) -> str:
    """Motivo (subject_name) que mais contribuiu pro desvio da regional - maior AUMENTO ABSOLUTO
    (contagem atual - média histórica no mesmo corte), não o motivo mais frequente. Pedido
    explícito do usuário (2026-09-11: "pense em como metrificar se algo está saindo do padrão, ex.
    lentidão"): o motivo mais comum de uma regional tende a ser sempre o mesmo (ex. "Registro de
    Atendimento Operacional") e mascara justamente o que MUDOU - "lentidão" pode ter volume baixo
    em termos absolutos e ainda assim ser o sinal relevante, se ela pulou de quase zero pra um
    número visível. Fallback pro motivo mais frequente do período atual só quando nenhum motivo
    tem aumento positivo (nada "novo" se destacando)."""
    deltas = _category_deltas(
        db, month_start=month_start, cutoff=cutoff, history_month_starts=history_month_starts,
        regional=regional, city=city, subject_id=subject_id, sector_id=sector_id, day=day,
    )
    if not deltas:
        return "Não informado"

    best_name = max(deltas, key=lambda name: deltas[name]["current"] - deltas[name]["expected"])
    best_delta = deltas[best_name]["current"] - deltas[best_name]["expected"]

    # Nenhum motivo aumentou de verdade (tudo estável ou em queda) - cai pro mais frequente do
    # período atual, só pra ter algo informativo pra mostrar.
    if best_delta <= 0:
        return max(deltas, key=lambda name: deltas[name]["current"])
    return best_name


def driver_decomposition(
    db: Session,
    *,
    month_start: date,
    cutoff: date,
    history_month_starts: list[date],
    regional: str | None = None,
    city: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
    day: date | None = None,
) -> list[dict[str, Any]]:
    """Decompõe o excesso (atual - esperado) por motivo, com `contribution_pct` = participação
    daquele motivo no excesso TOTAL positivo do escopo - pedido do usuário (2026-09-14, plano de
    evolução analítica do Atendimento IXC): "Lentidão explica 62% do aumento observado."

    Só motivos com excesso POSITIVO entram no denominador de `contribution_pct` - uma queda em
    outro motivo não pode "inflar" a participação dos que subiram. Motivo com excesso <= 0 aparece
    na lista com `contribution_pct = 0.0` (participação real de zero, não falta de dado). Lista
    vazia quando não há nenhum atendimento no período (mesmo caso de `_dominant_category`)."""
    deltas = _category_deltas(
        db, month_start=month_start, cutoff=cutoff, history_month_starts=history_month_starts,
        regional=regional, city=city, subject_id=subject_id, sector_id=sector_id, day=day,
    )
    items: list[dict[str, Any]] = []
    for name, values in deltas.items():
        excess = values["current"] - values["expected"]
        items.append({
            "subject_name": name,
            "current": values["current"],
            "expected": round(values["expected"], 2),
            "excess": round(excess, 2),
        })

    total_positive_excess = sum(item["excess"] for item in items if item["excess"] > 0)
    for item in items:
        item["contribution_pct"] = (
            round(item["excess"] / total_positive_excess * 100, 1)
            if total_positive_excess > 0 and item["excess"] > 0
            else 0.0
        )

    items.sort(key=lambda item: item["excess"], reverse=True)
    return items


def _priorities_for_scopes(
    db: Session,
    *,
    month: date,
    scope_key: str,
    scope_values: list[str],
    history_months: int,
    today: date | None,
    subject_id: str | None = None,
    sector_id: str | None = None,
    day: date | None = None,
) -> list[dict[str, Any]]:
    """Motor comum de "Prioridades detectadas": uma linha por valor de `scope_key`
    (`"regional"` ou `"city"`), com incidência, desvio vs a própria história e vs a MÉDIA DOS
    DEMAIS VALORES DA MESMA LISTA (pares) no mesmo período. `priorities()` (por regional) e
    `city_priorities()` (por cidade, pares = todas as cidades do sistema - decisão do usuário,
    2026-09-11) são finas camadas sobre isto, cada uma passando sua própria lista de valores."""
    today = today or date.today()
    month_start = _month_start(month)
    is_current_month = month_start == _month_start(today)
    cutoff = min(today, _clamp_day(month_start, 31)) if is_current_month else _clamp_day(month_start, 31)
    history_month_starts = [_add_months(month_start, -offset) for offset in range(1, history_months + 1)]

    per_scope: dict[str, dict[str, Any]] = {
        value: overview_kpis(
            db,
            month=month,
            history_months=history_months,
            today=today,
            subject_id=subject_id,
            sector_id=sector_id,
            day=day,
            **{scope_key: value},
        )
        for value in scope_values
    }

    items: list[dict[str, Any]] = []
    for value, kpis in per_scope.items():
        incidencia = kpis["incidencia_parcial"]
        peers_incidences = [
            other["incidencia_parcial"]
            for other_value, other in per_scope.items()
            if other_value != value and other["incidencia_parcial"] is not None
        ]
        peers_avg = round(sum(peers_incidences) / len(peers_incidences), 1) if peers_incidences else None
        peers_deviation_pct = None
        if incidencia is not None and peers_avg:
            peers_deviation_pct = round((incidencia - peers_avg) / peers_avg * 100, 1)

        category = _dominant_category(
            db,
            month_start=month_start,
            cutoff=cutoff,
            history_month_starts=history_month_starts,
            subject_id=subject_id,
            sector_id=sector_id,
            day=day,
            **{scope_key: value},
        )

        # Fallback de severidade quando não há amostra histórica suficiente
        # (MIN_HISTORICAL_SAMPLE): usa o desvio vs. OS PARES em vez de deixar "sem_dado" - achado
        # comparando com o painel de referência do Comercial (2026-09-14, pedido do usuário
        # "visualiza os drill e as heuristicas que tem"): uma regional/cidade nova ou com pouco
        # histórico não fica sem NENHUM sinal, só troca a base de comparação (histórico > pares >
        # nenhum). `severity_basis` deixa explícito pro frontend qual base foi usada, pra rotular
        # certo (não pode parecer que é "vs. histórico" quando na verdade é "vs. pares").
        if kpis["desvio_pct"] is not None:
            effective_deviation = kpis["desvio_pct"]
            severity_basis = "historical"
        elif peers_deviation_pct is not None:
            effective_deviation = peers_deviation_pct
            severity_basis = "peers"
        else:
            effective_deviation = None
            severity_basis = "none"

        items.append({
            scope_key: value,
            "category": category,
            "incidencia_parcial": incidencia,
            "historical_deviation_pct": kpis["desvio_pct"],
            "peers_deviation_pct": peers_deviation_pct,
            "severity": _classify_severity(effective_deviation),
            "severity_basis": severity_basis,
        })

    def _sort_key(item: dict[str, Any]) -> tuple[bool, float]:
        historical = item["historical_deviation_pct"]
        peers = item["peers_deviation_pct"]
        effective = historical if historical is not None else peers
        return (effective is None, -(effective or 0))

    items.sort(key=_sort_key)
    return items


def priorities(
    db: Session,
    *,
    month: date,
    history_months: int = DEFAULT_HISTORY_MONTHS,
    today: date | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
    day: date | None = None,
) -> list[dict[str, Any]]:
    """Lista "Prioridades detectadas" por REGIONAL: pares = as demais regionais."""
    regionals = [r for r in dict.fromkeys(REGIONAL_CODE_MAP.values()) if is_valid_regional(r)]
    return _priorities_for_scopes(
        db,
        month=month,
        scope_key="regional",
        scope_values=regionals,
        history_months=history_months,
        today=today,
        subject_id=subject_id,
        sector_id=sector_id,
        day=day,
    )


# Piso de contratos ativos pra uma cidade entrar no ranking de pares - sem isso, uma cidade de 5
# clientes ativos com 1 atendimento vira "200/1.000, CRÍTICO" por ruído de base pequena (mesmo
# problema que `MIN_HISTORICAL_SAMPLE` resolve pro eixo temporal, aqui é o eixo populacional).
MIN_CITY_ACTIVE_CONTRACTS = 20


def city_priorities(
    db: Session,
    *,
    month: date,
    history_months: int = DEFAULT_HISTORY_MONTHS,
    today: date | None = None,
    min_active_contracts: int = MIN_CITY_ACTIVE_CONTRACTS,
    subject_id: str | None = None,
    sector_id: str | None = None,
    day: date | None = None,
) -> list[dict[str, Any]]:
    """Lista "Prioridades detectadas" por CIDADE: pares = TODAS as cidades do sistema com base
    ativa suficiente, independente de regional - decisão explícita do usuário (2026-09-11): uma
    cidade de Rolim de Moura pode ser comparada com uma de Ji-Paraná, não só com as vizinhas da
    mesma regional. Detecta problema hiperlocal (ex.: um bairro/cidade específico saindo do
    padrão) que se dilui quando olhado só no nível regional."""
    cities = [
        row[0]
        for row in db.execute(
            select(OperationCustomerContract.city)
            .where(
                OperationCustomerContract.status == ACTIVE_CONTRACT_STATUS,
                OperationCustomerContract.city.is_not(None),
            )
            .group_by(OperationCustomerContract.city)
            .having(func.count(OperationCustomerContract.id) >= min_active_contracts)
        ).all()
    ]
    return _priorities_for_scopes(
        db,
        month=month,
        scope_key="city",
        scope_values=cities,
        history_months=history_months,
        today=today,
        subject_id=subject_id,
        sector_id=sector_id,
        day=day,
    )
