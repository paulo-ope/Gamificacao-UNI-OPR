from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.ai.queries import AGGREGATION_DIMENSIONS
from app.modules.operations.schemas import (
    OperationBreakdownItem,
    OperationFilters,
    OperationOfflineLoginClustersOut,
    OperationResponseMetaOut,
    OperationWarrantyOriginTypeItem,
    OperationWarrantyRegionalRankingItem,
)

AggregationDimension = Literal[
    "regional", "city", "neighborhood", "os_type", "subject", "diagnosis",
    "department", "sector", "priority", "responsible", "status", "sla_status",
    # "team_model", "scheduled_after_sla", "sla_expired_before_schedule" e "geo_cluster" não são
    # colunas de OperationOrder (são calculadas em ai/queries.py:_group_label - a primeira casando
    # responsável+regional contra a atribuição de modelo de equipe, as duas seguintes comparando
    # timestamps do ciclo de vida da O.S. contra a meta de SLA, e "geo_cluster" arredondando
    # latitude/longitude pra agrupar pontos praticamente coincidentes - ver GEO_CLUSTER_DECIMALS)
    # - por isso não aparecem em AGGREGATION_DIMENSIONS, só aqui na lista de valores aceitos.
    "team_model", "scheduled_after_sla", "sla_expired_before_schedule", "geo_cluster",
]
assert set(AggregationDimension.__args__) == set(AGGREGATION_DIMENSIONS) | {
    "team_model", "scheduled_after_sla", "sla_expired_before_schedule", "geo_cluster",
}


# Só campos de texto livre (não status_code ou outros campos curtos/categóricos, onde "contém"
# não faz sentido) - lista curada, não é qualquer coluna da O.S. "service_description" é a
# descrição de abertura, dentro do raw_payload bruto do IXC (ver ai/queries.py:TEXT_FILTER_COLUMNS
# - chave confirmada contra amostra real, ver operations/schemas.py). "neighborhood" (bairro) entra
# aqui, e não só em AggregationDimension, por causa da grafia inconsistente confirmada na amostra
# real (ex.: "Centro" e "CENTRO" convivem) - "contém" tolera isso melhor que igualdade exata.
TextFilterField = Literal[
    "sector", "subject", "diagnosis", "responsible", "city", "department", "service_description", "neighborhood",
]


class AiTextFilter(BaseModel):
    field: TextFilterField
    operator: Literal["contains", "starts_with", "ends_with", "not_equals"]
    value: str = Field(min_length=1, max_length=160)

    model_config = ConfigDict(extra="forbid")


class DateTimeFilterOp(BaseModel):
    """Filtro fino por horário exato num campo datetime - item pedido pelo usuário em 2026-08-15
    ("O.S. abertas nos últimos 30 minutos", "entre 17:30 e 18:00") porque `date_from`/`date_to`
    (tipo `date`, sem hora) nunca permitiu esse nível de precisão. Aceita qualquer datetime ISO8601
    com offset (`"2026-08-14T17:30:00-04:00"`) ou "Z"/UTC - o valor é convertido para UTC antes de
    comparar com a coluna (ver `_as_utc` em `operations/queries.py`), então qualquer timezone de
    entrada funciona igual. `gte`+`lte` juntos formam um "between"; cada operador sozinho também é
    válido (ex.: só `gte` = "a partir de")."""

    gte: datetime | None = None
    lte: datetime | None = None
    gt: datetime | None = None
    lt: datetime | None = None
    eq: datetime | None = None

    model_config = ConfigDict(extra="forbid")


