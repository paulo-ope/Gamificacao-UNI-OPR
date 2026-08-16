#!/usr/bin/env python3
"""MCP server para o módulo de IA da Operação Analítica (backend/app/modules/ai).

Expõe como tools MCP as mesmas rotas que já existem em /api/ai/* (protegidas por chave de API,
permissão "ai:query") - este servidor não reimplementa nenhuma lógica de análise, só chama a API
já em produção via HTTP. Roda local (stdio), pensado para Claude Code e Claude Desktop.

Configuração via variáveis de ambiente:
    OPR_API_BASE_URL   Base da API, ex.: "https://operacao.souuni.com/api" (produção, backend na
                       VM) ou "http://localhost:8000/api" (backend local)
    OPR_API_KEY        Chave de API com permissão "ai:query" (ver README.md deste diretório sobre
                        como gerar uma com `python -m app.modules.ai.cli create-service-user`)

Os filtros de O.S. (regional, cidade, bairro, assunto, responsável, coordenadas, etapa de SLA
etc.) são passados como um dicionário livre (`filters`), não como campos individuais no schema de
cada tool - ver `FILTERS_DOC` para a lista de chaves aceitas. Essa lista é mantida manualmente e
pode ficar desatualizada se o backend ganhar filtros novos sem atualizar este arquivo; chame
`opr_list_fields` para conferir o que a API aceita "ao vivo" quando um filtro parecer não ter
efeito.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

mcp = FastMCP("opr_analitica_mcp")

API_BASE_URL = os.environ.get("OPR_API_BASE_URL", "http://localhost:8000/api").rstrip("/")
API_KEY = os.environ.get("OPR_API_KEY", "")
HTTP_TIMEOUT_SECONDS = 60.0

if not API_KEY:
    raise RuntimeError(
        "OPR_API_KEY não está definida. Gere uma chave com:\n"
        '  docker exec opr-gamification-backend python -m app.modules.ai.cli '
        'create-service-user --name "Claude MCP"\n'
        "e defina OPR_API_KEY (e, se necessário, OPR_API_BASE_URL) na configuração do MCP - "
        "ver README.md deste diretório."
    )

# Documentação das chaves aceitas em `filters` - mesmo vocabulário de AiOrderFilters
# (backend/app/modules/ai/schemas.py). Mantida aqui só para orientar quem for chamar as tools;
# a validação de verdade acontece no backend, que rejeita chave desconhecida (extra="forbid").
FILTERS_DOC = """
Chaves aceitas em `filters` (todas opcionais; listas vazias/None = sem filtro):
- team_models, companies, regionals, states, cities, contract_types, person_types, os_types,
  subjects, diagnoses, departments, sectors, priorities, creators, responsibles, statuses,
  sla_statuses, projects, pops: list[str] - filtro exato (valor precisa bater igual).
- text_filters: list[{"field": ..., "operator": "contains"|"starts_with"|"ends_with"|"not_equals",
  "value": str}] - "field" aceita: sector, subject, diagnosis, responsible, city, department,
  service_description (descrição de abertura da O.S.), neighborhood (bairro).
- scheduled_after_sla, sla_expired_before_schedule: bool - indicadores de em que etapa o SLA foi
  perdido (ver group_by="scheduled_after_sla"/"sla_expired_before_schedule" para agrupar por eles).
- has_coordinates: bool - só O.S. com (True) ou sem (False) latitude/longitude preenchidas.
- near_latitude, near_longitude, radius_km: float - só tem efeito com os três juntos; filtra O.S.
  dentro de `radius_km` quilômetros do ponto (near_latitude, near_longitude). Útil para achar
  reincidência perto de uma O.S. já conhecida (usando as coordenadas dela como centro).
- customer_logins: list[str] - login PPPoE/fibra do cliente (mesmo valor de opr_login_status) -
  use para "todas as O.S. deste login".
- opened_at, closed_at, deadline_at, scheduled_at, assumed_at, displacement_started_at,
  execution_started_at, finished_at, source_updated_at: {"gte"/"gt"/"lte"/"lt"/"eq": "AAAA-MM-DDTHH:MM:SS±HH:MM"}
  - filtro fino por HORÁRIO EXATO (não só o dia), aceita qualquer timezone de entrada. Aditivo a
  date_from/date_to (que continuam obrigatórios, granularidade de dia) - use para "O.S. abertas
  nos últimos 30 minutos" (date_from=date_to=hoje + opened_at={"gte": "agora-30min"}) ou "entre
  17:30 e 18:00" (opened_at={"gte": "...17:30:00-04:00", "lte": "...18:00:00-04:00"}).
