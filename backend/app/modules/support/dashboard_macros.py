"""Dashboard Suporte - "Macro principais" (pedido do usuário, 2026-10-14).

Junta, num só lugar, os indicadores do Suporte Interno N1 no IXC com os tempos e a avaliação do OPA:

- P (protocolos N1) = operacional (motivo 90) + financeiro (motivo 29), de `ixc_n1.n1_summary`;
- F (O.S. para campo) = O.S. abertas pelos colaboradores dos grupos N1 (105 e 117) no período, SÓ dos setores
  de campo 7, 8 e 9 (`PRIMARY_SECTOR_NAMES`): a tabela pode ter O.S. de outros setores (Comercial, Retenção...),
  que o N1 também abre e que não vão a campo - contá-las inflava "foi a campo" e derrubava a resolutividade.
  O vínculo é pelo criador da O.S. (`OperationOrder.creator`, que o IXC resolve a partir do mesmo `id_usuarios`
  do ticket) casado por nome com `SupportIxcUser`; NÃO dá pra usar o ticket da O.S. porque ele tem o motivo
  comum do cliente (ex.: "Sem Conexão"), não o 90/29 do N1;
- Atendimentos realizados = P + F; Solucionados = P; Foi a campo = F; Resolutividade = P / (P + F);
- CSAT, TMR Geral e TMA Humano vêm de `opa_overview_service.overview_metrics` (mesmos números da Visão Geral).
  TMR/TMA só existem para parte dos atendimentos (o histórico é preenchido pelo backfill noturno, dos mais
  recentes para os mais antigos): cada cartão leva a cobertura e, abaixo de `MIN_COVERAGE_PERCENT`, vira "parcial"
  em vez de julgar a meta - uma média de poucos atendimentos (ex.: 94 h de TMA) enganava o painel. A cobertura é
  medida sobre os atendimentos ENCERRADOS QUE CHEGARAM A UM HUMANO (conversa só do bot nunca tem TMA, então
  contar todos os encerrados acusava "parcial" em período 100% calculado), e o período anterior só entra na
  comparação se a cobertura dele também for boa (senão a variação comparava com uma amostra viesada).
  Os filtros de departamento e colaborador (atendente) do OPA valem para os cartões do OPA; os do IXC não têm
  essa dimensão.

A comparação é com o período imediatamente anterior, de mesmo tamanho. As metas abaixo foram passadas pelo
usuário; cards sem meta saem sem status.
"""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.operations.models import OperationOrder
from app.modules.operations.scope import PRIMARY_SECTOR_NAMES

from . import ixc_n1, ixc_new_login, opa_overview_service
from .ixc_ticket_queries import _previous_period_bounds
from .models import SupportIxcTicket, SupportIxcUser, SupportOpaAttendance, SupportOpaDimension
from .opa_filters import OpaAttendanceFilters, apply_opa_attendance_filters

logger = logging.getLogger(__name__)

# Meta de cada card: valor e sentido. "min" = quanto maior melhor; "max" = quanto menor melhor.
CSAT_TARGET = 4.5
TMR_TARGET_SECONDS = 120.0
TMA_TARGET_SECONDS = 3600.0
RESOLUTIVITY_TARGET_PERCENT = 80.0

# Margem abaixo (ou acima) da meta em que o card ainda é "Atenção" em vez de "Crítico".
ATTENTION_MARGIN = 0.10

# Abaixo disso de cobertura, a média do OPA é de uma amostra pequena e não é comparada com a meta.
MIN_COVERAGE_PERCENT = 50.0


def metric_status(value: float | None, target: float | None, direction: str) -> str:
    """ok = bateu a meta; attention = a até 10% da meta; critical = pior que isso;
    no_data = sem valor no período; no_target = card sem meta definida."""
    if target is None:
        return "no_target"
    if value is None:
        return "no_data"
    if direction == "min":
        if value >= target:
            return "ok"
        return "attention" if value >= target * (1 - ATTENTION_MARGIN) else "critical"
    if value <= target:
        return "ok"
    return "attention" if value <= target * (1 + ATTENTION_MARGIN) else "critical"


