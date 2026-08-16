from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.modules.ai.auth import ApiKeyContext, enforce_token_scope, require_api_key_context, require_api_key_user, require_ai_permission
from app.modules.ai.queries import (
    AI_SEARCH_GOVERNED_FIELDS,
    AI_SEARCH_ITEM_FIELDS,
    AI_SEARCH_SUMMARY_FIELDS,
    aggregate_orders,
    backlog_aging,
    backlog_history,
    filter_options_for_ai,
    orders_timeseries,
    search_orders,
    team_target_performance,
    team_targets_for_ai,
    warranty_analytics_for_ai,
)
from app.modules.ai_governance.audit import record_ai_access
from app.modules.ai_governance.field_registry import ENTITY_OPERATION_ORDERS
from app.modules.ai_governance.gate import (
    enforce_ai_endpoint_for_user,
    enforce_date_field,
    enforce_requested_fields,
)
from app.modules.ai_governance.policy import EffectivePolicy
from app.modules.operations.coordinate_quality import coordinate_quality_audit
from app.modules.operations.login_aggregate import login_aggregate, login_incident_analysis, login_outages, login_timeseries
from app.modules.operations.login_geo_clusters import find_offline_login_clusters, query_login_status
from app.modules.operations.login_search import get_login_detail, search_logins
from app.modules.operations.onu_signal_snapshot import query_onu_signal_status
from app.modules.operations.queries import DATE_FIELD_COLUMNS, orders_by_identifiers
from app.modules.ai.schemas import (
    AiAggregationRequest,
    AiBacklogAgingItem,
    AiBacklogAgingRequest,
    AiBacklogHistoryPoint,
    AiBacklogHistoryRequest,
    AiFieldCatalogItem,
    AiFilterOptionsRequest,
    AiLoginAggregateRequest,
    AiLoginDetailRequest,
    AiCoordinateQualityRequest,
    AiLoginIncidentAnalysisRequest,
    AiLoginOutagesRequest,
    AiLoginStatusRequest,
    AiLoginTimeseriesRequest,
    AiSearchLoginsRequest,
    AiOfflineLoginClustersRequest,
    AiOnuSignalRequest,
    AiOrderDetailsRequest,
    AiOrderDetailsResponse,
    AiSearchRequest,
    AiTeamTargetItem,
    AiTeamTargetPerformanceItem,
    AiTeamTargetPerformanceRequest,
    AiTeamTargetsRequest,
    AiTimeseriesPoint,
    AiTimeseriesRequest,
    AiWarrantyAnalyticsRequest,
    AiWarrantyAnalyticsResponse,
)
from app.modules.operations.schemas import (
    OperationFilters,
    OperationLoginStatusOut,
    OperationLoginSearchResultOut,
    OperationLoginDetailOut,
    OperationLoginAggregateItemOut,
    OperationLoginAggregateResponseOut,
    OperationLoginOutageItemOut,
    OperationLoginOutagesResponseOut,
    OperationLoginTimeseriesPointOut,
    OperationLoginTimeseriesResponseOut,
    OperationLoginIncidentAnalysisOut,
    OperationCoordinateQualityItemOut,
    OperationCoordinateQualityResponseOut,
    OperationOfflineLoginClustersOut,
    OperationOnuSignalOut,
    OperationOrderDetailOut,
)

router = APIRouter(prefix="/ai", tags=["ai-tools"], dependencies=[Depends(require_ai_permission("ai:query"))])

# Schema fica num router SEM a dependency de chave de API acima - é metadado (o "manual de
# instruções" que o ChatGPT Actions importa), não dado da operação, então não faz sentido exigir a
# mesma chave que protege os dados pra simplesmente descrever o formato das rotas.
public_router = APIRouter(prefix="/ai", tags=["ai-tools-meta"])


@router.post("/aggregate-orders")
def aggregate_orders_route(
    payload: AiAggregationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_api_key_user),
) -> list[dict]:
    return aggregate_orders(
        db,
        user,
        group_by=payload.group_by,
        metric=payload.metric,
        date_from=payload.date_from,
        date_to=payload.date_to,
        **payload.filters.model_dump(),
    )


@router.post("/orders-timeseries", response_model=list[AiTimeseriesPoint])
def orders_timeseries_route(
    payload: AiTimeseriesRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_api_key_user),
) -> list[dict]:
    return orders_timeseries(
        db,
        user,
        metric=payload.metric,
        granularity=payload.granularity,
        date_from=payload.date_from,
        date_to=payload.date_to,
        group_by=payload.group_by,
        **payload.filters.model_dump(),
    )


