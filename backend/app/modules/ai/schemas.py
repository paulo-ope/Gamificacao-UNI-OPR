from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.ai.queries import AGGREGATION_DIMENSIONS

AggregationDimension = Literal[
    "regional", "city", "os_type", "subject", "diagnosis",
    "department", "sector", "priority", "responsible", "status",
]
assert set(AggregationDimension.__args__) == set(AGGREGATION_DIMENSIONS)


# Mesmos nomes de OperationFilters (operations/schemas.py) - a IA já "conhece" esse vocabulário
# porque é o mesmo usado no resto do sistema, sem inventar sinônimo novo. Só o subconjunto que já
# cobre o pedido original (localização/empresa, tipo/assunto/diagnóstico, responsável/status);
# adicionar mais um filtro depois é acréscimo de um campo aqui, não redesenho.
class AiOrderFilters(BaseModel):
    companies: list[str] = Field(default_factory=list, max_length=100)
    regionals: list[str] = Field(default_factory=list, max_length=100)
    states: list[str] = Field(default_factory=list, max_length=100)
    cities: list[str] = Field(default_factory=list, max_length=100)
    contract_types: list[str] = Field(default_factory=list, max_length=100)
    person_types: list[str] = Field(default_factory=list, max_length=100)
    os_types: list[str] = Field(default_factory=list, max_length=100)
    subjects: list[str] = Field(default_factory=list, max_length=100)
    diagnoses: list[str] = Field(default_factory=list, max_length=100)
    departments: list[str] = Field(default_factory=list, max_length=100)
    sectors: list[str] = Field(default_factory=list, max_length=100)
    priorities: list[str] = Field(default_factory=list, max_length=100)
    creators: list[str] = Field(default_factory=list, max_length=100)
    responsibles: list[str] = Field(default_factory=list, max_length=100)
    statuses: list[str] = Field(default_factory=list, max_length=100)
    sla_statuses: list[str] = Field(default_factory=list, max_length=100)
    projects: list[str] = Field(default_factory=list, max_length=100)
    pops: list[str] = Field(default_factory=list, max_length=100)

    model_config = ConfigDict(extra="forbid")


class AiAggregationRequest(BaseModel):
    date_from: date
    date_to: date
    group_by: AggregationDimension
    metric: Literal["quantidade_aberta", "quantidade_fechada", "taxa_sla", "horas_medias"]
    filters: AiOrderFilters = Field(default_factory=AiOrderFilters)

    model_config = ConfigDict(extra="forbid")


class AiBreakdownItem(BaseModel):
    label: str
    quantity: int
    metric_value: float
    percentage: float


class AiTimeseriesRequest(BaseModel):
    date_from: date
    date_to: date
    metric: Literal["abertas", "fechadas", "saldo"]
    granularity: Literal["day", "week", "month"] = "day"
    filters: AiOrderFilters = Field(default_factory=AiOrderFilters)

    model_config = ConfigDict(extra="forbid")


class AiTimeseriesPoint(BaseModel):
    period_start: date
    quantity: int


class AiSearchRequest(BaseModel):
    date_from: date
    date_to: date
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=10, le=200)
    keyword: str | None = Field(default=None, max_length=160)
    filters: AiOrderFilters = Field(default_factory=AiOrderFilters)

    model_config = ConfigDict(extra="forbid")


class AiOrderSearchItem(BaseModel):
    order_code: str
    regional: str | None
    os_type: str | None
    subject: str | None
    diagnosis: str | None
    technical_report: str | None
    status: str | None
    opened_at: datetime
    closed_at: datetime | None


class AiSearchResponse(BaseModel):
    items: list[AiOrderSearchItem]
    total_encontrado: int
    page: int
    page_size: int
    has_more: bool