# Mesmos nomes de OperationFilters (operations/schemas.py) - a IA já "conhece" esse vocabulário
# porque é o mesmo usado no resto do sistema, sem inventar sinônimo novo. Só o subconjunto que já
# cobre o pedido original (localização/empresa, tipo/assunto/diagnóstico, responsável/status);
# adicionar mais um filtro depois é acréscimo de um campo aqui, não redesenho.
class AiOrderFilters(BaseModel):
    team_models: list[str] = Field(default_factory=list, max_length=100)
    companies: list[str] = Field(default_factory=list, max_length=100)
    regionals: list[str] = Field(default_factory=list, max_length=100)
    states: list[str] = Field(default_factory=list, max_length=100)
    cities: list[str] = Field(default_factory=list, max_length=100)
    contract_types: list[str] = Field(default_factory=list, max_length=100)
    person_types: list[str] = Field(default_factory=list, max_length=100)
    os_types: list[str] = Field(default_factory=list, max_length=100)
    subjects: list[str] = Field(default_factory=list, max_length=100)
    # Nome canônico proposto em docs/proposta-filter-contract-v1.md (FilterContractV1, piloto
    # aggregate_orders) para o mesmo filtro de `subjects` acima - os dois convivem, `subjects`
    # continua funcionando (alias depreciado, sem prazo de remoção), só passa a gerar um aviso em
    # `meta.warnings`. Só `aggregate_orders` normaliza os dois nesta etapa (piloto único aprovado).
    os_subjects: list[str] = Field(default_factory=list, max_length=100)
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
    # Login PPPoE/fibra do cliente (radusuarios.login, mesmo valor usado em opr_login_status) -
    # pedido do usuário em 2026-08-15 pra fechar o fluxo "login caiu -> buscar O.S. do cliente":
    # o campo já existia em OperationOrder.customer_login (usado só na busca livre por keyword),
    # mas não era filtrável de forma exata até agora.
    customer_logins: list[str] = Field(default_factory=list, max_length=50)
    text_filters: list[AiTextFilter] = Field(default_factory=list, max_length=10)
    # Filtros booleanos exatos de etapa de SLA (ver ai/queries.py:_sla_stage_filter_conditions) -
    # None (padrão) significa "não filtrar por isso", igual ao resto dos filtros deste schema.
    scheduled_after_sla: bool | None = None
    sla_expired_before_schedule: bool | None = None
    # Filtros geográficos (ver ai/queries.py:_geo_filter_conditions). `radius_km` só tem efeito
    # quando `near_latitude` e `near_longitude` também vêm preenchidos - os três juntos formam uma
    # busca "O.S. num raio de X km de um ponto" (ex.: as coordenadas de uma O.S. já conhecida, pra
    # achar reincidência no mesmo local ou nas proximidades).
    has_coordinates: bool | None = None
    near_latitude: float | None = Field(default=None, ge=-90, le=90)
    near_longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float | None = Field(default=None, gt=0, le=500)
    # Filtro fino por horário exato (ver DateTimeFilterOp) - um por marco do ciclo de vida da O.S.,
    # mesmos nomes de `operations_queries.DATE_FIELD_COLUMNS`. Aditivo a `date_from`/`date_to`
    # (que continuam obrigatórios, com granularidade de dia) - permite recortar dentro do período
    # já selecionado, ex.: "O.S. abertas hoje" (date_from=date_to=hoje) + opened_at.gte/lte para os
    # últimos 30 minutos.
    opened_at: DateTimeFilterOp | None = None
    closed_at: DateTimeFilterOp | None = None
    deadline_at: DateTimeFilterOp | None = None
    scheduled_at: DateTimeFilterOp | None = None
    assumed_at: DateTimeFilterOp | None = None
    displacement_started_at: DateTimeFilterOp | None = None
    execution_started_at: DateTimeFilterOp | None = None
    finished_at: DateTimeFilterOp | None = None
    source_updated_at: DateTimeFilterOp | None = None

    model_config = ConfigDict(extra="forbid")


class AiAggregationRequest(BaseModel):
    date_from: date
    date_to: date
    # Uma dimensão só (formato original, resposta com campo `label`) ou uma lista de até 3 pra
    # agrupamento composto (resposta com uma chave por dimensão em vez de `label`) - ver
    # aggregate_orders em ai/queries.py.
    group_by: AggregationDimension | list[AggregationDimension]
    metric: Literal[
        "quantidade_aberta", "quantidade_fechada", "taxa_sla", "horas_medias",
        "quantidade_atrasada", "quantidade_backlog",
        "horas_abertura_agenda", "horas_agenda_execucao", "horas_execucao_fechamento", "horas_abertura_fechamento",
    ]
    filters: AiOrderFilters = Field(default_factory=AiOrderFilters)

    model_config = ConfigDict(extra="forbid")

    @field_validator("group_by")
    @classmethod
    def _validate_group_by_length(cls, value):
        if isinstance(value, list) and not (1 <= len(value) <= 3):
            raise ValueError("group_by deve ter entre 1 e 3 dimensões.")
        return value


class AiTimeseriesRequest(BaseModel):
    date_from: date
    date_to: date
    metric: Literal["abertas", "fechadas", "saldo"]
    granularity: Literal["day", "week", "month"] = "day"
    group_by: AggregationDimension | None = None
    filters: AiOrderFilters = Field(default_factory=AiOrderFilters)

    model_config = ConfigDict(extra="forbid")