"""

GROUP_BY_DOC = """
Dimensões aceitas em group_by (uma string, ou lista de até 3 para agrupamento composto):
regional, city, neighborhood, os_type, subject, diagnosis, department, sector, priority,
responsible, status, sla_status, team_model, scheduled_after_sla, sla_expired_before_schedule,
geo_cluster (agrupa O.S. de ponto geográfico praticamente coincidente, ~111m).
"""


def _post(endpoint: str, payload: dict) -> Any:
    with httpx.Client() as client:
        response = client.post(
            f"{API_BASE_URL}/ai/{endpoint}",
            json=payload,
            headers={"x-api-key": API_KEY},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        return _parse_response(response, endpoint)


def _get(endpoint: str) -> Any:
    with httpx.Client() as client:
        response = client.get(
            f"{API_BASE_URL}/ai/{endpoint}",
            headers={"x-api-key": API_KEY},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        return _parse_response(response, endpoint)


def _parse_response(response: httpx.Response, endpoint: str) -> Any:
    if response.status_code == 401:
        raise RuntimeError(
            "Chave de API inválida ou revogada. Gere uma nova com "
            "`docker exec opr-gamification-backend python -m app.modules.ai.cli "
            'create-service-user --name "Claude MCP"` e atualize OPR_API_KEY.'
        )
    if response.status_code == 403:
        raise RuntimeError("Permissão insuficiente (a chave precisa da permissão 'ai:query').")
    if response.status_code == 422:
        raise RuntimeError(f"Parâmetros inválidos para {endpoint}: {response.text}")
    response.raise_for_status()
    return response.json()


def _dump(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def _call(endpoint: str, payload: dict) -> str:
    """Wrapper comum a todas as tools POST: chama o endpoint e converte qualquer erro numa
    mensagem de texto acionável, em vez de deixar a exceção subir crua para o cliente MCP."""
    try:
        return _dump(_post(endpoint, payload))
    except httpx.TimeoutException:
        return f"Erro: tempo esgotado chamando {endpoint}. Tente um período menor ou tente de novo."
    except httpx.ConnectError:
        return (
            f"Erro: não foi possível conectar em {API_BASE_URL}. Confirme se o backend está no "
            f"ar e se OPR_API_BASE_URL está correta (valor atual: {API_BASE_URL})."
        )
    except Exception as exc:  # noqa: BLE001 - repassado como texto pro agente decidir o que fazer
        return f"Erro: {exc}"


class DateRangeFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: str = Field(..., description="Data inicial do período, formato AAAA-MM-DD.")
    date_to: str = Field(..., description="Data final do período, formato AAAA-MM-DD.")
    filters: dict[str, Any] = Field(default_factory=dict, description=FILTERS_DOC)


class AggregateOrdersInput(DateRangeFilters):
    group_by: str | list[str] = Field(..., description="Dimensão (ou lista de até 3). " + GROUP_BY_DOC)
    metric: str = Field(
        ...,
        description=(
            "Métrica a calcular por grupo: quantidade_aberta, quantidade_fechada, taxa_sla, "
            "horas_medias, quantidade_atrasada, quantidade_backlog, horas_abertura_agenda "
            "(abertura->agendamento), horas_agenda_execucao (agendamento->execução), "
            "horas_execucao_fechamento (execução->fechamento), horas_abertura_fechamento "
            "(abertura->fechamento, total)."
        ),
    )


@mcp.tool(
    name="opr_aggregate_orders",
    annotations={
        "title": "Agregar O.S. por dimensão",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def opr_aggregate_orders(params: AggregateOrdersInput) -> str:
    """Agrupa Ordens de Serviço por uma dimensão (ou até 3 combinadas) e calcula uma métrica por
    grupo - a ferramenta principal para "concentração de X por Y" (ex.: backlog por bairro,
    quantidade de O.S. por assunto, taxa de SLA por regional, horas médias de execução por
    modelo de equipe).

    Args:
        params (AggregateOrdersInput): date_from, date_to (AAAA-MM-DD), group_by (uma dimensão ou
            lista de até 3, ver GROUP_BY_DOC), metric (ver descrição do campo), filters (ver
            FILTERS_DOC). Piloto do FilterContractV1 (docs/proposta-filter-contract-v1.md):
            `os_subjects` é o nome canônico do filtro de assunto da O.S. neste endpoint -
            `subjects` continua funcionando (alias depreciado), só passa a gerar um aviso
            DEPRECATED_FILTER_ALIAS em `meta.warnings`.

    Returns:
        str: JSON {"meta": {...}, "data": [...]}. Com 1 dimensão, cada item de `data`:
        [{"label": str, "quantity": int, "metric_value": float, "percentage": float}, ...],
        ordenado por quantidade decrescente. Com 2-3 dimensões: cada item troca "label" por uma
        chave por dimensão pedida
        (ex.: {"regional": ..., "subject": ..., "quantity": ..., "metric_value": ..., "percentage": ...}).

    Exemplos de uso:
        - "Quais bairros têm mais O.S. em aberto?" -> group_by="neighborhood", metric="quantidade_backlog"
        - "Taxa de SLA por regional em julho" -> group_by="regional", metric="taxa_sla"
        - "Onde o SLA está sendo perdido: na agenda ou na execução?" -> comparar
          metric="horas_abertura_agenda" vs "horas_agenda_execucao" vs "horas_execucao_fechamento"
        - "Clusters de chamado por ponto geográfico" -> group_by="geo_cluster", metric="quantidade_aberta"
    """
    payload = {
        "date_from": params.date_from,
        "date_to": params.date_to,
        "group_by": params.group_by,
        "metric": params.metric,
        "filters": params.filters,
    }
    return _call("aggregate-orders", payload)


class OrdersTimeseriesInput(DateRangeFilters):
    metric: str = Field(..., description="abertas, fechadas ou saldo (abertas - fechadas).")
    granularity: str = Field(default="day", description="day, week ou month.")
    group_by: str | None = Field(
        default=None, description="Dimensão opcional para quebrar cada ponto da série. " + GROUP_BY_DOC
    )


@mcp.tool(
    name="opr_orders_timeseries",
    annotations={
        "title": "Série temporal de O.S.",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def opr_orders_timeseries(params: OrdersTimeseriesInput) -> str:
    """Série temporal (dia/semana/mês) de O.S. abertas, fechadas, ou o saldo entre as duas -
    para ver tendência ao longo do tempo, opcionalmente quebrada por uma dimensão.

    Args:
        params (OrdersTimeseriesInput): date_from, date_to, metric (abertas/fechadas/saldo),
            granularity (day/week/month, default day), group_by (opcional, ver GROUP_BY_DOC),
            filters (ver FILTERS_DOC).

    Returns:
        str: JSON com lista de pontos [{"period_start": "AAAA-MM-DD", "quantity": int,
        "group": str|null}, ...]. "group" só aparece quando group_by foi informado.

    Exemplos de uso:
        - "Evolução diária de O.S. abertas em agosto" -> metric="abertas", granularity="day"
        - "O backlog está crescendo ou diminuindo por semana?" -> metric="saldo", granularity="week"
        - "Produção fechada por modelo de equipe, mês a mês" -> metric="fechadas",
          granularity="month", group_by="team_model"
    """
    payload = {
        "date_from": params.date_from,
        "date_to": params.date_to,
        "metric": params.metric,
        "granularity": params.granularity,
        "group_by": params.group_by,
        "filters": params.filters,
    }
    return _call("orders-timeseries", payload)


class SearchOrdersInput(DateRangeFilters):
    page: int = Field(default=1, ge=1, description="Página (1-indexado).")
    page_size: int = Field(default=50, ge=10, le=200, description="Itens por página (10-200).")
    keyword: str | None = Field(
        default=None, max_length=160, description="Busca livre (mesmo campo 'search' do resto do sistema)."
    )
    date_field: str | None = Field(
        default=None,
        description=(
            "opened_at, closed_at, scheduled_at, assumed_at, displacement_started_at, "
            "execution_started_at, finished_at ou deadline_at - default (None) mantém a regra "
            "'abriu OU fechou no período'. Nunca use opened_at como substituto de closed_at."
        ),
    )
    fields: list[str] | None = Field(
        default=None,
        description="Subconjunto de campos a retornar (nomes iguais aos do item de resposta) - rejeitado explicitamente se algum não estiver autorizado.",
    )
    response_mode: str = Field(
        default="full",
        description="'full' (default, todos os campos autorizados) ou 'summary' (poucos campos, para triagem).",
    )


@mcp.tool(
    name="opr_search_orders",
    annotations={
        "title": "Buscar O.S. individuais",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def opr_search_orders(params: SearchOrdersInput) -> str:
    """Busca paginada de O.S. individuais, com texto qualitativo (descrição de abertura, relato
    técnico) e todos os campos de SLA/tempo já calculados - use para ler o conteúdo de O.S.
    específicas, não para números agregados (para isso, use opr_aggregate_orders).

    IMPORTANTE sobre date_from/date_to: uma O.S. entra no resultado se teve QUALQUER atividade no
    período - abriu OU fechou dentro de [date_from, date_to] (união, não intersecção). Uma O.S.
    aberta antes de date_from mas fechada dentro do período aparece, e vice-versa. Não é "abertas
    no período"; é "com atividade no período" (mesma semântica da tela de Operação).

    Args:
        params (SearchOrdersInput): date_from, date_to, page (default 1), page_size (10-200,
            default 50), keyword (busca livre opcional), filters (ver FILTERS_DOC - incluindo o
            filtro geográfico de raio, útil para "O.S. perto deste ponto/desta O.S."). Piloto do
            FilterContractV1 (docs/proposta-filter-contract-v1.md): `os_subjects` é o nome
            canônico do filtro de assunto da O.S. - `subjects` continua funcionando (alias
            depreciado), só passa a gerar um aviso DEPRECATED_FILTER_ALIAS em `meta.warnings`.

    Returns:
        str: JSON {"items": [...], "total_encontrado": int, "page": int, "page_size": int,
        "has_more": bool, "meta": {...}}. Cada item inclui order_code, regional, city, neighborhood, sector,
        latitude, longitude, distance_km (só quando o filtro de raio foi usado), service_description,
        technical_report, service_address, datas do ciclo de vida (opened_at, scheduled_at,
        execution_started_at, closed_at, sla_deadline_at...), indicadores de etapa de SLA
        (scheduled_after_sla, sla_expired_before_schedule, hours_open_to_schedule, etc.) e a meta
        de equipe vigente na O.S. (team_target_*).

    Exemplos de uso:
        - "Me mostra as O.S. abertas essa semana no bairro Centro sobre queda de sinal" ->
          filters={"text_filters": [{"field": "neighborhood", "operator": "contains", "value": "centro"},
          {"field": "service_description", "operator": "contains", "value": "queda de sinal"}]}
        - "Tem outra O.S. perto das coordenadas -10.88,-61.90 nos últimos 30 dias?" ->
          filters={"near_latitude": -10.88, "near_longitude": -61.90, "radius_km": 1}
    """
    payload = {
        "date_from": params.date_from,
        "date_to": params.date_to,
        "page": params.page,
        "page_size": params.page_size,
        "keyword": params.keyword,
        "filters": params.filters,
        "date_field": params.date_field,
        "fields": params.fields,
        "response_mode": params.response_mode,
    }
    return _call("search-orders", payload)


class OrderDetailsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_codes: list[str] = Field(default_factory=list, description="Lista de order_code (ex.: 'IXC-12345'). Até 50 por chamada.")
    source_order_ids: list[str] = Field(default_factory=list, description="Lista de OS_ID bruto do IXC. Até 50 por chamada.")
    fields: list[str] | None = Field(
        default=None,
        description="Subconjunto de campos a retornar - rejeitado explicitamente se algum não estiver autorizado.",
    )
    response_mode: str = Field(
        default="full",
        description="'full' (default, todos os detalhes autorizados) ou 'summary' (poucos campos).",
    )


@mcp.tool(
    name="opr_order_details",
    annotations={
        "title": "Detalhe de O.S. por order_code/OS_ID",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def opr_order_details(params: OrderDetailsInput) -> str:
    """Detalhe de uma ou várias O.S. por `order_code` e/ou `source_order_id` (OS_ID) - use quando
    já se sabe qual(is) O.S. se quer (ex.: após uma triagem com opr_search_orders em
    response_mode="summary"), em vez de opr_search_orders com filtro/keyword. Não exige período.

    Args:
        params (OrderDetailsInput): order_codes e/ou source_order_ids (pelo menos um não vazio),
            fields (subconjunto de campos), response_mode ("full" ou "summary").

    Returns:
        str: JSON {"items": [...], "not_found_order_codes": [...], "not_found_source_order_ids": [...]}.
    """
    if not params.order_codes and not params.source_order_ids:
        return "Erro: informe ao menos um order_code ou source_order_id (OS_ID) em params."
    payload = {
        "order_codes": params.order_codes,
        "source_order_ids": params.source_order_ids,
        "fields": params.fields,
        "response_mode": params.response_mode,
    }
    return _call("orders/details", payload)


class LoginStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logins: list[str] = Field(default_factory=list, description="Lista de login (ex.: 'cliente.teste'). Vazio = sem filtro por login.")
    online_statuses: list[str] = Field(
        default_factory=list,
        description=(
            "Filtra pelo status bruto do IXC - 'S' (conectado), 'N' (desconectado - sinal real de "
            "queda recente), 'SS' (conectado sem sinal, característica crônica de "
            "equipamento/login, não é queda recente)."
        ),
    )
    regionals: list[str] = Field(
        default_factory=list,
        description="Filtra pela regional (ex.: 'UNI - MACHADINHO DOESTE') - mesma normalização usada nas O.S.",
    )
    near_latitude: float | None = Field(default=None, description="Busca geográfica por raio - use junto com near_longitude e radius_km.")
    near_longitude: float | None = Field(default=None)
    radius_km: float | None = Field(default=None)
    limit: int = Field(default=200, ge=1, le=500)


@mcp.tool(
    name="opr_login_status",
    annotations={
        "title": "Status de conectividade de login",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def opr_login_status(params: LoginStatusInput) -> str:
    """Status ATUAL de conectividade por login - não é um evento de queda, é o estado agora e há
    quanto tempo está nesse estado. Use para "quais logins estão desconectados perto deste
    ponto/nesta regional" ou "há quanto tempo esse login caiu".

    Args:
        params (LoginStatusInput): logins, online_statuses, regionals,
            near_latitude/near_longitude/radius_km (os três juntos, ou nenhum), limit (até 500,
            default 200).

    Returns:
        str: JSON com lista de {"login_id", "login", "online", "regional", "latitude",
        "longitude", "last_connected_at", "last_disconnected_at", "status_changed_at",
        "captured_at"}. `status_changed_at` só avança quando `online` muda de valor - é o campo
        certo para "quando começou esse estado", não `captured_at` (última vez que o sistema viu o
        login).
    """
    payload = {
        "logins": params.logins,
        "online_statuses": params.online_statuses,
        "regionals": params.regionals,
        "near_latitude": params.near_latitude,
        "near_longitude": params.near_longitude,
        "radius_km": params.radius_km,
        "limit": params.limit,
    }
    return _call("infra/login-status", payload)


class OnuSignalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login_ids: list[int] = Field(default_factory=list, max_length=200, description="Lista de login_id. Vazio = sem filtro.")
    last_drop_causes: list[str] = Field(
        default_factory=list,
        description="Filtra pela causa da última queda registrada na ONU (ex.: 'Link Loss', 'Power Fail' - varia conforme o hardware).",
    )
    transmitter_ids: list[str] = Field(default_factory=list, description="Filtra por id do transmissor/OLT.")
    limit: int = Field(default=200, ge=1, le=500)


@mcp.tool(
    name="opr_onu_signal",
    annotations={
        "title": "Telemetria óptica/ONU e PON",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def opr_onu_signal(params: OnuSignalInput) -> str:
    """Telemetria óptica/ONU (sinal RX/TX em dBm, causa da última queda, transmissor/OLT, PON/slot)
    dos logins já monitorados por opr_login_status. Não cobre a base inteira de ONUs do IXC (~90
    mil) - só os logins que o sistema já acompanha, para não sobrecarregar a API deles.

    Args:
        params (OnuSignalInput): login_ids, last_drop_causes, transmitter_ids, limit (até 500,
            default 200).

    Returns:
        str: JSON com lista de {"login_id", "login", "contract_id", "signal_rx_dbm",
        "signal_tx_dbm", "last_drop_cause", "onu_serial", "onu_model", "transmitter_id",
        "temperature_c", "voltage", "signal_measured_at", "pon_id", "pon_no", "slot_no",
        "latitude", "longitude", "captured_at"}.
    """
    payload = {
        "login_ids": params.login_ids,
        "last_drop_causes": params.last_drop_causes,
        "transmitter_ids": params.transmitter_ids,
        "limit": params.limit,
    }
    return _call("infra/onu-signal", payload)


DateTimeOpDoc = (
    'Filtro fino de horário exato: {"gte"/"gt"/"lte"/"lt"/"eq": "AAAA-MM-DDTHH:MM:SS±HH:MM"} - '
    "aceita qualquer timezone de entrada."
)


class SearchLoginsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logins: list[str] = Field(default_factory=list, description="Lista de login exato. Vazio = sem filtro.")
    login_query: str | None = Field(default=None, description="Busca parcial (contém) pelo login.")
    login_ids: list[int] = Field(default_factory=list)
    online_statuses: list[str] = Field(default_factory=list, description="'S' (conectado), 'N' (desconectado), 'SS' (sem sinal, crônico).")
    regionals: list[str] = Field(default_factory=list, description="Ex.: 'UNI - MACHADINHO DOESTE'.")
    pon_ids: list[str] = Field(default_factory=list, description="Filtra pela telemetria ONU (join) - só logins com telemetria capturada aparecem.")
    transmitter_ids: list[str] = Field(default_factory=list)
    contract_ids: list[str] = Field(default_factory=list)
    near_latitude: float | None = Field(default=None, description="Busca geográfica por raio - use junto com near_longitude e radius_km.")
    near_longitude: float | None = Field(default=None)
    radius_km: float | None = Field(default=None)
    status_changed_at: dict[str, str] | None = Field(default=None, description=DateTimeOpDoc)
    last_connected_at: dict[str, str] | None = Field(default=None, description=DateTimeOpDoc)
    last_disconnected_at: dict[str, str] | None = Field(default=None, description=DateTimeOpDoc + ' Ex.: "caiu nos últimos 60 min" = {"gte": "<agora-60min>"}.')
    captured_at: dict[str, str] | None = Field(default=None, description=DateTimeOpDoc)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)


@mcp.tool(
    name="opr_search_logins",
    annotations={
        "title": "Buscar logins (paginado)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def opr_search_logins(params: SearchLoginsInput) -> str:
    """Busca paginada de login - equivalente de opr_search_orders para logins. Use para "pesquise
    o login X", "quais logins estão desconectados na regional Y", "quais logins caíram nos últimos
    N minutos", "quais logins estão numa PON/transmissor específico".

    Args:
        params (SearchLoginsInput): logins/login_query, login_ids, online_statuses, regionals,
            pon_ids/transmitter_ids/contract_ids (via telemetria ONU),
            near_latitude/near_longitude/radius_km, filtros de datetime, page/page_size.

    Returns:
        str: JSON {"items": [...], "total_encontrado": int, "page": int, "page_size": int,
        "has_more": bool, "meta": {...}}. Cada item inclui login_id, login, online, regional,
        latitude/longitude, last_connected_at, last_disconnected_at, status_changed_at,
        captured_at, contract_id, pon_id, transmitter_id, last_drop_cause.
    """
    payload = {
        "logins": params.logins,
        "login_query": params.login_query,
        "login_ids": params.login_ids,
        "online_statuses": params.online_statuses,
        "regionals": params.regionals,
        "pon_ids": params.pon_ids,
        "transmitter_ids": params.transmitter_ids,
        "contract_ids": params.contract_ids,
        "near_latitude": params.near_latitude,
        "near_longitude": params.near_longitude,
        "radius_km": params.radius_km,
        "status_changed_at": params.status_changed_at,
        "last_connected_at": params.last_connected_at,
        "last_disconnected_at": params.last_disconnected_at,
        "captured_at": params.captured_at,
        "page": params.page,
        "page_size": params.page_size,
    }
    return _call("infra/search-logins", payload)


class LoginDetailInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str | None = Field(default=None, description="Login exato. Informe login ou login_id.")
    login_id: int | None = Field(default=None)
    history_hours: int = Field(default=24, ge=1, le=168, description="Janela do histórico de eventos recentes.")


@mcp.tool(
    name="opr_get_login_detail",
    annotations={
        "title": "Detalhe completo de um login",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def opr_get_login_detail(params: LoginDetailInput) -> str:
    """Detalhamento completo de um login - identificação, status de conexão com tempo já calculado
    no estado atual (ex.: "offline há 47 minutos"), telemetria ONU/PON e histórico recente de
    eventos de conexão/desconexão. Use depois de achar o login via opr_search_logins/
    opr_login_status, quando precisar de TODOS os detalhes de um único login.

    Args:
        params (LoginDetailInput): login ou login_id (pelo menos um), history_hours (1-168,
            default 24).

    Returns:
        str: JSON com identificação, status (`seconds_in_current_state` já calculado), telemetria
        ONU/PON e `recent_events`: lista de {"event": "connected"|"disconnected", "at": timestamp}
        reconstruída do histórico real (horário exato registrado pelo IXC).
    """
    if params.login is None and params.login_id is None:
        return "Erro: informe login ou login_id em params."
    payload = {"login": params.login, "login_id": params.login_id, "history_hours": params.history_hours}
    return _call("infra/login-detail", payload)


class LoginAggregateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_by: str = Field(..., description="regional, online, transmitter_id, pon_id ou last_drop_cause.")
    regionals: list[str] = Field(default_factory=list)
    online_statuses: list[str] = Field(default_factory=list)


@mcp.tool(
    name="opr_login_aggregate",
    annotations={
        "title": "Agregar logins por dimensão",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def opr_login_aggregate(params: LoginAggregateInput) -> str:
    """Contagem de logins por dimensão - "quantos offline por regional", "quantos por PON",
    "quantos por transmissor/OLT", "quantos por causa de queda". Use para detectar concentração
    (incidente coletivo) sem baixar registro por registro.

    Args:
        params (LoginAggregateInput): group_by (regional/online/transmitter_id/pon_id/
            last_drop_cause - valor inválido rejeitado com erro claro), regionals/online_statuses
            (filtros opcionais antes de agregar).

    Returns:
        str: JSON {"meta": {...}, "data": [{"label": str, "quantity": int, "percentage": float},
        ...]}, `data` ordenado por quantidade decrescente. `meta.applied_filters` mostra o que de
        fato foi usado; `meta.source_last_sync` indica há quanto tempo o snapshot é real.
    """
    payload = {"group_by": params.group_by, "regionals": params.regionals, "online_statuses": params.online_statuses}
    return _call("infra/login-aggregate", payload)


class LoginOutagesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    since: str = Field(..., description="Início da janela, ISO8601 (ex.: '2026-08-15T17:00:00-04:00').")
    until: str | None = Field(default=None, description="Fim da janela - default agora.")
    regionals: list[str] = Field(default_factory=list)
    limit: int = Field(default=200, ge=1, le=1000)


@mcp.tool(
    name="opr_login_outages",
    annotations={
        "title": "Quedas de login por período",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def opr_login_outages(params: LoginOutagesInput) -> str:
    """Logins que estão OFFLINE agora e caíram dentro de [since, until] - candidatos a incidente
    coletivo quando concentrados na mesma regional. Não pega quedas que já reconectaram (para isso,
    use opr_get_login_detail no login específico).

    Args:
        params (LoginOutagesInput): since/until (ISO8601), regionals (opcional), limit (até 1000).

    Returns:
        str: JSON {"meta": {...}, "data": [{"login_id", "login", "regional", "latitude",
        "longitude", "status_changed_at", "last_disconnected_at"}, ...]}, `data` mais recente
        primeiro. `meta.warnings` avisa se o resultado foi truncado pelo teto do endpoint.
    """
    payload = {"since": params.since, "until": params.until, "regionals": params.regionals, "limit": params.limit}
    return _call("infra/login-outages", payload)


class LoginTimeseriesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    since: str = Field(..., description="Início da janela, ISO8601.")
    until: str | None = Field(default=None, description="Fim da janela - default agora.")


@mcp.tool(
    name="opr_login_timeseries",
    annotations={
        "title": "Série temporal de conectividade",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def opr_login_timeseries(params: LoginTimeseriesInput) -> str:
    """Série temporal de conectados/desconectados/quedas novas/reconexões novas - um ponto por
    captura real do snapshot periódico. Use para ver a curva de quedas ao longo do tempo (ex.:
    "17:00 → 15 desconectados, 17:15 → 47" indica incidente coletivo em andamento).

    Args:
        params (LoginTimeseriesInput): since/until (ISO8601).

    Returns:
        str: JSON {"meta": {...}, "data": [{"captured_at", "connected", "disconnected",
        "new_drops", "new_reconnects"}, ...]}, `data` em ordem cronológica.
    """
    payload = {"since": params.since, "until": params.until}
    return _call("infra/login-timeseries", payload)


class OfflineLoginClustersInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    radius_meters: float = Field(default=300.0, ge=10.0, le=5000.0, description="Raio de vizinhança entre dois logins pra contarem como próximos.")
    min_cluster_size: int = Field(default=3, ge=2, le=100, description="Mínimo de logins vizinhos pra formar um cluster.")
    window_minutes: int = Field(default=30, ge=5, le=1440, description="Janela de detecção - só considera quedas dentro desse intervalo.")


@mcp.tool(
    name="opr_offline_login_clusters",
    annotations={
        "title": "Clusters geográficos de queda de login",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def opr_offline_login_clusters(params: OfflineLoginClustersInput) -> str:
    """Agrupa logins que caíram nos últimos `window_minutes` e estão geograficamente próximos -
    candidato a rompimento de fibra num trecho (distinto de uma queda isolada de um único cliente).
    Já faz o agrupamento espacial no backend (DBSCAN sobre grade), em vez de baixar
    opr_login_status/opr_login_outages e agrupar manualmente. Só considera proximidade e tempo de
    desconexão - não filtra por regional/setor/assunto de O.S.

    Args:
        params (OfflineLoginClustersInput): radius_meters (10-5000, default 300),
            min_cluster_size (2-100, default 3), window_minutes (5-1440, default 30).

    Returns:
        str: JSON {"radius_meters", "min_cluster_size", "window_minutes", "clusters": [{
        "center_latitude", "center_longitude", "radius_meters", "size", "logins": [{"login_id",
        "login", "online", "latitude", "longitude", "last_disconnected_at"}, ...]}, ...],
        "meta": {...}}, `clusters` ordenado do maior pro menor.
    """
    payload = {
        "radius_meters": params.radius_meters,
        "min_cluster_size": params.min_cluster_size,
        "window_minutes": params.window_minutes,
    }
    return _call("infra/offline-login-clusters", payload)


class LoginIncidentAnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_minutes: int = Field(default=90, ge=5, le=1440, description="Janela de análise.")
    regionals: list[str] = Field(default_factory=list, description="Filtro opcional - não se aplica aos geo_clusters de propósito.")
    cluster_radius_meters: float = Field(default=300.0, ge=10.0, le=5000.0)
    cluster_min_size: int = Field(default=3, ge=2, le=100)


@mcp.tool(
    name="opr_login_incident_analysis",
    annotations={
        "title": "Funil de incidente coletivo",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def opr_login_incident_analysis(params: LoginIncidentAnalysisInput) -> str:
    """Funil de incidente coletivo numa única chamada - quedas novas, ainda offline, reconexões,
    quebra por regional/transmissor/PON/causa de queda e clusters geográficos, já agregados no
    backend. Use esta tool PRIMEIRO ao investigar um possível incidente (evita várias chamadas
    separadas de opr_login_outages/opr_login_aggregate/opr_login_timeseries).

    Args:
        params (LoginIncidentAnalysisInput): window_minutes (5-1440, default 90), regionals
            (opcional), cluster_radius_meters/cluster_min_size (parâmetros do agrupamento
            geográfico).

    Returns:
        str: JSON {"window_minutes", "since", "new_drops", "still_offline", "reconnects",
        "by_regional", "by_transmitter", "by_pon", "by_drop_cause": [{"label", "quantity",
        "percentage"}, ...], "geo_clusters": [{"center_latitude", "center_longitude",
        "radius_meters", "size", "logins": [...]}, ...], "meta": {...}}.
    """
    payload = {
        "window_minutes": params.window_minutes,
        "regionals": params.regionals,
        "cluster_radius_meters": params.cluster_radius_meters,
        "cluster_min_size": params.cluster_min_size,
    }
    return _call("infra/login-incident-analysis", payload)


class CoordinateQualityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity: str = Field(..., description="operations_orders, operations_login_current_status ou operations_onu_signal_current.")
    outlier_km: float = Field(default=300.0, gt=0, le=2000)
    duplicate_threshold: int = Field(default=20, ge=1, le=10000)


@mcp.tool(
    name="opr_coordinate_quality_audit",
    annotations={
        "title": "Auditoria de qualidade de coordenadas",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def opr_coordinate_quality_audit(params: CoordinateQualityInput) -> str:
    """Auditoria de qualidade de latitude/longitude, quebrada por regional - SÓ classifica e conta,
    nenhuma correção automática. Use ANTES de confiar em qualquer cluster geográfico
    (opr_offline_login_clusters, opr_login_incident_analysis) - coordenada ruim produz cluster
    sofisticado e errado sem nenhum aviso.

    Args:
        params (CoordinateQualityInput): entity (operations_orders/
            operations_login_current_status/operations_onu_signal_current), outlier_km (default
            300), duplicate_threshold (default 20).

    Returns:
        str: JSON {"meta": {...}, "data": [{"entity", "regional", "total", "validated", "missing",
        "invalid_range", "zero_zero", "outside_region", "suspicious_duplicates",
        "valid_coverage_pct"}, ...]}, um item de `data` por regional.
    """
    payload = {
        "entity": params.entity,
        "outlier_km": params.outlier_km,
        "duplicate_threshold": params.duplicate_threshold,
    }
    return _call("infra/coordinate-quality", payload)


class BacklogAgingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_to: str = Field(..., description="Data de referência do backlog, formato AAAA-MM-DD.")
    group_by: str = Field(default="regional", description="Uma dimensão só. " + GROUP_BY_DOC)
    filters: dict[str, Any] = Field(default_factory=dict, description=FILTERS_DOC)


@mcp.tool(
    name="opr_backlog_aging",
    annotations={
        "title": "Idade do backlog por dimensão",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def opr_backlog_aging(params: BacklogAgingInput) -> str:
    """Idade do backlog (O.S. ainda abertas em date_to) por dimensão: quantidade, idade média e
    mediana em dias, a O.S. mais antiga, e quantas passam de 1/3/5/7/15 dias.

    Args:
        params (BacklogAgingInput): date_to (AAAA-MM-DD), group_by (uma dimensão, default
            "regional", ver GROUP_BY_DOC), filters (ver FILTERS_DOC). Piloto do FilterContractV1
            (docs/proposta-filter-contract-v1.md): `os_subjects` é o nome canônico do filtro de
            assunto da O.S. - `subjects` continua funcionando (alias depreciado), só passa a
            gerar um aviso DEPRECATED_FILTER_ALIAS em `meta.warnings`.

    Returns:
        str: JSON {"meta": {...}, "data": [{"label": str, "quantity": int, "avg_age_days": float,
        "median_age_days": float, "oldest_order_code": str, "oldest_age_days": float,
        "over_1d": int, "over_3d": int, "over_5d": int, "over_7d": int, "over_15d": int}, ...]},
        `data` ordenado por quantidade decrescente.

    Exemplos de uso:
        - "Qual bairro tem o backlog mais velho?" -> group_by="neighborhood", ordenar por avg_age_days
        - "Quantas O.S. estão abertas há mais de 7 dias por setor?" -> group_by="sector", ler over_7d
    """
    payload = {"date_to": params.date_to, "group_by": params.group_by, "filters": params.filters}
    return _call("backlog-aging", payload)


class BacklogHistoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: str = Field(..., description="Data inicial, formato AAAA-MM-DD.")
    date_to: str = Field(..., description="Data final, formato AAAA-MM-DD.")
    metric: str = Field(..., description="backlog ou backlog_atrasado.")
    group_by: str = Field(
        default="none", description="none, regional, team_model, sector ou city (só essas cinco)."
    )
    sector_filter: dict[str, str] | None = Field(
        default=None,
        description=(
            'Filtro de texto sobre o setor: {"operator": "contains"|"starts_with"|"ends_with"|'
            '"not_equals", "value": str}.'
        ),
    )


@mcp.tool(
    name="opr_backlog_history",
    annotations={
        "title": "Série histórica de backlog",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def opr_backlog_history(params: BacklogHistoryInput) -> str:
    """Série histórica diária de backlog (ou backlog atrasado), lida de um snapshot capturado 1x
    por dia - só tem dado a partir do dia em que essa captura entrou em produção, sem
    retroatividade. Diferente das outras ferramentas, só quebra/filtra por regional, team_model,
    sector ou city (o snapshot já vem pré-agregado só por essas quatro dimensões).

    Args:
        params (BacklogHistoryInput): date_from, date_to, metric (backlog/backlog_atrasado),
            group_by (none/regional/team_model/sector/city, default none), sector_filter (opcional).

    Returns:
        str: JSON com lista [{"snapshot_date": "AAAA-MM-DD", "quantity": int, "group": str|null}, ...].

    Exemplos de uso:
        - "O backlog atrasado por cidade está subindo esse mês?" -> metric="backlog_atrasado",
          group_by="city"
    """
    payload = {
        "date_from": params.date_from,
        "date_to": params.date_to,
        "metric": params.metric,
        "group_by": params.group_by,
        "sector_filter": params.sector_filter,
    }
    return _call("backlog-history", payload)


class FilterOptionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: str = Field(..., description="Data inicial, formato AAAA-MM-DD.")
    date_to: str = Field(..., description="Data final, formato AAAA-MM-DD.")


@mcp.tool(
    name="opr_filter_options",
    annotations={
        "title": "Listar valores cadastrados para filtro",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def opr_filter_options(params: FilterOptionsInput) -> str:
    """Lista os valores realmente cadastrados no período (regionais, modelos de equipe, setores,
    assuntos, diagnósticos, responsáveis, status, status de SLA, prioridades etc.) - use antes de
    montar um filtro exato quando não tiver certeza da grafia correta de um valor.

    Args:
        params (FilterOptionsInput): date_from, date_to (AAAA-MM-DD).

    Returns:
        str: JSON com listas de valores por categoria (regionals, team_models, sectors, subjects,
        diagnoses, responsibles, statuses, sla_statuses, priorities, etc.).
    """
    return _call("filter-options", {"date_from": params.date_from, "date_to": params.date_to})


class WarrantyAnalyticsInput(DateRangeFilters):
    period_basis: str = Field(default="opened", description="opened ou closed - base temporal da consulta.")
    denominator: str = Field(
        default="active_origins",
        description="closed_origins, active_origins, maintenance_total ou activation_closed.",
    )
    origin_excluded_diagnoses: list[str] = Field(
        default_factory=list, description="Diagnósticos de origem a excluir (ex.: 'Desistência da solicitação')."
    )


@mcp.tool(
    name="opr_warranty_analytics",
    annotations={
        "title": "Análise de garantia de ativação",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def opr_warranty_analytics(params: WarrantyAnalyticsInput) -> str:
    """Garantia de ativação: uma Manutenção é garantia quando abre no mesmo contrato até 30 dias
    após o fechamento de uma Ativação/Mud. Endereço/Mud. Tecnologia elegível. Mesma conta da aba
    Garantias da tela de Operação.

    Args:
        params (WarrantyAnalyticsInput): date_from, date_to, period_basis (opened/closed, default
            opened), denominator (closed_origins/active_origins/maintenance_total/activation_closed,
            default active_origins), origin_excluded_diagnoses (opcional), filters (ver FILTERS_DOC).

    Returns:
        str: JSON com numerator, denominator_count, percentage, contracts_with_warranty,
        customers_with_warranty, breakdown por diversas dimensões (by_regional, by_diagnosis,
        by_subject, by_origin_type), items (lista plana de cada garantia encontrada) e
        items_truncated (bool, se a lista de items foi cortada por volume).
    """
    payload = {
        "date_from": params.date_from,
        "date_to": params.date_to,
        "period_basis": params.period_basis,
        "denominator": params.denominator,
        "origin_excluded_diagnoses": params.origin_excluded_diagnoses,
        "filters": params.filters,
    }
    return _call("warranty-analytics", payload)


class TeamTargetsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_date: str = Field(
        ..., description="Data de referência, formato AAAA-MM-DD - traz a meta VIGENTE nessa data, não a mais recente."
    )


@mcp.tool(
    name="opr_team_targets",
    annotations={
        "title": "Metas de equipe vigentes numa data",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def opr_team_targets(params: TeamTargetsInput) -> str:
    """Metas de equipe (por modelo e tipo de período: dia útil/sábado/domingo/mensal) vigentes
    numa data específica - não é a configuração atual, é a que valia naquele dia (histórico
    append-only).

    Args:
        params (TeamTargetsInput): reference_date (AAAA-MM-DD).

    Returns:
        str: JSON com lista [{"team_model": str, "period_type": str, "target_quantity": int,
        "median_from_quantity": int, "good_from_quantity": int, "valid_from": str,
        "valid_to": str|null}, ...].
    """
    return _call("team-targets", {"reference_date": params.reference_date})


class TeamTargetPerformanceInput(DateRangeFilters):
    granularity: str = Field(default="day", description="day, week ou month.")


@mcp.tool(
    name="opr_team_target_performance",
    annotations={
        "title": "Realizado x meta por modelo de equipe",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def opr_team_target_performance(params: TeamTargetPerformanceInput) -> str:
    """Produção realizada (O.S. fechadas) x meta prevista, por modelo de equipe - usa a meta que
    era vigente em cada período, não a de hoje. Só cobre modelos com produção real no período
    (não gera linha zerada para modelo sem nenhuma atividade).

    Args:
        params (TeamTargetPerformanceInput): date_from, date_to, granularity (day/week/month,
            default day), filters (ver FILTERS_DOC). Piloto do FilterContractV1
            (docs/proposta-filter-contract-v1.md): `os_subjects` é o nome canônico do filtro de
            assunto da O.S. - `subjects` continua funcionando (alias depreciado), só passa a
            gerar um aviso DEPRECATED_FILTER_ALIAS em `meta.warnings`.

    Returns:
        str: JSON {"meta": {...}, "data": [{"period_start": "AAAA-MM-DD", "team_model": str,
        "actual": int, "target": int|null, "delta": int|null,
        "percentage_of_target": float|null}, ...]}.
    """
    payload = {
        "date_from": params.date_from,
        "date_to": params.date_to,
        "granularity": params.granularity,
        "filters": params.filters,
    }
    return _call("team-target-performance", payload)


@mcp.tool(
    name="opr_list_fields",
    annotations={
        "title": "Listar campos disponíveis da O.S.",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
def opr_list_fields() -> str:
    """Lista todos os campos da tabela de Ordens de Serviço e mostra quais já estão expostos
    às ferramentas de IA (como dimensão de agrupamento, filtro exato ou filtro de texto) e quais
    ainda não estão - use quando um filtro/agrupamento que você esperava não existir, ou pra
    confirmar se um campo específico já é consultável antes de tentar usá-lo.

    Returns:
        str: JSON {"all_fields": [str, ...], "exposed_to_ai": [str, ...], "not_exposed": [str, ...]}.
    """
    try:
        return _dump(_get("fields"))
    except Exception as exc:  # noqa: BLE001
        return f"Erro: {exc}"


if __name__ == "__main__":
    mcp.run()