def validate_ai_search_fields(policy: EffectivePolicy, fields: list[str] | None) -> list[str] | None:
    """Fonte única de validação de `fields` para `opr_search_orders` - usada pela rota REST abaixo
    E por `mcp_connector/server.py` (o servidor MCP remoto chama `search_orders()` direto, sem
    passar por esta rota, então precisa chamar isto explicitamente para não divergir - item 16 do
    pedido: "não manter regras divergentes entre API e MCP")."""
    if fields is None:
        return None
    unknown = sorted(set(fields) - AI_SEARCH_ITEM_FIELDS)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Campo(s) desconhecidos em 'fields': {', '.join(unknown)}.")
    governed_entity_names = [AI_SEARCH_GOVERNED_FIELDS[name] for name in fields if name in AI_SEARCH_GOVERNED_FIELDS]
    enforce_requested_fields(policy, ENTITY_OPERATION_ORDERS, governed_entity_names, "selectable")
    return fields


def resolve_ai_search_output_fields(policy: EffectivePolicy, response_mode: str, fields: list[str] | None) -> list[str] | None:
    if fields is not None:
        return fields
    if response_mode != "summary":
        return None
    allowed_entity_fields = set(policy.selectable_fields(ENTITY_OPERATION_ORDERS))
    return [
        name
        for name in AI_SEARCH_SUMMARY_FIELDS
        if AI_SEARCH_GOVERNED_FIELDS.get(name, name) in allowed_entity_fields
    ]


@router.post("/search-orders", response_model=None)
def search_orders_route(
    payload: AiSearchRequest,
    db: Session = Depends(get_db),
    context: ApiKeyContext = Depends(require_api_key_context),
) -> dict:
    started_at = perf_counter()
    user = context.user
    enforce_token_scope(context, "orders.read")
    policy = enforce_ai_endpoint_for_user(db, user, "ai.search_orders", "api")
    date_field = enforce_date_field(policy, ENTITY_OPERATION_ORDERS, payload.date_field, DATE_FIELD_COLUMNS)
    fields = validate_ai_search_fields(policy, payload.fields)
    output_fields = resolve_ai_search_output_fields(policy, payload.response_mode, fields)
    result = search_orders(
        db,
        user,
        date_from=payload.date_from,
        date_to=payload.date_to,
        page=payload.page,
        page_size=payload.page_size,
        keyword=payload.keyword,
        date_field=date_field,
        fields=output_fields,
        **payload.filters.model_dump(),
    )
    record_ai_access(
        db,
        origin="api",
        endpoint_key="ai.search_orders",
        user=user,
        token_id=context.token_id,
        filters={**payload.filters.model_dump(), "keyword": payload.keyword, "date_field": date_field},
        fields_requested=fields,
        response_mode=payload.response_mode,
        result_count=result["total_encontrado"],
        duration_ms=round((perf_counter() - started_at) * 1000),
    )
    return result


# Mesma lista de `operations/router.py:ORDER_SUMMARY_FIELDS`, mas com os nomes de coluna de
# `OperationOrderDetailOut` (ex.: "os_subject", não "subject") - duplicada aqui de propósito em vez
# de importada do router de `operations` pra não criar uma dependência cruzada entre routers só por
# causa de uma lista curta de nomes.
AI_ORDER_DETAIL_SUMMARY_FIELDS = [
    "order_code", "regional", "city", "os_type", "os_subject", "sector", "status",
    "sla_status", "opened_at", "closed_at", "responsible", "priority",
]


def resolve_ai_order_details_output_fields(policy: EffectivePolicy, response_mode: str, fields: list[str] | None) -> list[str] | None:
    if fields is not None:
        return fields
    if response_mode != "summary":
        return None
    allowed = set(policy.selectable_fields(ENTITY_OPERATION_ORDERS))
    return [name for name in AI_ORDER_DETAIL_SUMMARY_FIELDS if name in allowed]