class AiTimeseriesPoint(BaseModel):
    period_start: date
    quantity: int
    group: str | None = None


class AiTimeseriesResponse(BaseModel):
    meta: OperationResponseMetaOut
    data: list[AiTimeseriesPoint]


class AiSearchRequest(BaseModel):
    date_from: date
    date_to: date
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=10, le=200)
    keyword: str | None = Field(default=None, max_length=160)
    filters: AiOrderFilters = Field(default_factory=AiOrderFilters)
    # Item 7 do pedido de governança IA/MCP: base explícita de data, nunca opened_at por padrão
    # quando o chamador quer closed_at (ou outro marco do ciclo de vida). `None` mantém a regra de
    # sempre (abriu OU fechou no período) - ver operations.queries.DATE_FIELD_COLUMNS.
    date_field: str | None = Field(default=None)
    # Item 4: seleção de campos - rejeitado explicitamente (não omitido em silêncio) se algum nome
    # não existir ou não estiver autorizado para o perfil do chamador.
    fields: list[str] | None = Field(default=None)
    # Item 6: "summary" evita payload excessivo pra triagem; "full" (default) preserva o
    # comportamento de sempre.
    response_mode: Literal["summary", "full"] = Field(default="full")

    model_config = ConfigDict(extra="forbid")


class AiOrderSearchItem(BaseModel):
    order_code: str
    regional: str | None
    city: str | None
    os_type: str | None
    subject: str | None
    diagnosis: str | None
    sector: str | None
    # Descrição de abertura ("mensagem" no IXC, confirmada contra amostra real) - mesma chave do
    # filtro de texto "service_description" em TEXT_FILTER_COLUMNS.
    service_description: str | None
    technical_report: str | None
    # Texto livre (endereço+complemento+referência do payload bruto do IXC) - rua/número/CEP
    # continuam embutidos nessa string única, sem chave própria confirmada na fonte.
    service_address: str | None
    # Bairro e coordenadas SÃO campos separados na origem (confirmados contra amostra real) -
    # None quando a O.S. não tiver esse dado preenchido no IXC.
    neighborhood: str | None
    latitude: float | None
    longitude: float | None
    # Distância (km) até o ponto de `near_latitude`/`near_longitude` do filtro - None quando a
    # busca não usou filtro geográfico de raio, ou quando esta O.S. não tem coordenadas.
    distance_km: float | None
    pop: str | None
    responsible: str | None
    team_model: str | None
    status: str | None
    opened_at: datetime
    scheduled_at: datetime | None
    assumed_at: datetime | None
    displacement_started_at: datetime | None
    execution_started_at: datetime | None
    finished_at: datetime | None
    closed_at: datetime | None
    sla_status: str
    sla_risk: str | None
    sla_target_hours: float | None
    sla_deadline_at: datetime | None
    horas_para_vencer: float | None
    horas_atrasada: float | None
    dias_em_aberto: float | None
    sla_estourado: bool
    # Etapa em que o SLA foi perdido - ver ai/queries.py:_sla_stage_flags_for_order.
    # scheduled_after_sla é None quando a O.S. não tem agendamento (não dá pra dizer que "o
    # agendamento venceu" sem agendamento nenhum).
    scheduled_after_sla: bool | None
    sla_expired_before_schedule: bool | None
    hours_open_to_schedule: float | None
    hours_schedule_to_execution: float | None
    hours_execution_to_close: float | None
    hours_open_to_close: float | None
    team_target_quantity: int | None
    team_target_period: str | None
    team_target_valid_from: datetime | None
    team_target_valid_to: datetime | None


class AiSearchResponse(BaseModel):
    items: list[AiOrderSearchItem]
    total_encontrado: int
    page: int
    page_size: int
    has_more: bool


class AiFieldsResponse(BaseModel):
    all_fields: list[str]
    exposed_to_ai: list[str]
    not_exposed: list[str]


class AiFieldCatalogItem(BaseModel):
    """Uma linha do catálogo dinâmico de campos (item 10 do pedido) - reflete a política de
    exposição vigente para o perfil de quem chamou, não um estado estático do código."""

    entity: str
    field: str
    type: str
    description: str | None = None
    filterable: bool
    text_filterable: bool
    groupable: bool
    returnable: bool
    selectable: bool
    detail_available: bool
    sensitive: bool
    enabled_for_api: bool
    enabled_for_mcp: bool
    enabled_for_ai: bool


