from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.openapi.utils import get_openapi
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.modules.ai.auth import require_api_key_user, require_ai_permission
from app.modules.ai.queries import (
    aggregate_orders,
    backlog_aging,
    backlog_history,
    filter_options_for_ai,
    orders_timeseries,
    search_orders,
    warranty_analytics_for_ai,
)
from app.modules.ai.schemas import (
    AiAggregationRequest,
    AiBacklogAgingItem,
    AiBacklogAgingRequest,
    AiBacklogHistoryPoint,
    AiBacklogHistoryRequest,
    AiFilterOptionsRequest,
    AiSearchRequest,
    AiSearchResponse,
    AiTimeseriesPoint,
    AiTimeseriesRequest,
    AiWarrantyAnalyticsRequest,
    AiWarrantyAnalyticsResponse,
)
from app.modules.operations.schemas import OperationFilters

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


@router.post("/search-orders", response_model=AiSearchResponse)
def search_orders_route(
    payload: AiSearchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_api_key_user),
) -> dict:
    return search_orders(
        db,
        user,
        date_from=payload.date_from,
        date_to=payload.date_to,
        page=payload.page,
        page_size=payload.page_size,
        keyword=payload.keyword,
        **payload.filters.model_dump(),
    )


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
        "Série histórica de backlog/backlog atrasado. Só há dado a partir da entrada em produção "
        "da captura diária (sem retroatividade). Quebra/filtra só por regional, team_model ou "
        "sector; use sector_filter (ex.: contains 'Ex') para restringir por setor."
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


@public_router.get("/openapi.json", include_in_schema=False)
def ai_openapi_schema(request: Request) -> dict:
    """Schema OpenAPI só com as 3 rotas deste módulo - pra importar no ChatGPT Actions sem
    vazar nada do resto do sistema, mesmo que ele cresça.

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