@router.post("/orders/details", response_model=AiOrderDetailsResponse)
def order_details_route(
    payload: AiOrderDetailsRequest,
    db: Session = Depends(get_db),
    context: ApiKeyContext = Depends(require_api_key_context),
) -> dict:
    """Detalhe de uma ou várias O.S. por `order_code` e/ou `source_order_id` (OS_ID) - item 5 do
    pedido. Diferente de `/search-orders`, não exige período: quem já sabe qual O.S. quer não
    deveria também ter que acertar a janela de datas em que ela foi aberta/fechada."""
    started_at = perf_counter()
    user = context.user
    enforce_token_scope(context, "orders.detail")
    policy = enforce_ai_endpoint_for_user(db, user, "ai.order_details", "api")
    # "detail_available" (não "selectable") - mesmo racional do detalhe individual em
    # `operations/router.py:order_detail`, autoriza também campos que só existem no detalhe.
    fields = enforce_requested_fields(policy, ENTITY_OPERATION_ORDERS, payload.fields, "detail_available")
    output_fields = resolve_ai_order_details_output_fields(policy, payload.response_mode, fields)

    orders = orders_by_identifiers(
        db, user, order_codes=payload.order_codes, source_order_ids=payload.source_order_ids
    )
    found_order_codes: set[str] = set()
    found_source_order_ids: set[str] = set()
    items = []
    for order in orders:
        found_order_codes.add(order.order_code)
        found_source_order_ids.add(order.source_order_id)
        detail = OperationOrderDetailOut.model_validate(order).model_dump()
        if output_fields is not None:
            detail = {key: value for key, value in detail.items() if key in output_fields}
        items.append(detail)

    record_ai_access(
        db,
        origin="api",
        endpoint_key="ai.order_details",
        user=user,
        token_id=context.token_id,
        filters={"order_codes": payload.order_codes, "source_order_ids": payload.source_order_ids},
        fields_requested=fields,
        response_mode=payload.response_mode,
        result_count=len(items),
        duration_ms=round((perf_counter() - started_at) * 1000),
    )
    return {
        "items": items,
        "not_found_order_codes": sorted(set(payload.order_codes) - found_order_codes),
        "not_found_source_order_ids": sorted(set(payload.source_order_ids) - found_source_order_ids),
    }


@router.post("/infra/offline-login-clusters", response_model=OperationOfflineLoginClustersOut)
def offline_login_clusters_route(
    payload: AiOfflineLoginClustersRequest,
    db: Session = Depends(get_db),
    context: ApiKeyContext = Depends(require_api_key_context),
) -> dict:
    """Agrupa logins que caíram nos últimos `window_minutes` e estão geograficamente próximos -
    candidato a rompimento de fibra num trecho (distinto de uma queda isolada). Só considera
    proximidade e tempo de desconexão, não regional/setor/assunto de O.S."""
    started_at = perf_counter()
    enforce_token_scope(context, "infra.read")
    enforce_ai_endpoint_for_user(db, context.user, "ai.offline_login_clusters", "api")
    clusters = find_offline_login_clusters(
        db,
        radius_meters=payload.radius_meters,
        min_cluster_size=payload.min_cluster_size,
        window_minutes=payload.window_minutes,
    )
    result = {
        "radius_meters": payload.radius_meters,
        "min_cluster_size": payload.min_cluster_size,
        "window_minutes": payload.window_minutes,
        "clusters": [
            {
                "center_latitude": cluster.center_latitude,
                "center_longitude": cluster.center_longitude,
                "radius_meters": cluster.radius_meters,
                "size": cluster.size,
                "logins": [
                    {
                        "login_id": point.login_id,
                        "login": point.login,
                        "online": point.online,
                        "latitude": point.latitude,
                        "longitude": point.longitude,
                        "last_disconnected_at": point.last_disconnected_at,
                    }
                    for point in cluster.logins
                ],
            }
            for cluster in clusters
        ],
    }
    record_ai_access(
        db,
        origin="api",
        endpoint_key="ai.offline_login_clusters",
        user=context.user,
        token_id=context.token_id,
        filters={"radius_meters": payload.radius_meters, "min_cluster_size": payload.min_cluster_size, "window_minutes": payload.window_minutes},
        result_count=len(clusters),
        duration_ms=round((perf_counter() - started_at) * 1000),
    )
    return result