class AiOrderDetailsRequest(BaseModel):
    """Detalhe de uma ou várias O.S. por `order_code` e/ou `source_order_id` (OS_ID) - item 5 do
    pedido. Pelo menos uma lista precisa vir não vazia."""

    order_codes: list[str] = Field(default_factory=list, max_length=50)
    source_order_ids: list[str] = Field(default_factory=list, max_length=50)
    fields: list[str] | None = Field(default=None)
    response_mode: Literal["summary", "full"] = Field(default="full")

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _require_at_least_one_identifier(self) -> "AiOrderDetailsRequest":
        # `model_validator(mode="after")` (não `field_validator`) de propósito - um
        # `field_validator` não roda sobre valor DEFAULT no Pydantic v2 (só quando o campo é
        # passado explicitamente), então um corpo `{}` (nenhum dos dois campos enviado) passaria
        # batido e `orders_by_identifiers` devolveria uma lista vazia em silêncio, em vez do erro
        # claro que o item 5 do pedido exige.
        if not self.order_codes and not self.source_order_ids:
            raise ValueError("Informe ao menos um order_code ou source_order_id (OS_ID).")
        return self


class AiOrderDetailsResponse(BaseModel):
    items: list[dict]
    not_found_order_codes: list[str]
    not_found_source_order_ids: list[str]


class AiFilterOptionsRequest(BaseModel):
    date_from: date
    date_to: date

    model_config = ConfigDict(extra="forbid")


class AiBacklogAgingRequest(BaseModel):
    date_to: date
    group_by: AggregationDimension = "regional"
    filters: AiOrderFilters = Field(default_factory=AiOrderFilters)

    model_config = ConfigDict(extra="forbid")


class AiBacklogAgingItem(BaseModel):
    label: str
    quantity: int
    avg_age_days: float
    median_age_days: float
    oldest_order_code: str
    oldest_age_days: float
    over_1d: int
    over_3d: int
    over_5d: int
    over_7d: int
    over_15d: int


class AiBacklogAgingResponse(BaseModel):
    meta: OperationResponseMetaOut
    data: list[AiBacklogAgingItem]


class AiBacklogSectorFilter(BaseModel):
    operator: Literal["contains", "starts_with", "ends_with", "not_equals"]
    value: str = Field(min_length=1, max_length=160)

    model_config = ConfigDict(extra="forbid")


class AiBacklogHistoryRequest(BaseModel):
    date_from: date
    date_to: date
    metric: Literal["backlog", "backlog_atrasado"]
    # Diferente das outras ferramentas: só "regional"/"team_model"/"sector"/"city" (o snapshot
    # diário já vem pré-agregado só por essas quatro - ver operations/backlog_snapshot.py).
    group_by: Literal["none", "regional", "team_model", "sector", "city"] = "none"
    sector_filter: AiBacklogSectorFilter | None = None

    model_config = ConfigDict(extra="forbid")


class AiBacklogHistoryPoint(BaseModel):
    snapshot_date: date
    quantity: int
    group: str | None = None
    # Quando a captura diária deste snapshot de fato rodou (UTC) - permite saber se o dado de
    # "hoje" está fresco (rodou há minutos) ou desatualizado (rodou há quase 24h), e comparar com
    # segurança contra um número "ao vivo" (ex.: opr_backlog_aging, que expõe generated_at).
    captured_at: datetime


class AiWarrantyAnalyticsRequest(BaseModel):
    date_from: date
    date_to: date
    period_basis: Literal["opened", "closed"] = "opened"
    denominator: Literal["closed_origins", "active_origins", "maintenance_total", "activation_closed"] = "active_origins"
    # Ativação/Mud. Endereço/Mud. Tecnologia com um desses diagnósticos deixa de contar como
    # origem elegível (ex.: "Desistência da solicitação") - mesmo filtro que já existe na tela.
    origin_excluded_diagnoses: list[str] = Field(default_factory=list, max_length=20)
    filters: AiOrderFilters = Field(default_factory=AiOrderFilters)

    model_config = ConfigDict(extra="forbid")


class AiWarrantyItem(BaseModel):
    contract_id: str | None
    customer_name: str | None
    regional: str | None
    diagnosis: str | None
    return_os_subject: str | None
    origin_order_code: str
    origin_os_type: str | None
    origin_closed_at: datetime
    return_order_code: str
    return_opened_at: datetime
    return_closed_at: datetime | None


