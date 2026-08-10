from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.openapi.utils import get_openapi
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
    return schema