@router.post("/infra/login-status", response_model=list[OperationLoginStatusOut])
def login_status_route(
    payload: AiLoginStatusRequest,
    db: Session = Depends(get_db),
    context: ApiKeyContext = Depends(require_api_key_context),
) -> list:
    """Status ATUAL de conectividade por login - não é um evento de queda, é o estado agora e há
    quanto tempo está nesse estado (`status_changed_at` só avança quando `online` muda). Consulta
    individual (login específico ou busca geográfica), não cluster de queda em massa."""
    started_at = perf_counter()
    enforce_token_scope(context, "infra.read")
    enforce_ai_endpoint_for_user(db, context.user, "ai.login_status", "api")
    results = query_login_status(
        db,
        logins=payload.logins,
        online_statuses=payload.online_statuses,
        regionals=payload.regionals,
        near_latitude=payload.near_latitude,
        near_longitude=payload.near_longitude,
        radius_km=payload.radius_km,
        limit=payload.limit,
    )
    record_ai_access(
        db,
        origin="api",
        endpoint_key="ai.login_status",
        user=context.user,
        token_id=context.token_id,
        filters={"logins": payload.logins, "online_statuses": payload.online_statuses, "regionals": payload.regionals, "near_latitude": payload.near_latitude},
        result_count=len(results),
        duration_ms=round((perf_counter() - started_at) * 1000),
    )
    return results


@router.post("/infra/search-logins", response_model=OperationLoginSearchResultOut)
def search_logins_route(
    payload: AiSearchLoginsRequest,
    db: Session = Depends(get_db),
    context: ApiKeyContext = Depends(require_api_key_context),
) -> dict:
    """Busca paginada de login (item novo, pedido do usuário em 2026-08-15) - equivalente de
    `search_orders` para logins: paginação real (total_encontrado/page/has_more), filtros de
    PON/transmissor/contrato (join com telemetria ONU) e datetime completo (gte/gt/lte/lt/eq)."""
    started_at = perf_counter()
    enforce_token_scope(context, "infra.read")
    enforce_ai_endpoint_for_user(db, context.user, "ai.search_logins", "api")
    result = search_logins(
        db,
        logins=payload.logins,
        login_query=payload.login_query,
        login_ids=payload.login_ids,
        online_statuses=payload.online_statuses,
        regionals=payload.regionals,
        pon_ids=payload.pon_ids,
        transmitter_ids=payload.transmitter_ids,
        contract_ids=payload.contract_ids,
        near_latitude=payload.near_latitude,
        near_longitude=payload.near_longitude,
        radius_km=payload.radius_km,
        status_changed_at=payload.status_changed_at.model_dump() if payload.status_changed_at else None,
        last_connected_at=payload.last_connected_at.model_dump() if payload.last_connected_at else None,
        last_disconnected_at=payload.last_disconnected_at.model_dump() if payload.last_disconnected_at else None,
        captured_at=payload.captured_at.model_dump() if payload.captured_at else None,
        page=payload.page,
        page_size=payload.page_size,
    )
    record_ai_access(
        db,
        origin="api",
        endpoint_key="ai.search_logins",
        user=context.user,
        token_id=context.token_id,
        filters={"logins": payload.logins, "login_query": payload.login_query, "regionals": payload.regionals},
        result_count=result["total_encontrado"],
        duration_ms=round((perf_counter() - started_at) * 1000),
    )
    return result


@router.post("/infra/login-detail", response_model=OperationLoginDetailOut)
def login_detail_route(
    payload: AiLoginDetailRequest,
    db: Session = Depends(get_db),
    context: ApiKeyContext = Depends(require_api_key_context),
) -> dict:
    """Detalhamento completo de um login (item novo, pedido do usuário em 2026-08-15) -
    identificação, status de conexão com tempo já calculado no estado atual, telemetria ONU/PON e
    histórico recente de eventos de conexão/desconexão (reconstruído do histórico append-only)."""
    started_at = perf_counter()
    enforce_token_scope(context, "infra.read")
    enforce_ai_endpoint_for_user(db, context.user, "ai.login_detail", "api")
    detail = get_login_detail(db, login=payload.login, login_id=payload.login_id, history_hours=payload.history_hours)
    if detail is None:
        raise HTTPException(status_code=404, detail="Login não encontrado.")
    record_ai_access(
        db,
        origin="api",
        endpoint_key="ai.login_detail",
        user=context.user,
        token_id=context.token_id,
        filters={"login": payload.login, "login_id": payload.login_id},
        result_count=1,
        duration_ms=round((perf_counter() - started_at) * 1000),
    )
    return detail