class AiWarrantyAnalyticsResponse(BaseModel):
    period_basis: Literal["opened", "closed"]
    denominator: Literal["closed_origins", "active_origins", "maintenance_total", "activation_closed"]
    origin_excluded_diagnoses: list[str]
    numerator: int
    denominator_count: int
    percentage: float | None
    contracts_with_warranty: int
    customers_with_warranty: int
    breakdown: list[OperationBreakdownItem]
    by_regional: list[OperationWarrantyRegionalRankingItem]
    by_diagnosis: list[OperationBreakdownItem]
    by_subject: list[OperationBreakdownItem]
    by_origin_type: list[OperationWarrantyOriginTypeItem]
    items: list[AiWarrantyItem]
    items_truncated: bool
    meta: OperationResponseMetaOut


class AiTeamTargetsRequest(BaseModel):
    # Padrão hoje (data corrente) - a meta é sempre "a vigente nesta data", nunca "a mais recente"
    # (ver operations/models.py:OperationTeamTargetVersion).
    reference_date: date = Field(default_factory=date.today)

    model_config = ConfigDict(extra="forbid")


class AiTeamTargetItem(BaseModel):
    team_model: str
    period_type: Literal["weekday", "saturday", "sunday", "monthly"]
    target_quantity: int
    median_from_quantity: int
    good_from_quantity: int
    valid_from: datetime
    valid_to: datetime | None


class AiTeamTargetPerformanceRequest(BaseModel):
    date_from: date
    date_to: date
    granularity: Literal["day", "week", "month"] = "day"
    filters: AiOrderFilters = Field(default_factory=AiOrderFilters)

    model_config = ConfigDict(extra="forbid")


class AiTeamTargetPerformanceItem(BaseModel):
    period_start: date
    team_model: str
    actual: int
    target: int | None
    delta: int | None
    percentage_of_target: float | None


class AiTeamTargetPerformanceResponse(BaseModel):
    meta: OperationResponseMetaOut
    data: list[AiTeamTargetPerformanceItem]


class AiOfflineLoginClustersRequest(BaseModel):
    """Item 19 do pedido ("consulta de Infra" no monitor de incidentes) - mesmos parâmetros de
    `GET /operations/network/offline-login-clusters`, agora acessível para IA/MCP."""

    radius_meters: float = Field(default=300.0, ge=10.0, le=5000.0)
    min_cluster_size: int = Field(default=3, ge=2, le=100)
    window_minutes: int = Field(default=30, ge=5, le=1440, description="Janela de detecção - 30/60/90 minutos são os valores mais comuns.")

    model_config = ConfigDict(extra="forbid")


class AiOnuSignalRequest(BaseModel):
    """Telemetria óptica/ONU (sinal RX/TX em dBm, causa da última queda, transmissor) - só dos
    logins já monitorados pelo sistema, não a base inteira de ONUs do IXC."""

    login_ids: list[int] = Field(default_factory=list, max_length=200)
    last_drop_causes: list[str] = Field(default_factory=list)
    transmitter_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=200, ge=1, le=500)

    model_config = ConfigDict(extra="forbid")


class AiOnuSignalHistoryRequest(BaseModel):
    """Série histórica de telemetria óptica/ONU (um ponto por captura) - "o sinal do login/serial
    X estava em Y na data Z, e hoje está em W". Distinto de `AiOnuSignalRequest`: aqui é a série no
    tempo de um login/serial específico, não o estado mais recente de vários. Exige pelo menos
    `login_ids` ou `onu_serials`."""

    login_ids: list[int] = Field(default_factory=list, max_length=50)
    onu_serials: list[str] = Field(default_factory=list, max_length=50)
    date_from: datetime | None = None
    date_to: datetime | None = None
    limit: int = Field(default=500, ge=1, le=2000)

    model_config = ConfigDict(extra="forbid")


class AiManagementCaseDiagnosticsRequest(BaseModel):
    """Diagnóstico agregado de casos de Gestão Integrada (produtividade abaixo da meta) - "quem
    mais não bate meta, por regional/colaborador/motivo" - pedido do usuário em 2026-08-20 pra
    facilitar essa análise pela IA sem precisar abrir a tela. Mesmos filtros da tela de Gestão."""

    status: str | None = None
    severity: str | None = None
    regional: str | None = None
    case_type: str | None = None
    reference_year: int | None = None
    reference_month: int | None = Field(default=None, ge=1, le=12)
    only_overdue: bool = False
    only_open: bool = False
    search: str | None = None

    model_config = ConfigDict(extra="forbid")