def _n1_field_orders(db: Session, date_from: date, date_to: date) -> int:
    """O.S. abertas no período por colaboradores dos grupos N1 (casamento por nome, sem caixa/espaços)."""
    n1_names = ixc_n1.n1_user_name_keys()
    query = select(func.count(OperationOrder.id)).where(
        func.lower(func.trim(OperationOrder.creator)).in_(n1_names),
        OperationOrder.sector.in_(PRIMARY_SECTOR_NAMES),
    )
    query = ixc_n1.apply_period_utc(query, OperationOrder.opened_at, date_from, date_to)
    return int(db.scalar(query) or 0)


def _n1_field_orders_by_day(db: Session, date_from: date, date_to: date) -> dict[str, int]:
    n1_names = ixc_n1.n1_user_name_keys()
    day = func.date(OperationOrder.opened_at)
    query = (
        select(day, func.count(OperationOrder.id))
        .where(func.lower(func.trim(OperationOrder.creator)).in_(n1_names), OperationOrder.sector.in_(PRIMARY_SECTOR_NAMES))
        .group_by(day)
    )
    query = ixc_n1.apply_period_utc(query, OperationOrder.opened_at, date_from, date_to)
    # SQLite (testes) devolve texto, Postgres devolve `date` - normaliza pra ISO.
    return {str(row_day)[:10]: int(count) for row_day, count in db.execute(query).all()}