@router.post("/infra/login-aggregate", response_model=OperationLoginAggregateResponseOut)
def login_aggregate_route(
    payload: AiLoginAggregateRequest,
    db: Session = Depends(get_db),
    context: ApiKeyContext = Depends(require_api_key_context),
) -> dict:
    """Contagem de logins por dimensão (item novo, pedido do usuário em 2026-08-15) - para
    detecção de incidente coletivo sem baixar registro por registro."""
    started_at = perf_counter()
    enforce_token_scope(context, "infra.read")
    enforce_ai_endpoint_for_user(db, context.user, "ai.login_aggregate", "api")
    try:
        result = login_aggregate(db, group_by=payload.group_by, regionals=payload.regionals, online_statuses=payload.online_statuses)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_ai_access(
        db, origin="api", endpoint_key="ai.login_aggregate", user=context.user, token_id=context.token_id,
        filters={"group_by": payload.group_by, "regionals": payload.regionals}, result_count=len(result["data"]),
        duration_ms=round((perf_counter() - started_at) * 1000),
    )
    return result


@router.post("/infra/login-outages", response_model=OperationLoginOutagesResponseOut)
def login_outages_route(
    payload: AiLoginOutagesRequest,
    db: Session = Depends(get_db),
    context: ApiKeyContext = Depends(require_api_key_context),
) -> dict:
    """Logins offline agora que caíram dentro de [since, until] (item novo, pedido do usuário em
    2026-08-15) - candidatos a incidente coletivo quando concentrados na mesma regional/PON."""
    started_at = perf_counter()
    enforce_token_scope(context, "infra.read")
    enforce_ai_endpoint_for_user(db, context.user, "ai.login_outages", "api")
    result = login_outages(db, since=payload.since, until=payload.until, regionals=payload.regionals, limit=payload.limit)
    record_ai_access(
        db, origin="api", endpoint_key="ai.login_outages", user=context.user, token_id=context.token_id,
        filters={"since": payload.since, "regionals": payload.regionals}, result_count=len(result["data"]),
        duration_ms=round((perf_counter() - started_at) * 1000),
    )
    return result


@router.post("/infra/login-timeseries", response_model=OperationLoginTimeseriesResponseOut)
def login_timeseries_route(
    payload: AiLoginTimeseriesRequest,
    db: Session = Depends(get_db),
    context: ApiKeyContext = Depends(require_api_key_context),
) -> dict:
    """Série temporal de conectados/desconectados/quedas novas/reconexões novas (item novo, pedido
    do usuário em 2026-08-15) - um ponto por captura real do snapshot periódico."""
    started_at = perf_counter()
    enforce_token_scope(context, "infra.read")
    enforce_ai_endpoint_for_user(db, context.user, "ai.login_timeseries", "api")
    result = login_timeseries(db, since=payload.since, until=payload.until)
    record_ai_access(
        db, origin="api", endpoint_key="ai.login_timeseries", user=context.user, token_id=context.token_id,
        filters={"since": payload.since}, result_count=len(result["data"]),
        duration_ms=round((perf_counter() - started_at) * 1000),
    )
    return result


@router.post("/infra/login-incident-analysis", response_model=OperationLoginIncidentAnalysisOut)
def login_incident_analysis_route(
    payload: AiLoginIncidentAnalysisRequest,
    db: Session = Depends(get_db),
    context: ApiKeyContext = Depends(require_api_key_context),
) -> dict:
    """Funil de incidente coletivo numa única chamada (item novo, pedido do usuário em 2026-08-15)
    - quedas novas, ainda offline, reconexões, quebra por regional/transmissor/PON/causa de queda e
    clusters geográficos, já agregados no backend."""
    started_at = perf_counter()
    enforce_token_scope(context, "infra.read")
    enforce_ai_endpoint_for_user(db, context.user, "ai.login_incident_analysis", "api")
    result = login_incident_analysis(
        db, window_minutes=payload.window_minutes, regionals=payload.regionals,
        cluster_radius_meters=payload.cluster_radius_meters, cluster_min_size=payload.cluster_min_size,
    )
    record_ai_access(
        db, origin="api", endpoint_key="ai.login_incident_analysis", user=context.user, token_id=context.token_id,
        filters={"window_minutes": payload.window_minutes, "regionals": payload.regionals},
        result_count=result["still_offline"], duration_ms=round((perf_counter() - started_at) * 1000),
    )
    return result