class AiLoginStatusRequest(BaseModel):
    """Status ATUAL de conectividade por login - mesmos parâmetros de `GET
    /operations/network/logins`, agora acessível para IA/MCP via chave de API. Distinto de
    `AiOfflineLoginClustersRequest`: aqui é consulta individual (um login específico ou uma busca
    geográfica pontual), não a detecção de cluster de queda em massa."""

    logins: list[str] = Field(default_factory=list, max_length=200)
    online_statuses: list[str] = Field(default_factory=list)
    regionals: list[str] = Field(default_factory=list, description="Ex.: 'UNI - MACHADINHO DOESTE' - mesma normalização usada nas O.S.")
    near_latitude: float | None = Field(default=None, ge=-90, le=90)
    near_longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float | None = Field(default=None, gt=0, le=500)
    limit: int = Field(default=200, ge=1, le=500)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_geo_triplet(self) -> "AiLoginStatusRequest":
        if (self.near_latitude is None) != (self.near_longitude is None) or (
            self.radius_km is not None and self.near_latitude is None
        ):
            raise ValueError("Informe near_latitude, near_longitude e radius_km juntos, ou nenhum dos três.")
        return self


class AiSearchLoginsRequest(BaseModel):
    """Busca paginada de login - equivalente a `AiLoginStatusRequest`, mas com paginação real
    (total_encontrado/page/has_more) e filtros adicionais de PON/transmissor/contrato (via join com
    telemetria ONU) e datetime completo (gte/gt/lte/lt/eq, não só "a partir de")."""

    logins: list[str] = Field(default_factory=list, max_length=200)
    login_query: str | None = Field(default=None, max_length=160, description="Busca parcial (contém) pelo login.")
    login_ids: list[int] = Field(default_factory=list, max_length=200)
    online_statuses: list[str] = Field(default_factory=list)
    regionals: list[str] = Field(default_factory=list)
    pon_ids: list[str] = Field(default_factory=list)
    transmitter_ids: list[str] = Field(default_factory=list)
    contract_ids: list[str] = Field(default_factory=list)
    near_latitude: float | None = Field(default=None, ge=-90, le=90)
    near_longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float | None = Field(default=None, gt=0, le=500)
    status_changed_at: DateTimeFilterOp | None = None
    last_connected_at: DateTimeFilterOp | None = None
    last_disconnected_at: DateTimeFilterOp | None = None
    captured_at: DateTimeFilterOp | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_geo_triplet(self) -> "AiSearchLoginsRequest":
        if (self.near_latitude is None) != (self.near_longitude is None) or (
            self.radius_km is not None and self.near_latitude is None
        ):
            raise ValueError("Informe near_latitude, near_longitude e radius_km juntos, ou nenhum dos três.")
        return self


class AiLoginDetailRequest(BaseModel):
    login: str | None = Field(default=None, max_length=160)
    login_id: int | None = None
    history_hours: int = Field(default=24, ge=1, le=168)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_identifier(self) -> "AiLoginDetailRequest":
        if self.login is None and self.login_id is None:
            raise ValueError("Informe login ou login_id.")
        return self


class AiLoginAggregateRequest(BaseModel):
    group_by: Literal["regional", "online", "transmitter_id", "pon_id", "last_drop_cause"]
    regionals: list[str] = Field(default_factory=list)
    online_statuses: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class AiLoginOutagesRequest(BaseModel):
    since: datetime
    until: datetime | None = None
    regionals: list[str] = Field(default_factory=list)
    limit: int = Field(default=200, ge=1, le=1000)

    model_config = ConfigDict(extra="forbid")


class AiLoginTimeseriesRequest(BaseModel):
    since: datetime
    until: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class AiCoordinateQualityRequest(BaseModel):
    entity: Literal["operations_orders", "operations_login_current_status", "operations_onu_signal_current"]
    outlier_km: float = Field(default=300.0, gt=0, le=2000)
    duplicate_threshold: int = Field(default=20, ge=1, le=10000)

    model_config = ConfigDict(extra="forbid")


class AiLoginIncidentAnalysisRequest(BaseModel):
    window_minutes: int = Field(default=90, ge=5, le=1440)
    regionals: list[str] = Field(default_factory=list)
    cluster_radius_meters: float = Field(default=300.0, ge=10.0, le=5000.0)
    cluster_min_size: int = Field(default=3, ge=2, le=100)

    model_config = ConfigDict(extra="forbid")
