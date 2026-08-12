from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import Numeric, String, and_, case, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from app.models import User
from app.modules.operations import queries as operations_queries
from app.modules.operations.models import (
    OperationBacklogSnapshot,
    OperationOrder,
    OperationResponsibleAssignment,
    OperationTeamModel,
    OperationTeamTargetVersion,
)
from app.modules.operations.period import local_period_utc_bounds
from app.modules.operations.schemas import OperationFilters, _service_address_from_payload, _text_from_payload
from app.services.regional import effective_managed_regionals

# As mesmas 9 dimensões que a tela de Operação já deixa filtrar/agrupar hoje (regional, cidade,
# tipo de O.S., assunto, diagnóstico, setor, prioridade, responsável, status) - deliberadamente um
# dict novo aqui, não reaproveitado de operations.queries, porque lá as listas de dimensão
# permitida variam por função (`FILTER_COLUMNS` é pra filtro, no plural; `in_progress_breakdown`/
# `sla_breakdown` têm cada uma seu próprio subconjunto no singular). Esta é a lista de agrupamento
# do módulo `ai`, que é uma decisão de produto própria dele.
AGGREGATION_DIMENSIONS = {
    "regional": OperationOrder.regional,
    "city": OperationOrder.city,
    # Confirmado contra amostra real de 104k+ O.S. (ver migration 20260811_0048) - permite achar
    # concentração de O.S. por bairro (pedido original: "quais bairros geram mais manutenção").
    "neighborhood": OperationOrder.neighborhood,
    "os_type": OperationOrder.os_type,
    "subject": OperationOrder.os_subject,
    "diagnosis": OperationOrder.diagnosis,
    "department": OperationOrder.department,
    "sector": OperationOrder.sector,
    "priority": OperationOrder.priority,
    "responsible": OperationOrder.responsible,
    "status": OperationOrder.status,
    "sla_status": OperationOrder.sla_status,
}

AggregationMetric = Literal[
    "quantidade_aberta", "quantidade_fechada", "taxa_sla", "horas_medias",
    "quantidade_atrasada", "quantidade_backlog",
    # Métricas de etapa de SLA (ver _sla_stage_duration_columns) - horas médias entre dois marcos
    # consecutivos do ciclo de vida da O.S., pra achar em qual etapa o tempo foi de fato perdido.
    "horas_abertura_agenda", "horas_agenda_execucao", "horas_execucao_fechamento", "horas_abertura_fechamento",
]

# Pares (início, fim) de cada métrica de horas por etapa acima - todas medidas em relação a O.S.
# fechadas no período (mesmo corte de "horas_medias"), exigindo que os dois marcos existam.
_SLA_STAGE_DURATION_COLUMNS = {
    "horas_abertura_agenda": (OperationOrder.opened_at, OperationOrder.scheduled_at),
    "horas_agenda_execucao": (OperationOrder.scheduled_at, OperationOrder.execution_started_at),
    "horas_execucao_fechamento": (OperationOrder.execution_started_at, OperationOrder.closed_at),
    "horas_abertura_fechamento": (OperationOrder.opened_at, OperationOrder.closed_at),
}


EARTH_RADIUS_KM = 6371.0

# Tamanho da célula do "cluster geográfico" (ver `_group_label`, caso "geo_cluster") - 3 casas
# decimais de lat/long equivalem a ~111m na latitude (a longitude varia um pouco menos conforme se
# afasta do equador, mas a escala pedida - "mesmo ponto"/cluster de LOS - não exige precisão
# geodésica exata, só agrupar pontos praticamente coincidentes).
GEO_CLUSTER_DECIMALS = 3