@router.post("/infra/coordinate-quality", response_model=OperationCoordinateQualityResponseOut)
def coordinate_quality_route(
    payload: AiCoordinateQualityRequest,
    db: Session = Depends(get_db),
    context: ApiKeyContext = Depends(require_api_key_context),
) -> dict:
    """Auditoria de qualidade de latitude/longitude, quebrada por regional (item novo, Fase 1 do
    plano de confiabilidade de dado, pedido do usuário em 2026-08-15) - SÓ classifica e conta,
    nenhuma correção automática. Use antes de confiar em qualquer cluster geográfico."""
    started_at = perf_counter()
    enforce_token_scope(context, "infra.read")
    enforce_ai_endpoint_for_user(db, context.user, "ai.coordinate_quality", "api")
    result = coordinate_quality_audit(
        db, entity=payload.entity, outlier_km=payload.outlier_km, duplicate_threshold=payload.duplicate_threshold
    )
    record_ai_access(
        db, origin="api", endpoint_key="ai.coordinate_quality", user=context.user, token_id=context.token_id,
        filters={"entity": payload.entity}, result_count=len(result["data"]),
        duration_ms=round((perf_counter() - started_at) * 1000),
    )
    return result


@router.post("/infra/onu-signal", response_model=list[OperationOnuSignalOut])
def onu_signal_route(
    payload: AiOnuSignalRequest,
    db: Session = Depends(get_db),
    context: ApiKeyContext = Depends(require_api_key_context),
) -> list[dict]:
    """Telemetria óptica/ONU (transmissor, sinal RX/TX em dBm, serial da ONU, causa da última
    queda - ex.: "Link Loss"). Só cobre os logins já monitorados pelo sistema, não a base inteira
    de ONUs do IXC."""
    started_at = perf_counter()
    enforce_token_scope(context, "infra.read")
    enforce_ai_endpoint_for_user(db, context.user, "ai.onu_signal", "api")
    results = query_onu_signal_status(
        db,
        login_ids=payload.login_ids,
        last_drop_causes=payload.last_drop_causes,
        transmitter_ids=payload.transmitter_ids,
        limit=payload.limit,
    )
    record_ai_access(
        db,
        origin="api",
        endpoint_key="ai.onu_signal",
        user=context.user,
        token_id=context.token_id,
        filters={"login_ids": payload.login_ids, "last_drop_causes": payload.last_drop_causes, "transmitter_ids": payload.transmitter_ids},
        result_count=len(results),
        duration_ms=round((perf_counter() - started_at) * 1000),
    )
    return results


@router.post("/backlog-aging", response_model=list[AiBacklogAgingItem])
def backlog_aging_route(
    payload: AiBacklogAgingRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_api_key_user),
) -> list[dict]:
    return backlog_aging(db, user, group_by=payload.group_by, date_to=payload.date_to, **payload.filters.model_dump())


@router.post(
    "/backlog-history",
    response_model=list[AiBacklogHistoryPoint],
    description=(
        "Série histórica de backlog/backlog atrasado. Só há dado desde a entrada em produção "
        "da captura diária (sem retroatividade). Agrupa por regional, team_model, sector ou "
        "city; use sector_filter pra restringir setor. 'city' é mais recente - snapshots "
        "antigos mostram 'Não identificado' nela."
    ),
)
def backlog_history_route(
    payload: AiBacklogHistoryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_api_key_user),
) -> list[dict]:
    return backlog_history(
        db,
        user,
        metric=payload.metric,
        date_from=payload.date_from,
        date_to=payload.date_to,
        group_by=payload.group_by,
        sector_filter=payload.sector_filter.model_dump() if payload.sector_filter else None,
    )


@router.get(
    "/fields",
    response_model=list[AiFieldCatalogItem],
    description=(
        "Catálogo dinâmico de campos e capacidades (item 10 do pedido de governança IA/MCP) - "
        "reflete a política de exposição vigente (overrides administrativos + restrição por "
        "perfil) para quem está chamando, não um estado estático do código."
    ),
)
def ai_fields_route(db: Session = Depends(get_db), user: User = Depends(require_api_key_user)) -> list[dict]:
    policy = enforce_ai_endpoint_for_user(db, user, "ai.list_fields", "api")
    return policy.field_catalog()


@router.post("/filter-options", response_model=OperationFilters)
def filter_options_route(
    payload: AiFilterOptionsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_api_key_user),
) -> dict:
    return filter_options_for_ai(db, user, payload.date_from, payload.date_to)


