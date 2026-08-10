from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.modules.ai.auth import require_api_key_user, require_ai_permission
from app.modules.ai.queries import aggregate_orders, orders_timeseries, search_orders
from app.modules.ai.schemas import (
    AiAggregationRequest,
    AiBreakdownItem,
    AiSearchRequest,
    AiSearchResponse,
    AiTimeseriesPoint,
    AiTimeseriesRequest,
)

router = APIRouter(prefix="/ai", tags=["ai-tools"], dependencies=[Depends(require_ai_permission("ai:query"))])

# Schema fica num router SEM a dependency de chave de API acima - é metadado (o "manual de
# instruções" que o ChatGPT Actions importa), não dado da operação, então não faz sentido exigir a
# mesma chave que protege os dados pra simplesmente descrever o formato das rotas.
public_router = APIRouter(prefix="/ai", tags=["ai-tools-meta"])


@router.post("/aggregate-orders", response_model=list[AiBreakdownItem])
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


@public_router.get("/openapi.json", include_in_schema=False)
def ai_openapi_schema(request: Request) -> dict:
    """Schema OpenAPI filtrado só com as rotas da tag `ai-tools` - pra importar no ChatGPT
    Actions sem nunca vazar rotas administrativas/de login, mesmo que o resto do sistema cresça.

    Filtra o schema JÁ GERADO (`request.app.openapi()`) em vez de pré-filtrar `request.app.routes`
    por tag: nesta versão do FastAPI, `app.routes` guarda um wrapper interno (`_IncludedRouter`)
    sem `.tags` acessível diretamente - só o schema final tem essa informação resolvida."""
    full_schema = request.app.openapi()
    ai_paths = {
        path: operations
        for path, operations in full_schema.get("paths", {}).items()
        if any(
            "ai-tools" in (operation.get("tags") or [])
            for operation in operations.values()
            if isinstance(operation, dict)
        )
    }
    return {
        **full_schema,
        "info": {
            **full_schema.get("info", {}),
            "title": "Operação Analítica — Ferramentas de IA",
            "description": "Agregação, série temporal e busca de Ordens de Serviço para consulta por IA.",
        },
        "paths": ai_paths,
    }