def _haversine_km_expr(lat_column, lng_column, ref_latitude: float, ref_longitude: float):
    """Distância aproximada (fórmula de Haversine, em km) entre cada O.S. e um ponto de
    referência, em SQL puro - usa só funções trigonométricas padrão (sin/cos/acos/radians),
    disponíveis tanto no Postgres quanto no SQLite usado nos testes (builds modernos do SQLite já
    trazem essas funções de fábrica), sem precisar de extensão geoespacial (PostGIS) nem de
    ramificação por dialeto."""
    ref_lat_rad = func.radians(ref_latitude)
    ref_lng_rad = func.radians(ref_longitude)
    lat_rad = func.radians(lat_column)
    lng_rad = func.radians(lng_column)
    cos_angle = (
        func.sin(lat_rad) * func.sin(ref_lat_rad)
        + func.cos(lat_rad) * func.cos(ref_lat_rad) * func.cos(lng_rad - ref_lng_rad)
    )
    # CASE em vez de LEAST/GREATEST (que não existem no SQLite, só no Postgres) - imprecisão de
    # ponto flutuante pode deixar o cosseno levemente fora de [-1, 1] quando o ponto de referência
    # é (quase) o mesmo da O.S., o que travaria `acos()` com erro de domínio bem no caso de uso
    # mais comum (buscar reincidência no mesmo ponto de uma O.S. já existente).
    clamped_cos_angle = case(
        (cos_angle > 1.0, 1.0),
        (cos_angle < -1.0, -1.0),
        else_=cos_angle,
    )
    return EARTH_RADIUS_KM * func.acos(clamped_cos_angle)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Mesma fórmula de `_haversine_km_expr`, em Python - usada em `search_orders` (que já carrega
    o objeto `OperationOrder` inteiro) para anexar a distância de cada item ao ponto de referência
    sem precisar de mais uma query SQL."""
    lat1_r, lng1_r, lat2_r, lng2_r = (math.radians(v) for v in (lat1, lng1, lat2, lng2))
    cos_angle = math.sin(lat1_r) * math.sin(lat2_r) + math.cos(lat1_r) * math.cos(lat2_r) * math.cos(lng2_r - lng1_r)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return EARTH_RADIUS_KM * math.acos(cos_angle)


def _geo_filter_conditions(filters: dict) -> list:
    """Filtros geográficos de `AiOrderFilters`: `has_coordinates` (True/False) e a combinação
    `near_latitude`+`near_longitude`+`radius_km` (raio de busca) - só aplica o raio quando os três
    vêm juntos, mesmo critério de "só ativa quando todos os pedaços estão definidos" já usado em
    `custom_window` (operations/queries.py)."""
    conditions = []
    has_coordinates = filters.get("has_coordinates")
    if has_coordinates is True:
        conditions.append(and_(OperationOrder.latitude.is_not(None), OperationOrder.longitude.is_not(None)))
    elif has_coordinates is False:
        conditions.append(or_(OperationOrder.latitude.is_(None), OperationOrder.longitude.is_(None)))

    near_latitude = filters.get("near_latitude")
    near_longitude = filters.get("near_longitude")
    radius_km = filters.get("radius_km")
    if near_latitude is not None and near_longitude is not None and radius_km is not None:
        distance = _haversine_km_expr(OperationOrder.latitude, OperationOrder.longitude, near_latitude, near_longitude)
        conditions.append(
            and_(
                OperationOrder.latitude.is_not(None),
                OperationOrder.longitude.is_not(None),
                distance <= radius_km,
            )
        )
    return conditions


def _hours_diff_expr(db: Session, end_column, start_column):
    """Diferença em horas entre duas colunas de timestamp, em SQL. `func.extract("epoch", a - b)`
    só é portável no Postgres - no SQLite (usado nos testes) a subtração de duas colunas DATETIME
    não produz um intervalo que "epoch" saiba extrair, então usa `julianday` (mesma ramificação de
    `operations_queries._execution_hours`, que já resolveu esse mesmo problema)."""
    if db.get_bind().dialect.name == "postgresql":
        return func.extract("epoch", end_column - start_column) / 3600.0
    return (func.julianday(end_column) - func.julianday(start_column)) * 24.0


def _scheduled_after_sla_expr(db: Session):
    """"Agendamento ocorreu após o deadline do SLA" (opened_at + sla_target_hours) - só tem
    resposta (True/False) quando a O.S. TEM meta de SLA e TEM agendamento; sem um dos dois vira
    NULL (não "Não", que sugeriria falsamente que o agendamento foi dentro do prazo)."""
    hours_to_schedule = _hours_diff_expr(db, OperationOrder.scheduled_at, OperationOrder.opened_at)
    return case(
        (
            and_(OperationOrder.sla_target_hours.is_not(None), OperationOrder.scheduled_at.is_not(None)),
            hours_to_schedule > OperationOrder.sla_target_hours,
        ),
        else_=None,
    )


def _sla_expired_before_schedule_expr(db: Session, reference_at: datetime):
    """Generalização de `_scheduled_after_sla_expr` pra cobrir também O.S. que AINDA não foram
    agendadas: usa o agendamento quando existe (mesmo resultado do indicador acima); sem
    agendamento, usa o fechamento (se já fechou sem nunca ter sido agendada) ou `reference_at`
    (o "agora" da consulta, pra O.S. ainda aberta e sem agenda) - decisão tomada explicitamente
    com o usuário: O.S. aberta sem agenda deve contar como filtrável em tempo real, não ficar
    sempre None até fechar."""
    hours_to_schedule = _hours_diff_expr(db, OperationOrder.scheduled_at, OperationOrder.opened_at)
    hours_to_close = _hours_diff_expr(db, OperationOrder.closed_at, OperationOrder.opened_at)
    hours_to_reference = _hours_diff_expr(db, literal(reference_at), OperationOrder.opened_at)
    hours_elapsed_before_schedule = case(
        (OperationOrder.scheduled_at.is_not(None), hours_to_schedule),
        (OperationOrder.closed_at.is_not(None), hours_to_close),
        else_=hours_to_reference,
    )
    return case(
        (OperationOrder.sla_target_hours.is_not(None), hours_elapsed_before_schedule > OperationOrder.sla_target_hours),
        else_=None,
    )


def _sla_stage_filter_conditions(db: Session, filters: dict) -> list:
    """Filtros booleanos exatos (True/False) para `scheduled_after_sla`/`sla_expired_before_schedule`
    - `None` (chave ausente ou valor não informado) significa "não filtrar por isso", igual ao
    resto dos filtros deste módulo."""
    conditions = []
    if filters.get("scheduled_after_sla") is not None:
        conditions.append(_scheduled_after_sla_expr(db).is_(filters["scheduled_after_sla"]))
    if filters.get("sla_expired_before_schedule") is not None:
        conditions.append(
            _sla_expired_before_schedule_expr(db, datetime.now(timezone.utc)).is_(filters["sla_expired_before_schedule"])
        )
    return conditions


TimeseriesMetric = Literal["abertas", "fechadas", "saldo"]
Granularity = Literal["day", "week", "month"]

AI_SEARCH_MAX_PAGE_SIZE = 200

# Descrição de abertura - não é coluna própria, vive só dentro do `raw_payload` bruto do IXC
# ("mensagem", confirmado contra amostra real - ver RAW_PAYLOAD_DESCRIPTION_KEYS em
# operations/queries.py). `coalesce` reproduziria a regra de "primeira chave preenchida vence" de
# `_text_from_payload` se houvesse mais de uma chave - com uma só, usa a expressão direto: SQLite
# rejeita `coalesce()` com um único argumento (Postgres aceita, mas os testes rodam em SQLite).
_SERVICE_DESCRIPTION_CANDIDATES = [
    OperationOrder.raw_payload[key].as_string() for key in operations_queries.RAW_PAYLOAD_DESCRIPTION_KEYS
]
_SERVICE_DESCRIPTION_EXPR = (
    _SERVICE_DESCRIPTION_CANDIDATES[0]
    if len(_SERVICE_DESCRIPTION_CANDIDATES) == 1
    else func.coalesce(*_SERVICE_DESCRIPTION_CANDIDATES)
)

# Campos de texto livre onde "contém"/"começa com"/"termina com"/"diferente de" fazem sentido -
# não inclui campos tipo status_code, que são códigos curtos, não texto pra buscar por trecho.
TEXT_FILTER_COLUMNS = {
    "sector": OperationOrder.sector,
    "subject": OperationOrder.os_subject,
    "diagnosis": OperationOrder.diagnosis,
    "responsible": OperationOrder.responsible,
    "city": OperationOrder.city,
    "department": OperationOrder.department,
    "neighborhood": OperationOrder.neighborhood,
    "service_description": _SERVICE_DESCRIPTION_EXPR,
}


# Nomes de `operations_queries.FILTER_COLUMNS` que `AiOrderFilters` (ai/schemas.py) também aceita
# - o único que fica de fora é "responsible_ixc_ids" (id bruto do IXC, não exposto à IA). Definido
# aqui (e não derivado de `AiOrderFilters` diretamente) para evitar import circular: ai/schemas.py
# já importa `AGGREGATION_DIMENSIONS` deste módulo.
AI_ORDER_FILTER_FIELDS = set(operations_queries.FILTER_COLUMNS) - {"responsible_ixc_ids"}


# Colunas expostas à IA por mecanismo próprio, não coberto pelos três dicionários abaixo
# (AGGREGATION_DIMENSIONS/TEXT_FILTER_COLUMNS/FILTER_COLUMNS): latitude/longitude são valores
# contínuos, não fazem sentido como dimensão de agrupamento exata nem filtro de texto - mas SÃO
# usadas pelo filtro geográfico (`has_coordinates`/`near_latitude`/`near_longitude`/`radius_km`,
# ver `_geo_filter_conditions`) e pela dimensão calculada "geo_cluster" (`_group_label`), além de
# virem nos itens de `search_orders`.
MANUALLY_EXPOSED_COLUMNS = {"latitude", "longitude"}


def available_fields() -> dict:
    """Introspecciona `OperationOrder.__table__` e compara com o que já está exposto à IA
    (dimensões de agrupamento, filtros de texto livre e filtros exatos de `AiOrderFilters`) -
    usado pelo endpoint `/ai/fields` para a própria IA (ou quem estiver configurando as
    ferramentas) descobrir o que ainda não tem cobertura, sem precisar ler o código-fonte."""
    all_fields = sorted(OperationOrder.__table__.columns.keys())
    exposed_columns = {column.key for column in AGGREGATION_DIMENSIONS.values()}
    # `getattr(..., "key", None)` porque "service_description" (acima) é uma expressão SQL
    # calculada a partir do JSON bruto, não uma `Column` de verdade - não tem `.key` e não
    # corresponde a nenhum campo isolado de `OperationOrder.__table__` (só faz sentido excluir,
    # não contar como coluna "exposta" nem afetar a lista de "não exposta").
    exposed_columns |= {
        key for column in TEXT_FILTER_COLUMNS.values() if (key := getattr(column, "key", None)) is not None
    }
    exposed_columns |= {
        operations_queries.FILTER_COLUMNS[field].key for field in AI_ORDER_FILTER_FIELDS
    }
    exposed_columns |= MANUALLY_EXPOSED_COLUMNS
    exposed_to_ai = sorted(exposed_columns)
    not_exposed = sorted(set(all_fields) - exposed_columns)
    return {"all_fields": all_fields, "exposed_to_ai": exposed_to_ai, "not_exposed": not_exposed}


def _escape_like(value: str) -> str:
    """Escapa os caracteres especiais do LIKE/ILIKE (`%`, `_`, e a própria barra de escape) antes
    de embutir o valor do usuário no padrão - sem isso, um valor com "%" ou "_" se comportaria
    como wildcard em vez de caractere literal."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _text_operator_condition(column, operator: str, raw_value: str):
    if operator == "not_equals":
        return func.lower(column) != raw_value.lower()
    escaped = _escape_like(raw_value)
    pattern = {
        "contains": f"%{escaped}%",
        "starts_with": f"{escaped}%",
        "ends_with": f"%{escaped}",
    }.get(operator)
    return column.ilike(pattern, escape="\\") if pattern is not None else None