def _ixc_daily(db: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Um ponto por dia (inclusive os zerados): protocolos N1 solucionados, O.S. para campo e o total."""
    field_by_day = _n1_field_orders_by_day(db, date_from, date_to)
    points = []
    for point in ixc_n1._daily_series(db, date_from, date_to, "n1"):
        solved = point["operational"] + point["financial"]
        field = field_by_day.get(point["day"].isoformat(), 0)
        points.append({"day": point["day"], "solved": solved, "field": field, "performed": solved + field})
    # Atendimentos N2 (motivos 80 + 81) por dia, para o mini-gráfico do cartão "Total de atendimentos N2".
    n2_points = ixc_n1._daily_series(db, date_from, date_to, "n2")
    for point, n2_point in zip(points, n2_points, strict=True):
        point["n2_total"] = n2_point["operational"] + n2_point["financial"]
    return points


# Equipe do Suporte Técnico (OPA) que aparece FIXA no filtro "Colaborador" dos Indicadores do Suporte (lista
# informada pelo usuário em 2026-10-15). Cada item é (nome mostrado, nome do usuário no cadastro do OPA). O OPA não
# traz o departamento de cada usuário, então a equipe é uma lista fixa: quem entrar ou sair precisa ser editado aqui.
# "Wendher Moura" e "Wendher Lopes de Moura" são o MESMO usuário do OPA (mesmo id; o nome mudou), então é um item só.
SUPPORT_TEAM: tuple[tuple[str, str], ...] = (
    ("Maycon Batista", "Maycon Batista"),
    ("Eduardo Leite", "Eduardo Leite"),
    ("Julio César", "Julio César"),
    ("Weslley Meguro", "Weslley Meguro"),
    ("Vinicius Burg", "Vinicius Burg"),
    ("Kaline Vitoria", "Kaline Vitoria"),
    ("Vinicius Santiago", "Vinicius Santiago"),
    ("Jennyfer Tavares", "Jennyfer Tavares"),
    ("Bruna Vieira", "Bruna Vieira"),
    ("Joao Barbosa", "Joao Barbosa"),
    ("Lucas de Oliveira", "Lucas de Oliveira"),
    ("Emanuele Araújo", "Emanuele Araújo"),
    ("Anna Andrade", "Anna Andrade"),
    ("Bruno Assis", "Bruno Assis"),
    ("Adelaidy Vitoria", "Adelaidy Vitoria"),
    ("Wendher Lopes de Moura", "Wendher Moura"),
    ("Gabrieli Milani", "Gabrieli Milani"),
    ("Ana Virgínia", "Ana Virgínia"),
    ("Anna Heloisa", "Anna Heloisa"),
    ("Welington Souza", "Welington Souza"),
    ("Matheus Henrique", "Matheus Henrique"),
    ("Willamy Carrilho", "Willamy Carrilho"),
    ("Weverton Cordeiro", "Weverton Cordeiro"),
)


def support_team_options(db: Session) -> list[dict[str, str]]:
    """Opções do filtro "Colaborador": a equipe fixa acima, com o id do usuário no OPA (cadastro `user`) para o
    filtro por atendente. Quem ainda não existe no cadastro do OPA fica de fora até aparecer lá."""
    rows = db.execute(
        select(SupportOpaDimension.source_id, SupportOpaDimension.name).where(
            SupportOpaDimension.dimension_type == "user",
            func.lower(func.trim(SupportOpaDimension.name)).in_([opa_name.lower() for _, opa_name in SUPPORT_TEAM]),
        )
    ).all()
    id_by_name = {str(name).strip().lower(): source_id for source_id, name in rows}
    return [
        {"value": id_by_name[opa_name.lower()], "label": label}
        for label, opa_name in SUPPORT_TEAM
        if opa_name.lower() in id_by_name
    ]


def time_coverage(db: Session, filters: OpaAttendanceFilters) -> dict[str, Any]:
    """Quantos dos atendimentos encerrados que chegaram a um humano já têm os tempos calculados pela regra do OPA
    (`active_metrics_at`). TMA, TMR Geral e TMR Humano são preenchidos na mesma passada (sincronização,
    backfill noturno e comando de recálculo), então isso mede o andamento do histórico para os três; as lacunas
    naturais do TMR (sem mensagem do cliente) não contam como atraso."""
    eligible_where = (SupportOpaAttendance.closed_at.isnot(None), SupportOpaAttendance.reached_human.is_(True))
    eligible = int(db.scalar(apply_opa_attendance_filters(select(func.count(SupportOpaAttendance.id)).where(*eligible_where), filters)) or 0)
    processed = int(
        db.scalar(
            apply_opa_attendance_filters(
                select(func.count(SupportOpaAttendance.id)).where(*eligible_where, SupportOpaAttendance.active_metrics_at.isnot(None)),
                filters,
            )
        )
        or 0
    )
    return opa_overview_service.coverage(processed, eligible)


def _opa_daily(db: Session, filters: OpaAttendanceFilters) -> list[dict[str, Any]]:
    return [
        {
            "day": point["day"],
            "rating": point["average_rating"],
            "tmr_seconds": point["average_tmr_effective_seconds"],
            "tmr_human_seconds": point["average_tmr_human_live_seconds"],
            "tma_seconds": point["average_tma_effective_seconds"],
        }
        for point in opa_overview_service.daily_timeseries(db, filters)
    ]


def _n2_orders(db: Session, date_from: date, date_to: date) -> int:
    """O.S. abertas pelos colaboradores N2 no período."""
    query = select(func.count(OperationOrder.id)).where(
        func.lower(func.trim(OperationOrder.creator)).in_(ixc_n1.n2_user_name_keys()),
        OperationOrder.sector.in_(PRIMARY_SECTOR_NAMES),
    )
    return int(db.scalar(ixc_n1.apply_period_utc(query, OperationOrder.opened_at, date_from, date_to)) or 0)


def _new_login_live(db: Session, live_future: Future | None) -> dict[str, Any]:
    """Ativação de Novo Login (assunto 74) finalizadas no período, perguntando ao IXC (ver `ixc_new_login`).
    A consulta já foi disparada em outra thread (`live_future`) e roda junto com as consultas ao banco.
    Se o IXC estiver fora do ar ou lento o indicador sai como indisponível (`None` + mensagem), nunca como zero."""
    try:
        if live_future is None:
            raise RuntimeError("sem consulta ao IXC")
        live = live_future.result()
    except Exception:  # noqa: BLE001 - qualquer falha do IXC derruba só este indicador, não o dashboard
        logger.warning("Falha ao consultar Ativação de Novo Login no IXC", exc_info=True)
        return {
            "new_login_finalized": None,
            "new_login_finalized_by_n2": None,
            "new_login_error": "IXC indisponível no momento. Tente novamente em instantes.",
        }
    n2_keys = set(db.scalars(ixc_n1.n2_user_name_keys()).all())
    by_n2 = sum(count for raw_name, count in live["by_name"].items() if raw_name.strip().lower() in n2_keys)
    return {"new_login_finalized": live["finalized"], "new_login_finalized_by_n2": by_n2, "new_login_error": None}


def n2_by_collaborator(db: Session, date_from: date, date_to: date) -> dict[str, Any]:
    """Por colaborador N2 da lista: atendimentos Interno (motivo 80) e Externo (81) que abriu e O.S. que abriu.
    `others`: protocolos N2 abertos por quem NÃO está na lista (ou sem operador), para a tabela fechar com o total."""
    users = db.execute(
        select(SupportIxcUser.ixc_user_id, SupportIxcUser.name, SupportIxcUser.active).where(
            SupportIxcUser.ixc_user_id.in_(ixc_n1.N2_IXC_USER_IDS)
        )
    ).all()
    protocols_query = (
        select(SupportIxcTicket.opened_by_user_id, SupportIxcTicket.subject_id, func.count(SupportIxcTicket.id))
        .where(
            SupportIxcTicket.subject_id.in_(ixc_n1.N2_SUBJECT_IDS),
            SupportIxcTicket.opened_by_user_id.in_(ixc_n1.N2_IXC_USER_IDS),
        )
        .group_by(SupportIxcTicket.opened_by_user_id, SupportIxcTicket.subject_id)
    )
    protocols: dict[tuple[str, str], int] = {
        (user_id, subject_id): int(count)
        for user_id, subject_id, count in db.execute(ixc_n1.apply_period_utc(protocols_query, SupportIxcTicket.created_at, date_from, date_to)).all()
    }
    creator_key = func.lower(func.trim(OperationOrder.creator))
    orders_query = (
        select(creator_key, func.count(OperationOrder.id))
        .where(creator_key.in_(ixc_n1.n2_user_name_keys()), OperationOrder.sector.in_(PRIMARY_SECTOR_NAMES))
        .group_by(creator_key)
    )
    orders = {key: int(count) for key, count in db.execute(ixc_n1.apply_period_utc(orders_query, OperationOrder.opened_at, date_from, date_to)).all()}

    rows = []
    for user_id, name, active in users:
        internal = protocols.get((user_id, ixc_n1.N2_INTERNAL_SUBJECT_ID), 0)
        external = protocols.get((user_id, ixc_n1.N2_EXTERNAL_SUBJECT_ID), 0)
        rows.append(
            {
                "user_id": user_id,
                "name": name or f"Usuário {user_id}",
                "active": bool(active),
                "internal": internal,
                "external": external,
                "total": internal + external,
                "orders": orders.get(str(name or "").strip().lower(), 0),
            }
        )
    rows.sort(key=lambda row: (-(row["total"] + row["orders"]), row["name"].lower()))
    totals = ixc_n1._totals(db, date_from, date_to, "n2")
    return {
        "rows": rows,
        "others_internal": totals["operational"] - sum(row["internal"] for row in rows),
        "others_external": totals["financial"] - sum(row["external"] for row in rows),
    }


def _n2_block(db: Session, date_from: date, date_to: date, live_future: Future | None) -> dict[str, Any]:
    # No N2 a API devolve "operational" = motivo 80 (interno) e "financial" = motivo 81 (externo).
    protocols = ixc_n1._totals(db, date_from, date_to, "n2")
    return {
        "internal": protocols["operational"],
        "external": protocols["financial"],
        "total": protocols["operational"] + protocols["financial"],
        "orders": _n2_orders(db, date_from, date_to),
        **_new_login_live(db, live_future),
    }


def _ixc_block(db: Session, date_from: date, date_to: date) -> dict[str, float | int | None]:
    protocols = ixc_n1._totals(db, date_from, date_to, "n1")
    solved = protocols["operational"] + protocols["financial"]
    field = _n1_field_orders(db, date_from, date_to)
    performed = solved + field
    return {
        "performed": performed,
        "field": field,
        "solved": solved,
        "resolutivity": (solved / performed) * 100 if performed else None,
    }


def _card(
    key: str,
    label: str,
    unit: str,
    current: float | int | None,
    previous: float | int | None,
    *,
    target: float | None = None,
    direction: str = "min",
    source: str,
    note: str | None = None,
    coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    change = None if current is None or previous is None else current - previous
    status = metric_status(current, target, direction)
    if (
        coverage is not None
        and status not in ("no_data", "no_target")
        and (coverage["percentage"] or 0) < MIN_COVERAGE_PERCENT
    ):
        status = "partial"
    return {
        "key": key,
        "label": label,
        "unit": unit,
        "value": current,
        "previous": previous,
        "change": change,
        "target": target,
        "direction": direction,
        "status": status,
        "coverage": coverage,
        "source": source,
        "note": note,
    }


def month_week_buckets(reference: date) -> list[dict[str, Any]]:
    """Semanas (domingo a sábado, cortadas nos limites do mês) do mês de `reference`, mais a última
    semana do mês anterior e o mês inteiro - o desenho do gráfico "Evolução semanal" do painel de metas
    (ex.: outubro/2026 = 27/09-30/09, 01/10-03/10, 04/10-10/10, ..., 25/10-31/10 e o mensal)."""
    month_start = reference.replace(day=1)
    next_month_start = (month_start + timedelta(days=32)).replace(day=1)
    month_end = next_month_start - timedelta(days=1)
    previous_end = month_start - timedelta(days=1)
    previous_start = max(previous_end - timedelta(days=(previous_end.weekday() + 1) % 7), previous_end.replace(day=1))

    buckets: list[dict[str, Any]] = [{"key": "previous_last_week", "label": "Última semana", "from": previous_start, "to": previous_end}]
    cursor, number = month_start, 1
    while cursor <= month_end:
        week_end = min(cursor + timedelta(days=(5 - cursor.weekday()) % 7), month_end)
        buckets.append({"key": f"week_{number}", "label": f"{number}ª semana", "from": cursor, "to": week_end})
        cursor, number = week_end + timedelta(days=1), number + 1
    buckets.append({"key": "month", "label": "Mensal", "from": month_start, "to": month_end})
    return buckets


def weekly_evolution(db: Session, reference: date) -> dict[str, Any]:
    """Uma única série diária cobrindo todas as semanas (4 consultas no total) agregada em Python. Antes cada
    uma das ~7 semanas fazia as suas próprias consultas (~16), o que pesava na abertura do dashboard."""
    buckets = month_week_buckets(reference)
    daily = {point["day"]: point for point in _ixc_daily(db, min(b["from"] for b in buckets), max(b["to"] for b in buckets))}
    items = []
    for bucket in buckets:
        points = [daily[day] for day in daily if bucket["from"] <= day <= bucket["to"]]
        solved = sum(point["solved"] for point in points)
        field = sum(point["field"] for point in points)
        performed = solved + field
        items.append(
            {
                "key": bucket["key"],
                "label": bucket["label"],
                "date_from": bucket["from"],
                "date_to": bucket["to"],
                "performed": performed,
                "field": field,
                "solved": solved,
                "resolutivity": (solved / performed) * 100 if performed else None,
            }
        )
    return {
        "month": reference.strftime("%Y-%m"),
        "resolutivity_target": RESOLUTIVITY_TARGET_PERCENT,
        "buckets": items,
    }


def macro_dashboard(
    db: Session, *, date_from: date, date_to: date, department_id: str | None = None, attendant_id: str | None = None
) -> dict[str, Any]:
    """Dispara as consultas ao IXC (Novo Login, período atual e anterior) em threads, para rodarem JUNTO com as
    consultas ao banco em vez de somar ao tempo total; a sessão do banco só é usada nesta thread."""
    bounds = _previous_period_bounds(date_from, date_to)
    with ThreadPoolExecutor(max_workers=2) as pool:
        live_current = pool.submit(ixc_new_login.finalized_in_period, date_from, date_to)
        live_previous = pool.submit(ixc_new_login.finalized_in_period, *bounds) if bounds else None
        return _macro_dashboard(db, date_from, date_to, live_current, live_previous, department_id, attendant_id)


def _macro_dashboard(
    db: Session, date_from: date, date_to: date, live_current: Future, live_previous: Future | None,
    department_id: str | None, attendant_id: str | None,
) -> dict[str, Any]:
    bounds = _previous_period_bounds(date_from, date_to)
    previous_from, previous_to = bounds if bounds else (None, None)

    current_ixc = _ixc_block(db, date_from, date_to)
    previous_ixc = (
        _ixc_block(db, previous_from, previous_to)
        if previous_from and previous_to
        else {"performed": None, "field": None, "solved": None, "resolutivity": None}
    )

    current_n2_total = sum(ixc_n1._totals(db, date_from, date_to, "n2").values())
    previous_n2_total = sum(ixc_n1._totals(db, previous_from, previous_to, "n2").values()) if previous_from and previous_to else None

    filters = OpaAttendanceFilters(date_from=date_from, date_to=date_to, department_id=department_id or None, attendant_id=attendant_id or None)
    current_opa = opa_overview_service.overview_metrics(db, filters)
    previous_filters = filters.previous_period()
    previous_opa = opa_overview_service.overview_metrics(db, previous_filters)
    current_coverage = time_coverage(db, filters)
    previous_coverage = time_coverage(db, previous_filters)

    def previous_time(value):
        """Período anterior só serve de base se também tiver cobertura boa; senão a variação é enganosa."""
        return value if (previous_coverage["percentage"] or 0) >= MIN_COVERAGE_PERCENT else None

    cards = [
        _card(
            "csat", "Qualidade percebida na avaliação geral - OPA", "score",
            current_opa["average_rating"], previous_opa["average_rating"],
            target=CSAT_TARGET, direction="min", source="opa",
        ),
        _card(
            "tmr", "Tempo médio de resposta ao cliente - OPA", "seconds",
            current_opa["average_tmr_effective_seconds"], previous_time(previous_opa["average_tmr_effective_seconds"]),
            target=TMR_TARGET_SECONDS, direction="max", source="opa", note="TMR Geral (inclui as respostas do bot)",
            coverage=current_coverage,
        ),
        _card(
            "tmr_human", "TMR Humano - OPA", "seconds",
            current_opa["average_tmr_human_live_seconds"], previous_time(previous_opa["average_tmr_human_live_seconds"]),
            direction="max", source="opa", note="Só respostas de humano (sem o bot); sem meta definida",
            coverage=current_coverage,
        ),
        _card(
            "tma", "Tempo médio de atendimento - OPA", "seconds",
            current_opa["average_tma_effective_seconds"], previous_time(previous_opa["average_tma_effective_seconds"]),
            target=TMA_TARGET_SECONDS, direction="max", source="opa", note="TMA Humano (1ª msg do atendente até a conclusão)",
            coverage=current_coverage,
        ),
        _card(
            "performed", "Quantidade de atendimentos realizados - IXC", "count",
            current_ixc["performed"], previous_ixc["performed"], source="ixc",
            note="Protocolos N1 (operacional + financeiro) + O.S. abertas para campo pelo N1",
        ),
        _card(
            "field", "Quantidade de atendimentos que foi a campo - IXC", "count",
            current_ixc["field"], previous_ixc["field"], source="ixc",
            note="O.S. abertas pelos colaboradores N1 (vínculo pelo nome do criador da O.S.)",
        ),
        _card(
            "solved", "Quantidade de atendimentos solucionados - IXC", "count",
            current_ixc["solved"], previous_ixc["solved"], source="ixc",
            note="Protocolos N1 operacionais + financeiros",
        ),
        _card(
            "resolutivity", "Resolutividade - IXC", "percent",
            current_ixc["resolutivity"], previous_ixc["resolutivity"],
            target=RESOLUTIVITY_TARGET_PERCENT, direction="min", source="ixc",
            note="Solucionados ÷ (solucionados + O.S. para campo)",
        ),
        _card(
            "n2_total", "Total de atendimentos N2 - IXC", "count",
            current_n2_total, previous_n2_total, source="ixc",
            note="Atendimento Interno N2 (motivo 80) + Externo N2 (motivo 81)",
        ),
    ]
    return {
        "date_from": date_from,
        "date_to": date_to,
        "previous_date_from": previous_from,
        "previous_date_to": previous_to,
        "cards": cards,
        # Séries diárias do recorte (mini-gráficos dos cartões e fluxo diário) e do período anterior, que
        # a tela alinha por posição do dia (dia 1 com dia 1), como o resto da Visão Geral.
        "daily": [
            {**ixc_point, **{key: value for key, value in opa_point.items() if key != "day"}}
            for ixc_point, opa_point in zip(_ixc_daily(db, date_from, date_to), _opa_daily(db, filters), strict=True)
        ],
        "previous_daily": _ixc_daily(db, previous_from, previous_to) if previous_from and previous_to else [],
        # Suporte N2: protocolos (motivos 80 e 81), O.S. abertas por eles e Ativação de Novo Login finalizada.
        "n2": _n2_block(db, date_from, date_to, live_current),
        "n2_collaborators": n2_by_collaborator(db, date_from, date_to),
        "previous_n2": _n2_block(db, previous_from, previous_to, live_previous) if previous_from and previous_to else None,
        # Evolução semanal do mês de `date_to` (independe do recorte escolhido: sempre o mês inteiro).
        "weekly": weekly_evolution(db, date_to),
    }