@router.post(
    "/warranty-analytics",
    response_model=AiWarrantyAnalyticsResponse,
    description=(
        "Garantia de ativação: uma Manutenção é garantia quando abre no mesmo contrato até 30 "
        "dias após o fechamento de uma Ativação/Mud. Endereço/Mud. Tecnologia elegível. Mesma "
        "conta da aba Garantias da tela."
    ),
)
def warranty_analytics_route(
    payload: AiWarrantyAnalyticsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_api_key_user),
) -> dict:
    return warranty_analytics_for_ai(
        db,
        user,
        date_from=payload.date_from,
        date_to=payload.date_to,
        period_basis=payload.period_basis,
        denominator=payload.denominator,
        origin_excluded_diagnoses=payload.origin_excluded_diagnoses,
        **payload.filters.model_dump(),
    )


@router.post(
    "/team-targets",
    response_model=list[AiTeamTargetItem],
    description="Metas de equipe (por modelo e tipo de período) vigentes numa data - não é a mais recente, é a que valia naquele dia.",
)
def team_targets_route(
    payload: AiTeamTargetsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_api_key_user),
) -> list[dict]:
    return team_targets_for_ai(db, payload.reference_date)


@router.post(
    "/team-target-performance",
    response_model=list[AiTeamTargetPerformanceItem],
    description=(
        "Produção realizada (fechadas) x meta prevista, por modelo de equipe. Usa a meta que "
        "era vigente em cada bucket, não a de hoje. Só cobre modelos com produção real no "
        "período (não gera linha zerada pra modelo sem nenhuma atividade)."
    ),
)
def team_target_performance_route(
    payload: AiTeamTargetPerformanceRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_api_key_user),
) -> list[dict]:
    return team_target_performance(
        db,
        user,
        date_from=payload.date_from,
        date_to=payload.date_to,
        granularity=payload.granularity,
        **payload.filters.model_dump(),
    )


@public_router.get("/openapi.json", include_in_schema=False)
def ai_openapi_schema(request: Request) -> dict:
    """Schema OpenAPI só com as rotas deste módulo (`/ai/*`, hoje bem mais que as 3 originais) -
    pra importar no ChatGPT Actions sem vazar nada do resto do sistema. O ChatGPT limita a
    `description` de cada operação a 300 caracteres - ao adicionar uma rota nova aqui, confira o
    tamanho do docstring antes de publicar (achado real 2026-08-15: 3 rotas excediam o limite e
    quebravam a importação inteira do schema, não só a rota problemática).

    Gera o schema a partir de `router.routes` (o APIRouter isolado deste módulo, ANTES de ser
    incluído no app) - não do app inteiro. Isso importa porque `get_openapi()` computa
    `components.schemas` a partir de TODAS as rotas recebidas antes de filtrar `paths`: gerar a
    partir do app inteiro e filtrar só os `paths` depois (como uma versão anterior deste código
    fazia) deixava os modelos de dados de todo o resto do sistema (gamificação, pontuação,
    penalidades...) expostos em `components`, mesmo sem nenhuma rota deles listada."""
    schema = get_openapi(
        title="Operação Analítica — Ferramentas de IA",
        version="1.0.0",
        description="Agregação, série temporal e busca de Ordens de Serviço para consulta por IA.",
        routes=router.routes,
    )
    # `router.routes` não carrega o prefixo de API global (ex.: "/api"), aplicado só quando este
    # router é incluído no app (main.py) - por isso o servidor é calculado a partir da própria
    # requisição, tirando o sufixo fixo desta rota, em vez de hardcoded.
    base_path = str(request.url.path).removesuffix("/ai/openapi.json")
    # O proxy reverso da VM termina o TLS e repassa a conexão em HTTP puro pro backend, sem
    # `--proxy-headers` configurado no Uvicorn - sem isso, request.url.scheme sempre voltaria
    # "http", mesmo quando o cliente de fato conectou por HTTPS. `X-Forwarded-Proto` é o header
    # padrão que o proxy usa pra informar o protocolo original.
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    schema["servers"] = [{"url": f"{scheme}://{host}{base_path}"}]

    # As 3 rotas são POST só por causa dos filtros compostos no corpo - nenhuma delas escreve
    # nada. Sem isso, o ChatGPT assume que todo POST é "consequente" (pode ter efeito colateral)
    # e força confirmação manual a cada chamada, sem nem oferecer a opção de "sempre permitir".
    for operations in schema.get("paths", {}).values():
        for operation in operations.values():
            if isinstance(operation, dict):
                operation["x-openai-isConsequential"] = False

    return schema