def _text_filter_conditions(text_filters: list[dict] | None) -> list:
    conditions = []
    for item in text_filters or []:
        column = TEXT_FILTER_COLUMNS.get(item["field"])
        if column is None:
            continue
        condition = _text_operator_condition(column, item["operator"], item["value"])
        if condition is not None:
            conditions.append(condition)
    return conditions


def _dimension_conditions_with_text(db: Session, user: User, filters: dict, *, opening: bool = False) -> list:
    """Wrapper fino sobre `operations_queries._dimension_conditions` - aplica os filtros exatos
    de sempre e, além deles, os filtros textuais novos (item 10), que não existem no motor de
    filtro do resto do sistema."""
    base_filters = operations_queries._opening_filters(filters) if opening else filters
    conditions = operations_queries._dimension_conditions(db, user, base_filters)
    conditions.extend(_text_filter_conditions(filters.get("text_filters")))
    conditions.extend(_sla_stage_filter_conditions(db, filters))
    conditions.extend(_geo_filter_conditions(filters))
    return conditions


def _group_labels(group_by: str | list[str]) -> list[str]:
    """Normaliza `group_by` (uma dimensão ou várias) numa lista de 1 a 3 - limite pra não deixar
    o resultado explodir combinatorialmente (ex.: 20 regionais x 50 assuntos)."""
    dims = [group_by] if isinstance(group_by, str) else list(group_by)
    return dims[:3] or ["regional"]


def _group_label(db: Session, group_by: str):
    """"team_model" não é uma coluna de OperationOrder - é calculado casando o responsável contra
    a atribuição de modelo de equipe, SÓ PELO NOME (case-insensitive) - igual ao filtro
    `team_models` (`_dimension_conditions`, operations/queries.py:176-189) e ao resto do sistema
    (`team_configuration`, `work_schedule_overview`).

    Achado real corrigido aqui: uma versão anterior desta função também exigia que a regional da
    atribuição batesse com a regional da O.S. - isso divergia do filtro (que casa só pelo nome),
    então uma O.S. podia ENTRAR no resultado de `team_models=["X"]` mas aparecer como "Não
    identificado" em `group_by="team_model"`, porque a atribuição de "X" para aquele responsável
    existia numa regional diferente da regional daquela O.S. específica. Quando o mesmo
    responsável tem atribuições em mais de uma regional, prevalece a mais recentemente atualizada
    - mesmo critério de `team_configuration` (`operations/queries.py:2154-2156`)."""
    if group_by == "team_model":
        team_model_name = (
            select(OperationTeamModel.name)
            .join(OperationResponsibleAssignment, OperationResponsibleAssignment.team_model_id == OperationTeamModel.id)
            .where(func.lower(OperationResponsibleAssignment.responsible_name) == func.lower(OperationOrder.responsible))
            .order_by(OperationResponsibleAssignment.updated_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        return func.coalesce(team_model_name, "Não identificado")
    if group_by == "scheduled_after_sla":
        expr = _scheduled_after_sla_expr(db)
        return case((expr.is_(True), "Sim"), (expr.is_(False), "Não"), else_="Sem meta/agendamento")
    if group_by == "sla_expired_before_schedule":
        expr = _sla_expired_before_schedule_expr(db, datetime.now(timezone.utc))
        return case((expr.is_(True), "Sim"), (expr.is_(False), "Não"), else_="Sem meta de SLA")
    if group_by == "geo_cluster":
        # Agrupa O.S. por ponto (quase) coincidente - arredonda lat/long pra GEO_CLUSTER_DECIMALS
        # casas (~111m) e concatena como rótulo "lat,long". `cast(..., Numeric)` antes do `round`
        # porque o Postgres não tem round(double precision, int) - só round(numeric, int); o
        # SQLite aceita os dois jeitos, então o cast não muda nada lá.
        #
        # Limitação conhecida (efeito de borda de qualquer clustering por grade): duas O.S. bem
        # próximas fisicamente podem cair em células vizinhas se a coordenada de uma delas ficar
        # do outro lado de um limite de arredondamento (ex.: -10.88349 vira -10.883, -10.88351 vira
        # -10.884, mesmo a ~2m de distância). Para "no mesmo ponto ou bem próximo" com garantia de
        # não perder vizinho de borda, prefira o filtro de raio (`near_latitude`/`near_longitude`/
        # `radius_km`, ver `_geo_filter_conditions`), que não sofre desse efeito.
        lat_rounded = func.round(cast(OperationOrder.latitude, Numeric), GEO_CLUSTER_DECIMALS)
        lng_rounded = func.round(cast(OperationOrder.longitude, Numeric), GEO_CLUSTER_DECIMALS)
        cluster_label = cast(lat_rounded, String).concat(",").concat(cast(lng_rounded, String))
        return case(
            (and_(OperationOrder.latitude.is_not(None), OperationOrder.longitude.is_not(None)), cluster_label),
            else_="Sem coordenadas",
        )
    field = AGGREGATION_DIMENSIONS.get(group_by, OperationOrder.regional)
    return func.coalesce(field, "Não identificado")


def _team_model_lookup(db: Session, orders: list[OperationOrder]) -> dict[str, str]:
    """Resolve o modelo de equipe de uma página de O.S. já carregada, numa única query extra (em
    vez de juntar essa tabela na query paginada principal). Casa só pelo nome do responsável
    (case-insensitive) - mesma regra de `_group_label`/o filtro `team_models` - com a atribuição
    mais recentemente atualizada prevalecendo quando o nome tem mais de uma (mesmo critério de
    `team_configuration`)."""
    names = {order.responsible.lower() for order in orders if order.responsible}
    if not names:
        return {}
    rows = db.execute(
        select(OperationResponsibleAssignment.responsible_name, OperationTeamModel.name)
        .join(OperationTeamModel, OperationTeamModel.id == OperationResponsibleAssignment.team_model_id)
        .where(func.lower(OperationResponsibleAssignment.responsible_name).in_(names))
        .order_by(OperationResponsibleAssignment.updated_at.desc())
    ).all()
    result: dict[str, str] = {}
    for responsible_name, team_model_name in rows:
        result.setdefault(responsible_name.lower(), team_model_name)
    return result


def _percentage(count: int, total: int) -> float:
    return round((count / total) * 100, 2) if total else 0.0


def _sla_risk_bucket(elapsed_hours: float | None, sla_target_hours: float | None) -> str:
    """Mesmos limiares de `operations_queries._sla_risk_bucket_case()` (queries.py:2228-2240),
    replicados em Python porque `search_orders` já carrega o objeto `OperationOrder` inteiro (não
    um select de colunas) - calcular aqui evita misturar ORM completo com expressão SQL bruta na
    mesma query. Se aqueles limiares mudarem lá, precisam mudar aqui também."""
    if not sla_target_hours or sla_target_hours <= 0:
        return "no_target"
    ratio = (elapsed_hours or 0) / sla_target_hours * 100
    if ratio >= 100:
        return "breached"
    if ratio >= 80:
        return "critical"
    if ratio >= 50:
        return "attention"
    return "on_track"


def aggregate_orders(
    db: Session,
    user: User,
    *,
    group_by: str | list[str],
    metric: AggregationMetric,
    date_from: date,
    date_to: date,
    **filters,
) -> list[dict]:
    """Agrupa O.S. por uma ou mais dimensões (até 3) e devolve, por grupo: `quantity` (nº de O.S.
    por trás do número), `metric_value` (o valor pedido - contagem, taxa de SLA ou horas médias) e
    `percentage` (fatia do grupo sobre o total de `quantity` entre todos os grupos). Os dois
    últimos têm significado diferente de propósito porque "taxa de SLA" e "horas médias" não são
    frações de um total, então não caberiam sozinhos num único campo `percentage`.

    Com 1 dimensão só, cada item da resposta tem um campo `label` (formato já em uso pelos
    conectores configurados). Com 2+ dimensões, `label` some e cada dimensão pedida aparece como
    sua própria chave (ex.: `{"regional": "...", "subject": "...", "quantity": ...}`) - aditivo,
    não quebra quem já chama com 1 dimensão só."""
    dims = _group_labels(group_by)
    labels = [_group_label(db, dim) for dim in dims]
    start, end = local_period_utc_bounds(date_from, date_to)

    if metric == "quantidade_aberta":
        conditions = _dimension_conditions_with_text(db, user, filters, opening=True)
        rows = db.execute(
            select(*labels, func.count(OperationOrder.id))
            .where(*conditions, OperationOrder.opened_at.between(start, end))
            .group_by(*labels)
        ).all()
        entries = [(row[:-1], int(row[-1]), float(row[-1])) for row in rows]

    elif metric == "taxa_sla":
        conditions = _dimension_conditions_with_text(db, user, filters)
        rows = db.execute(
            select(
                *labels,
                func.count(OperationOrder.id),
                func.sum(case((OperationOrder.sla_status == "on_time", 1), else_=0)),
            )
            .where(*conditions, OperationOrder.closed_at.between(start, end))
            .group_by(*labels)
        ).all()
        entries = [(row[:-2], int(row[-2]), _percentage(int(row[-1] or 0), int(row[-2]))) for row in rows]

    elif metric == "quantidade_atrasada":
        # Diferente de "quantidade_aberta" (que ignora de propósito equipe/responsável, porque
        # abertura é demanda), aqui o filtro de equipe faz sentido - queremos saber o atraso de
        # QUEM está com a O.S. hoje, então usa os filtros normais, não `_opening_filters`.
        conditions = _dimension_conditions_with_text(db, user, filters)
        rows = db.execute(
            select(*labels, func.count(OperationOrder.id))
            .where(
                *conditions,
                OperationOrder.is_closed.is_(False),
                OperationOrder.opened_at.between(start, end),
                OperationOrder.sla_status == "out_of_time",
            )
            .group_by(*labels)
        ).all()
        entries = [(row[:-1], int(row[-1]), float(row[-1])) for row in rows]

    elif metric == "quantidade_backlog":
        conditions = _dimension_conditions_with_text(db, user, filters)
        rows = db.execute(
            select(*labels, func.count(OperationOrder.id))
            .where(
                *conditions,
                OperationOrder.is_closed.is_(False),
                OperationOrder.opened_at.between(start, end),
            )
            .group_by(*labels)
        ).all()
        entries = [(row[:-1], int(row[-1]), float(row[-1])) for row in rows]

    elif metric == "horas_medias":
        conditions = _dimension_conditions_with_text(db, user, filters)
        elapsed = OperationOrder.elapsed_hours
        rows = db.execute(
            select(*labels, func.count(OperationOrder.id), func.avg(elapsed))
            .where(*conditions, OperationOrder.closed_at.between(start, end), elapsed.is_not(None))
            .group_by(*labels)
        ).all()
        entries = [(row[:-2], int(row[-2]), round(float(row[-1] or 0), 1)) for row in rows]

    elif metric in _SLA_STAGE_DURATION_COLUMNS:
        # Mesmo corte de período de "horas_medias" (O.S. fechada no período) - a diferença é o par
        # de marcos medido (ver _SLA_STAGE_DURATION_COLUMNS), pra localizar em qual etapa do ciclo
        # de vida da O.S. o tempo foi de fato perdido, não só o total abertura-fechamento.
        conditions = _dimension_conditions_with_text(db, user, filters)
        start_column, end_column = _SLA_STAGE_DURATION_COLUMNS[metric]
        duration = _hours_diff_expr(db, end_column, start_column)
        rows = db.execute(
            select(*labels, func.count(OperationOrder.id), func.avg(duration))
            .where(
                *conditions,
                OperationOrder.closed_at.between(start, end),
                start_column.is_not(None),
                end_column.is_not(None),
            )
            .group_by(*labels)
        ).all()
        entries = [(row[:-2], int(row[-2]), round(float(row[-1] or 0), 1)) for row in rows]

    else:  # "quantidade_fechada"
        conditions = _dimension_conditions_with_text(db, user, filters)
        rows = db.execute(
            select(*labels, func.count(OperationOrder.id))
            .where(*conditions, OperationOrder.closed_at.between(start, end))
            .group_by(*labels)
        ).all()
        entries = [(row[:-1], int(row[-1]), float(row[-1])) for row in rows]

    total = sum(count for _, count, _ in entries)
    results = []
    for label_values, count, metric_value in sorted(entries, key=lambda item: (-item[1], [str(v) for v in item[0]])):
        percentage = _percentage(count, total)
        if len(dims) == 1:
            item = {"label": str(label_values[0]), "quantity": count, "metric_value": metric_value, "percentage": percentage}
        else:
            item = {dim: str(value) for dim, value in zip(dims, label_values)}
            item.update({"quantity": count, "metric_value": metric_value, "percentage": percentage})
        results.append(item)
    return results


def orders_timeseries(
    db: Session,
    user: User,
    *,
    metric: TimeseriesMetric,
    granularity: Granularity,
    date_from: date,
    date_to: date,
    group_by: str | None = None,
    **filters,
) -> list[dict]:
    """Série temporal (dia/semana/mês) de abertas, fechadas, ou saldo (abertas - fechadas) por
    bucket - mesma lógica de bucketing de `operations_queries._period_group_start`.

    `group_by` é opcional: sem ele, cada ponto é `{period_start, quantity}` (formato já em uso).
    Com ele, cada ponto ganha `group` com o valor da dimensão naquele bucket (ex.: "quantidade
    fechada por dia por modelo de equipe") - aditivo, não muda a chamada sem `group_by`."""
    start, end = local_period_utc_bounds(date_from, date_to)
    opened_day = operations_queries._local_date(db, OperationOrder.opened_at)
    closed_day = operations_queries._local_date(db, OperationOrder.closed_at)
    label = _group_label(db, group_by) if group_by else None

    def _counts(day_expr, conditions, date_column) -> dict[tuple[date, str | None], int]:
        columns = (day_expr, label) if label is not None else (day_expr,)
        rows = db.execute(
            select(*columns, func.count(OperationOrder.id))
            .where(*conditions, date_column.between(start, end))
            .group_by(*columns)
        ).all()
        result: dict[tuple[date, str | None], int] = {}
        for row in rows:
            key = (row[0], str(row[1])) if label is not None else (row[0], None)
            result[key] = result.get(key, 0) + int(row[-1])
        return result

    opened_counts: dict[tuple[date, str | None], int] = {}
    closed_counts: dict[tuple[date, str | None], int] = {}

    if metric in ("abertas", "saldo"):
        opening_conditions = _dimension_conditions_with_text(db, user, filters, opening=True)
        opened_counts = _counts(opened_day, opening_conditions, OperationOrder.opened_at)

    if metric in ("fechadas", "saldo"):
        closed_conditions = _dimension_conditions_with_text(db, user, filters)
        closed_counts = _counts(closed_day, closed_conditions, OperationOrder.closed_at)

    buckets: dict[tuple[date, str | None], int] = defaultdict(int)
    if metric == "abertas":
        for (day, group), count in opened_counts.items():
            buckets[(operations_queries._period_group_start(day, granularity), group)] += count
    elif metric == "fechadas":
        for (day, group), count in closed_counts.items():
            buckets[(operations_queries._period_group_start(day, granularity), group)] += count
    else:
        for key in set(opened_counts) | set(closed_counts):
            day, group = key
            bucket = (operations_queries._period_group_start(day, granularity), group)
            buckets[bucket] += opened_counts.get(key, 0) - closed_counts.get(key, 0)

    results = []
    for (period_start, group), quantity in sorted(buckets.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        item = {"period_start": period_start, "quantity": quantity}
        if label is not None:
            item["group"] = group
        results.append(item)
    return results


def _team_target_versions_for_names(db: Session, team_model_names: set[str]) -> list[OperationTeamTargetVersion]:
    if not team_model_names:
        return []
    return list(
        db.scalars(
            select(OperationTeamTargetVersion).where(OperationTeamTargetVersion.team_model_name.in_(team_model_names))
        )
    )


def _resolve_team_target(
    versions: list[OperationTeamTargetVersion], team_model: str | None, period_type: str, reference_at: datetime
) -> OperationTeamTargetVersion | None:
    if not team_model:
        return None
    for version in versions:
        if (
            version.team_model_name == team_model
            and version.period_type == period_type
            and version.valid_from <= reference_at
            and (version.valid_to is None or version.valid_to > reference_at)
        ):
            return version
    return None


def _hours_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return round((end - start).total_seconds() / 3600, 1)


def _sla_stage_flags_for_order(order: OperationOrder, reference_at: datetime) -> tuple[bool | None, bool | None]:
    """Versão em Python de `_scheduled_after_sla_expr`/`_sla_expired_before_schedule_expr` (mesma
    regra, calculada por linha já carregada em memória em vez de em SQL) - usada aqui porque
    `search_orders` já itera `OperationOrder` como objeto ORM, então recalcular em SQL por O.S.
    seria uma query extra à toa."""
    target = order.sla_target_hours
    if target is None:
        return None, None
    if order.scheduled_at is not None:
        scheduled_after_sla = _hours_between(order.opened_at, order.scheduled_at) > target
        return scheduled_after_sla, scheduled_after_sla
    reference = order.closed_at or reference_at
    hours_elapsed_before_schedule = _hours_between(order.opened_at, reference)
    return None, hours_elapsed_before_schedule > target


def _build_search_item(
    order: OperationOrder,
    team_model: str | None,
    team_target: OperationTeamTargetVersion | None,
    *,
    reference_point: tuple[float, float] | None = None,
) -> dict:
    target = order.sla_target_hours
    elapsed = order.elapsed_hours
    is_open = order.closed_at is None
    reference_at = datetime.now(timezone.utc)
    distance_km = (
        round(_haversine_km(order.latitude, order.longitude, *reference_point), 3)
        if reference_point is not None and order.latitude is not None and order.longitude is not None
        else None
    )

    has_target = target is not None and elapsed is not None
    horas_para_vencer = round(target - elapsed, 1) if has_target else None
    horas_atrasada = round(max(0.0, elapsed - target), 1) if has_target else None
    dias_em_aberto = round((reference_at - order.opened_at).total_seconds() / 86400, 1) if is_open else None
    sla_deadline_at = order.opened_at + timedelta(hours=target) if target is not None else None
    scheduled_after_sla, sla_expired_before_schedule = _sla_stage_flags_for_order(order, reference_at)

    return {
        "order_code": order.order_code,
        "regional": order.regional,
        "city": order.city,
        "os_type": order.os_type,
        "subject": order.os_subject,
        "diagnosis": order.diagnosis,
        "sector": order.sector,
        # "mensagem" confirmado contra amostra real (ver operations/schemas.py) - mesma chave de
        # `service_description` no filtro de texto (TEXT_FILTER_COLUMNS); faltava no retorno de
        # search_orders, que só tinha o relato de FECHAMENTO (technical_report) - sem isso dava
        # pra filtrar pelo conteúdo da descrição de abertura mas não pra realmente lê-la.
        "service_description": _text_from_payload(order.raw_payload, "mensagem"),
        # "mensagem_resposta" confirmado contra amostra real (ver operations/schemas.py) -
        # "relato_tecnico"/"relato" nunca apareceram, removidas.
        "technical_report": _text_from_payload(order.raw_payload, "mensagem_resposta"),
        # Texto livre (endereço+complemento+referência do payload bruto do IXC) - rua/número/CEP
        # continuam embutidos nessa string única (sem chave própria confirmada na fonte); bairro e
        # coordenadas, em contraste, JÁ são campos separados - ver neighborhood/latitude/longitude.
        "service_address": _service_address_from_payload(order.raw_payload),
        "neighborhood": order.neighborhood,
        "latitude": order.latitude,
        "longitude": order.longitude,
        # Distância (km) até o ponto de referência do filtro geográfico (near_latitude/
        # near_longitude) - None quando a busca não usou filtro de raio, ou quando esta O.S. não
        # tem coordenadas. Existe pra apoiar "reincidência no mesmo ponto ou pontos próximos":
        # ordenar/ler o quão perto cada resultado está do ponto buscado.
        "distance_km": distance_km,
        "pop": order.pop,
        "responsible": order.responsible,
        "team_model": team_model,
        "status": order.status,
        "opened_at": order.opened_at,
        "scheduled_at": order.scheduled_at,
        "assumed_at": order.assumed_at,
        "displacement_started_at": order.displacement_started_at,
        "execution_started_at": order.execution_started_at,
        "finished_at": order.finished_at,
        "closed_at": order.closed_at,
        "sla_status": order.sla_status,
        # Só se aplica a O.S. ainda aberta (ver _sla_risk_bucket_case em operations/queries.py) -
        # numa O.S. já fechada o "risco" não tem mais sentido preditivo, fica None.
        "sla_risk": _sla_risk_bucket(elapsed, target) if is_open else None,
        "sla_target_hours": target,
        # `deadline_at` bruto do IXC está majoritariamente vazio nesta instância (ver
        # docs/plano-integracao-ixc.md) - este é o prazo EFETIVO, calculado a partir da meta de
        # horas do assunto (o mesmo que o sistema já usa por baixo pra decidir sla_status).
        "sla_deadline_at": sla_deadline_at,
        "horas_para_vencer": horas_para_vencer,
        "horas_atrasada": horas_atrasada,
        "dias_em_aberto": dias_em_aberto,
        "sla_estourado": order.sla_status == "out_of_time",
        # Etapa em que o SLA foi de fato perdido - ver _sla_stage_flags_for_order/
        # _scheduled_after_sla_expr/_sla_expired_before_schedule_expr sobre a definição de cada um
        # e por que scheduled_after_sla fica None quando a O.S. não tem agendamento (não dá pra
        # dizer que "o agendamento venceu" sem agendamento nenhum).
        "scheduled_after_sla": scheduled_after_sla,
        "sla_expired_before_schedule": sla_expired_before_schedule,
        "hours_open_to_schedule": _hours_between(order.opened_at, order.scheduled_at),
        "hours_schedule_to_execution": _hours_between(order.scheduled_at, order.execution_started_at),
        "hours_execution_to_close": _hours_between(order.execution_started_at, order.closed_at),
        "hours_open_to_close": _hours_between(order.opened_at, order.closed_at),
        # Só existe pra O.S. fechada (a meta é sobre produção realizada) e quando o modelo de
        # equipe é conhecido - a meta VIGENTE em closed_at, não a de hoje (ver
        # operations/models.py:OperationTeamTargetVersion sobre a limitação de não haver
        # retroatividade anterior a quando esse histórico entrou em produção).
        "team_target_quantity": team_target.target_quantity if team_target else None,
        "team_target_period": team_target.period_type if team_target else None,
        "team_target_valid_from": team_target.valid_from if team_target else None,
        "team_target_valid_to": team_target.valid_to if team_target else None,
    }


def search_orders(
    db: Session,
    user: User,
    *,
    date_from: date,
    date_to: date,
    page: int = 1,
    page_size: int = 50,
    keyword: str | None = None,
    **filters,
) -> dict:
    """Busca paginada de O.S. com diagnóstico/relato técnico, para leitura qualitativa. Período
    obrigatório + paginação real (mesmo padrão de `operations_queries.order_page`) para nunca
    devolver um volume de texto capaz de lotar o contexto da IA de uma vez só."""
    page_size = min(page_size, AI_SEARCH_MAX_PAGE_SIZE)
    if keyword:
        filters = {**filters, "search": keyword}

    conditions, _, _ = operations_queries._query_conditions(db, date_from, date_to, user, filters)
    conditions.extend(_text_filter_conditions(filters.get("text_filters")))
    conditions.extend(_sla_stage_filter_conditions(db, filters))
    conditions.extend(_geo_filter_conditions(filters))
    total = int(db.scalar(select(func.count(OperationOrder.id)).where(*conditions)) or 0)
    offset = (page - 1) * page_size

    near_latitude = filters.get("near_latitude")
    near_longitude = filters.get("near_longitude")
    reference_point = (near_latitude, near_longitude) if near_latitude is not None and near_longitude is not None else None
    # Com um ponto de referência, o mais útil é ver primeiro quem está mais perto (apoia
    # "reincidência no mesmo ponto ou pontos próximos") - sem ele, mantém a ordem de sempre
    # (mais recente primeiro).
    if reference_point is not None:
        order_clauses = (
            _haversine_km_expr(OperationOrder.latitude, OperationOrder.longitude, *reference_point).asc(),
            OperationOrder.id.desc(),
        )
    else:
        order_clauses = (OperationOrder.opened_at.desc(), OperationOrder.id.desc())

    orders = list(
        db.scalars(
            select(OperationOrder)
            .where(*conditions)
            .order_by(*order_clauses)
            .offset(offset)
            .limit(page_size)
        )
    )
    team_model_by_responsible = _team_model_lookup(db, orders)
    target_versions = _team_target_versions_for_names(db, set(team_model_by_responsible.values()))
    items = []
    for order in orders:
        team_model = team_model_by_responsible.get((order.responsible or "").lower())
        team_target = None
        if team_model and order.closed_at is not None:
            # Mesma conversão pra fuso local de work_schedule_overview (services.py:85) antes de
            # classificar o dia da semana - sem isso, uma O.S. fechada perto da meia-noite UTC
            # pode cair no dia errado (America/Porto_Velho é UTC-4).
            local_closed = order.closed_at.astimezone(operations_queries.OPERATIONS_TIMEZONE)
            period_type = operations_queries.period_type_for_date(local_closed.date())
            team_target = _resolve_team_target(target_versions, team_model, period_type, order.closed_at)
        items.append(_build_search_item(order, team_model, team_target, reference_point=reference_point))
    return {
        "items": items,
        "total_encontrado": total,
        "page": page,
        "page_size": page_size,
        "has_more": total > page * page_size,
    }


def backlog_aging(db: Session, user: User, *, group_by: str, date_to: date, **filters) -> list[dict]:
    """Idade do backlog (O.S. ainda abertas em `date_to`), por dimensão: quantidade, idade média
    e mediana em dias, a O.S. mais antiga, e quantas passam de 1/3/5/7/15 dias. Calculado em
    Python (não em SQL) porque o volume é do tamanho do backlog atual - milhares, não a base toda
    - e mediana não é portável entre Postgres/SQLite sem depender de extensão específica."""
    label = _group_label(db, group_by)
    conditions = _dimension_conditions_with_text(db, user, filters)
    _, reference_at = local_period_utc_bounds(date_to, date_to)
    rows = db.execute(
        select(label, OperationOrder.order_code, OperationOrder.opened_at).where(
            *conditions,
            OperationOrder.is_closed.is_(False),
            OperationOrder.opened_at <= reference_at,
        )
    ).all()

    by_group: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for label_value, order_code, opened_at in rows:
        age_days = (reference_at - opened_at).total_seconds() / 86400
        by_group[str(label_value)].append((order_code, age_days))

    results = []
    for label_value, entries in by_group.items():
        ages = [age for _, age in entries]
        oldest_code, oldest_age = max(entries, key=lambda entry: entry[1])
        results.append(
            {
                "label": label_value,
                "quantity": len(entries),
                "avg_age_days": round(sum(ages) / len(ages), 1),
                "median_age_days": round(statistics.median(ages), 1),
                "oldest_order_code": oldest_code,
                "oldest_age_days": round(oldest_age, 1),
                "over_1d": sum(1 for age in ages if age > 1),
                "over_3d": sum(1 for age in ages if age > 3),
                "over_5d": sum(1 for age in ages if age > 5),
                "over_7d": sum(1 for age in ages if age > 7),
                "over_15d": sum(1 for age in ages if age > 15),
            }
        )
    results.sort(key=lambda item: -item["quantity"])
    return results


def filter_options_for_ai(db: Session, user: User, date_from: date, date_to: date) -> OperationFilters:
    """Repassa direto pra `operations_queries.filter_options` - a mesma função que alimenta os
    dropdowns da tela de Operação (já cobre regionais, modelos de equipe, setores, assuntos,
    diagnósticos, responsáveis, status, status de SLA, prioridades etc.). Nenhuma lógica nova:
    resolve o problema de a IA não conseguir listar valores cadastrados sem reimplementar nada."""
    return operations_queries.filter_options(db, date_from, date_to, user, scope="period")


BacklogHistoryMetric = Literal["backlog", "backlog_atrasado"]
BacklogHistoryGroupBy = Literal["none", "regional", "team_model", "sector", "city"]


def backlog_history(
    db: Session,
    user: User,
    *,
    metric: BacklogHistoryMetric,
    date_from: date,
    date_to: date,
    group_by: BacklogHistoryGroupBy = "none",
    sector_filter: dict | None = None,
) -> list[dict]:
    """Série histórica de backlog/backlog atrasado, lida do snapshot diário (ver
    `operations/backlog_snapshot.py`). Limitações que a IA precisa saber (documentadas na
    descrição da ferramenta, ver schemas.py): (1) só tem dado a partir do dia em que o job de
    captura entrou em produção, sem retroatividade nenhuma; (2) só quebra/filtra por "regional",
    "team_model", "sector" ou "city" - o snapshot já vem pré-agregado por essas quatro dimensões,
    não por qualquer uma como as outras ferramentas. `city` foi adicionada depois das outras três -
    snapshots capturados antes dessa mudança ficam com "Não identificado" nessa dimensão.

    `sector_filter` é `{"operator": "contains"|"starts_with"|"ends_with"|"not_equals", "value":
    str}` - reaproveita `_text_filter_conditions` (mesma sintaxe/escape das outras ferramentas),
    fixando o campo em "sector"."""
    # Snapshot não passa por `_dimension_conditions` (não é uma O.S. individual) - o escopo
    # regional do usuário precisa ser aplicado aqui manualmente, mesma regra de sempre.
    allowed_regionals = effective_managed_regionals(user.managed_regional, user.managed_regionals)
    conditions = [OperationBacklogSnapshot.snapshot_date.between(date_from, date_to)]
    if allowed_regionals:
        conditions.append(OperationBacklogSnapshot.regional.in_(allowed_regionals))
    elif user.role == "regional_manager_viewer":
        conditions.append(OperationBacklogSnapshot.id == -1)
    if sector_filter:
        condition = _text_operator_condition(OperationBacklogSnapshot.sector, sector_filter["operator"], sector_filter["value"])
        if condition is not None:
            conditions.append(condition)

    count_column = (
        OperationBacklogSnapshot.backlog_atrasado_count
        if metric == "backlog_atrasado"
        else OperationBacklogSnapshot.backlog_count
    )
    group_column = {
        "regional": OperationBacklogSnapshot.regional,
        "team_model": OperationBacklogSnapshot.team_model,
        "sector": OperationBacklogSnapshot.sector,
        "city": OperationBacklogSnapshot.city,
    }.get(group_by)

    columns = (OperationBacklogSnapshot.snapshot_date, group_column) if group_column is not None else (OperationBacklogSnapshot.snapshot_date,)
    rows = db.execute(select(*columns, func.sum(count_column)).where(*conditions).group_by(*columns)).all()

    results = []
    for row in rows:
        item = {"snapshot_date": row[0], "quantity": int(row[-1] or 0)}
        if group_column is not None:
            item["group"] = row[1]
        results.append(item)
    results.sort(key=lambda item: (item["snapshot_date"], item.get("group") or ""))
    return results


def warranty_analytics_for_ai(
    db: Session,
    user: User,
    *,
    date_from: date,
    date_to: date,
    period_basis: str = "opened",
    denominator: str = "active_origins",
    origin_excluded_diagnoses: list[str] | None = None,
    **filters,
) -> dict:
    """Reaproveita `operations_queries.warranty_analytics` - a mesma função que alimenta a aba
    Garantias da tela - sem nenhuma lógica nova. Só troca os itens individuais: a versão da tela
    embute o objeto completo de 2 O.S. (origem e retorno) por item, pro drill clicável; aqui isso
    seria pesado demais pra IA (mesmo motivo de `search_orders` ser paginado) - fica só os campos
    planos de cada garantia encontrada."""
    result = operations_queries.warranty_analytics(
        db,
        date_from,
        date_to,
        user,
        period_basis=period_basis,
        denominator=denominator,
        origin_excluded_diagnoses=origin_excluded_diagnoses,
        **filters,
    )
    result["items"] = [
        {key: value for key, value in item.items() if key not in ("origin_order", "return_order")}
        for item in result["items"]
    ]
    return result


def team_targets_for_ai(db: Session, reference_date: date) -> list[dict]:
    """Metas de equipe vigentes numa data - repassa `operations_queries.team_targets_snapshot`
    (histórico append-only, ver operations/models.py:OperationTeamTargetVersion)."""
    versions = operations_queries.team_targets_snapshot(db, reference_date)
    return [
        {
            "team_model": version.team_model_name,
            "period_type": version.period_type,
            "target_quantity": version.target_quantity,
            "median_from_quantity": version.median_from_quantity,
            "good_from_quantity": version.good_from_quantity,
            "valid_from": version.valid_from,
            "valid_to": version.valid_to,
        }
        for version in versions
    ]


TeamTargetGranularity = Literal["day", "week", "month"]


def _team_target_for_bucket(
    db: Session, team_model: str, bucket_start: date, granularity: TeamTargetGranularity, date_from: date, date_to: date
) -> int | None:
    if granularity == "month":
        # A meta "monthly" é um valor configurado independente, não a soma dos alvos diários do
        # mês (pode existir pra compensar feriados/férias etc.) - usar direto, sem somar dias.
        version = operations_queries.team_target_for_date(db, team_model, "monthly", bucket_start)
        return version.target_quantity if version else None

    days_in_bucket = [bucket_start + timedelta(days=offset) for offset in range(7)] if granularity == "week" else [bucket_start]
    total = 0
    any_found = False
    for day in days_in_bucket:
        if day < date_from or day > date_to:
            continue
        period_type = operations_queries.period_type_for_date(day)
        version = operations_queries.team_target_for_date(db, team_model, period_type, day)
        if version:
            total += version.target_quantity
            any_found = True
    return total if any_found else None


def team_target_performance(
    db: Session,
    user: User,
    *,
    date_from: date,
    date_to: date,
    granularity: TeamTargetGranularity = "day",
    **filters,
) -> list[dict]:
    """Produção realizada (fechadas) x meta prevista, por bucket e por modelo de equipe - a meta
    usada é a que era VIGENTE naquele bucket (ver `_team_target_for_bucket`), não a de hoje.
    Reaproveita `orders_timeseries` (metric="fechadas", group_by="team_model") pro lado realizado
    - só cobre os modelos de equipe que aparecem com produção real no período, não todo modelo
    cadastrado (evita gerar linha zerada pra modelo sem nenhuma atividade)."""
    actual_points = orders_timeseries(
        db, user, metric="fechadas", granularity=granularity, date_from=date_from, date_to=date_to,
        group_by="team_model", **filters,
    )
    results = []
    for point in actual_points:
        team_model = point.get("group")
        if not team_model:
            continue
        target = _team_target_for_bucket(db, team_model, point["period_start"], granularity, date_from, date_to)
        actual = point["quantity"]
        results.append(
            {
                "period_start": point["period_start"],
                "team_model": team_model,
                "actual": actual,
                "target": target,
                "delta": actual - target if target is not None else None,
                "percentage_of_target": round(actual / target * 100, 1) if target else None,
            }
        )
    return results
