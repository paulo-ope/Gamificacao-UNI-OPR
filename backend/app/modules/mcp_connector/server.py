"""Servidor MCP remoto (Streamable HTTP) da Operação Analítica - mesmas 10 ferramentas de
`mcp-server/opr_analitica_mcp.py` (o servidor local via stdio para Claude Code/Desktop), mas
chamando as funções de consulta do módulo `ai` DIRETO (mesmo processo, mesma sessão de banco),
sem dar a volta por HTTP - já estamos dentro do próprio backend.

A autenticação (quem está chamando) vem do OAuth (ver provider.py), não de uma chave de API fixa:
cada chamada de tool resolve o usuário autenticado a partir do access token via
`get_access_token()`/`resolve_user_for_access_token`, e as consultas aplicam o escopo regional
DESSE usuário (mesma regra de sempre - `effective_managed_regionals`), não um acesso irrestrito.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import permissions_for_user
from app.db.session import SessionLocal
from app.modules.ai import queries as ai_queries
from app.modules.ai.router import (
    resolve_ai_order_details_output_fields,
    resolve_ai_search_output_fields,
    validate_ai_search_fields,
)
from app.modules.ai.schemas import AiOrderFilters
from app.modules.ai_governance.field_registry import ENTITY_LOGIN_CURRENT_STATUS, ENTITY_ONU_SIGNAL_CURRENT, ENTITY_OPERATION_ORDERS
from app.modules.ai_governance.gate import enforce_ai_endpoint_for_user, enforce_date_field, enforce_filter_field, enforce_requested_fields
from app.modules.operations.coordinate_quality import coordinate_quality_audit
from app.modules.operations.login_aggregate import login_aggregate, login_incident_analysis, login_outages, login_timeseries
from app.modules.operations.login_geo_clusters import offline_login_clusters_response, query_login_status
from app.modules.operations.login_search import get_login_detail, search_logins
from app.modules.operations.onu_signal_snapshot import query_onu_signal_status
from app.modules.operations.queries import DATE_FIELD_COLUMNS, orders_by_identifiers
from app.modules.operations.schemas import OperationOrderDetailOut

from .provider import SCOPE, OprMcpOAuthProvider, resolve_user_for_access_token

FILTERS_DOC = """
Chaves aceitas em `filters` (todas opcionais; listas vazias/None = sem filtro):
- team_models, companies, regionals, states, cities, contract_types, person_types, os_types,
  subjects, diagnoses, departments, sectors, priorities, creators, responsibles, statuses,
  sla_statuses, projects, pops: list[str] - filtro exato (valor precisa bater igual).
- text_filters: list[{"field": ..., "operator": "contains"|"starts_with"|"ends_with"|"not_equals",
  "value": str}] - "field" aceita: sector, subject, diagnosis, responsible, city, department,
  service_description (descrição de abertura da O.S.), neighborhood (bairro).
- scheduled_after_sla, sla_expired_before_schedule: bool - indicadores de em que etapa o SLA foi
  perdido.
- has_coordinates: bool - só O.S. com (True) ou sem (False) latitude/longitude preenchidas.
- near_latitude, near_longitude, radius_km: float - só tem efeito com os três juntos; filtra O.S.
  dentro de `radius_km` quilômetros do ponto (near_latitude, near_longitude).
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


def _dump(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def _parse_date(value: str) -> date:
    """Converte a data (string AAAA-MM-DD vinda dos parâmetros da tool) pro tipo `date` que as
    funções de `ai.queries` esperam de verdade (elas fazem aritmética de data, ex.:
    `datetime.combine` em `local_period_utc_bounds` - passar string quebraria ali)."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Data inválida: '{value}' - use o formato AAAA-MM-DD.") from exc


def _parse_datetime(value: str) -> datetime:
    """Converte um datetime ISO8601 (com offset, ex. '2026-08-15T17:30:00-04:00') - aceita
    qualquer timezone de entrada, mesmo racional de `ai.schemas.DateTimeFilterOp`."""
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Datetime inválido: '{value}' - use ISO8601, ex. '2026-08-15T17:30:00-04:00'.") from exc


def _validated_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    """Valida `filters` contra o mesmo schema da rota HTTP (`AiOrderFilters`, `extra="forbid"`)
    antes de expandi-lo como kwargs pras funções de `ai.queries`. Achado real: sem isso, uma chave
    errada (ex.: "regional" no singular, em vez de "regionals") não dava erro nenhum - as funções
    de consulta recebem `**filters` livre e só reconhecem os nomes exatos de `FILTER_COLUMNS`, então
    a chave errada era descartada em silêncio, dando a impressão de que o filtro "não funcionava".
    A rota HTTP (`ai/router.py`) já passa por esse mesmo schema e sempre teria pego isso com 422."""
    try:
        return AiOrderFilters.model_validate(filters or {}).model_dump()
    except ValidationError as exc:
        raise ValueError(f"filters inválido: {exc}") from exc


def _enforce(callable_, *args, **kwargs):
    """Chama uma função de `ai_governance.gate` (que levanta `HTTPException`, pensada pra FastAPI)
    convertendo em `ValueError` - mesma família de erro que o resto deste arquivo já usa pra
    validação (`_parse_date`/`_validated_filters`), que vira mensagem de erro legível pro Claude em
    vez de um `HTTPException` com status_code/detail que não faz sentido fora de uma resposta HTTP."""
    from fastapi import HTTPException

    try:
        return callable_(*args, **kwargs)
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from exc


def _current_user():
    """Resolve o usuário autenticado da chamada de tool atual a partir do access token OAuth -
    lança um erro claro (viraria mensagem de erro pro Claude) se não houver token válido, em vez de
    deixar uma exceção de atributo confusa estourar mais adiante."""
    access_token = get_access_token()
    if access_token is None:
        raise RuntimeError("Nenhum token de acesso encontrado nesta chamada - a conexão OAuth pode ter expirado.")
    user = resolve_user_for_access_token(access_token)
    if user is None:
        raise RuntimeError("Usuário do token não encontrado ou inativo - reconecte esta integração no Claude.")
    return user


def build_mcp_server() -> FastMCP:
    settings = get_settings()
    if not settings.public_base_url:
        raise RuntimeError("PUBLIC_BASE_URL não configurada - necessária para o conector MCP remoto.")
    base = settings.public_base_url.rstrip("/")
    issuer_url = f"{base}{settings.api_prefix}/mcp"
    resource_server_url = f"{issuer_url}/mcp"

    # A proteção de DNS rebinding do SDK do MCP (TransportSecurityMiddleware) rejeita com 421
    # qualquer `Host` fora da lista permitida - por padrão só localhost/127.0.0.1. Sem isto, TODA
    # chamada de tool (POST /mcp) do domínio real de produção falha, mesmo com o OAuth já
    # completo (achado real: consentimento e token funcionaram, só a chamada MCP em si quebrava).
    public_host = urlparse(base).netloc

    mcp = FastMCP(
        "opr_analitica_mcp_remote",
        auth_server_provider=OprMcpOAuthProvider(),
        auth=AuthSettings(
            issuer_url=issuer_url,
            resource_server_url=resource_server_url,
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]
            ),
            revocation_options=RevocationOptions(enabled=True),
            required_scopes=[SCOPE],
        ),
        transport_security=TransportSecuritySettings(
            allowed_hosts=[public_host, "localhost", "127.0.0.1"],
            allowed_origins=[base, "http://localhost", "http://127.0.0.1"],
        ),
    )

    @mcp.tool(
        name="opr_aggregate_orders",
        annotations={"title": "Agregar O.S. por dimensão", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_aggregate_orders(
        date_from: str, date_to: str, group_by: str | list[str], metric: str, filters: dict[str, Any] | None = None
    ) -> str:
        """Agrupa Ordens de Serviço por uma dimensão (ou até 3 combinadas) e calcula uma métrica
        por grupo - "concentração de X por Y" (backlog por bairro, O.S. por assunto, taxa de SLA
        por regional, horas médias de execução por modelo de equipe).

        Args:
            date_from, date_to: AAAA-MM-DD.
            group_by: uma dimensão ou lista de até 3. """ + GROUP_BY_DOC + """
            metric: quantidade_aberta, quantidade_fechada, taxa_sla, horas_medias,
                quantidade_atrasada, quantidade_backlog, horas_abertura_agenda,
                horas_agenda_execucao, horas_execucao_fechamento, horas_abertura_fechamento.
            filters: """ + FILTERS_DOC + """

        Returns:
            JSON com lista de grupos: [{"label": str, "quantity": int, "metric_value": float,
            "percentage": float}, ...] (ou uma chave por dimensão em vez de "label", com 2-3
            dimensões), ordenado por quantidade decrescente.
        """
        user = _current_user()
        with SessionLocal() as db:
            return _dump(
                ai_queries.aggregate_orders(
                    db, user, group_by=group_by, metric=metric,
                    date_from=_parse_date(date_from), date_to=_parse_date(date_to), **_validated_filters(filters),
                )
            )

    @mcp.tool(
        name="opr_orders_timeseries",
        annotations={"title": "Série temporal de O.S.", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_orders_timeseries(
        date_from: str,
        date_to: str,
        metric: str,
        granularity: str = "day",
        group_by: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> str:
        """Série temporal (dia/semana/mês) de O.S. abertas, fechadas, ou o saldo entre as duas,
        opcionalmente quebrada por uma dimensão.

        Args:
            date_from, date_to: AAAA-MM-DD.
            metric: abertas, fechadas ou saldo.
            granularity: day, week ou month.
            group_by: dimensão opcional. """ + GROUP_BY_DOC + """
            filters: """ + FILTERS_DOC + """

        Returns:
            JSON com lista de pontos [{"period_start": "AAAA-MM-DD", "quantity": int,
            "group": str|null}, ...].
        """
        user = _current_user()
        with SessionLocal() as db:
            return _dump(
                ai_queries.orders_timeseries(
                    db, user, metric=metric, granularity=granularity,
                    date_from=_parse_date(date_from), date_to=_parse_date(date_to),
                    group_by=group_by, **_validated_filters(filters),
                )
            )

    @mcp.tool(
        name="opr_search_orders",
        annotations={"title": "Buscar O.S. individuais", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_search_orders(
        date_from: str,
        date_to: str,
        page: int = 1,
        page_size: int = 50,
        keyword: str | None = None,
        filters: dict[str, Any] | None = None,
        date_field: str | None = None,
        fields: list[str] | None = None,
        response_mode: str = "full",
    ) -> str:
        """Busca paginada de O.S. individuais, com texto qualitativo (descrição de abertura,
        relato técnico) e todos os campos de SLA/tempo já calculados.

        IMPORTANTE sobre date_from/date_to: por padrão (date_field=None), uma O.S. entra no
        resultado se teve QUALQUER atividade no período - abriu OU fechou dentro de [date_from,
        date_to] (união, não intersecção). Passe `date_field` para filtrar por um único marco
        específico em vez dessa regra (ex.: "closed_at" para só O.S. FECHADAS no período - nunca
        use opened_at como substituto de closed_at).

        Args:
            date_from, date_to: AAAA-MM-DD.
            page: página (1-indexado).
            page_size: itens por página (10-200).
            keyword: busca livre opcional.
            filters: """ + FILTERS_DOC + """ (inclui o filtro geográfico de raio, útil para "O.S.
                perto deste ponto/desta O.S.").
            date_field: opened_at, closed_at, scheduled_at, assumed_at, displacement_started_at,
                execution_started_at, finished_at ou deadline_at - default (None) mantém a regra
                "abriu OU fechou no período" acima.
            fields: subconjunto de campos a retornar (nomes iguais aos do item de resposta, ver
                Returns) - rejeitado explicitamente se algum nome não existir ou não estiver
                autorizado para este perfil, nunca omitido em silêncio.
            response_mode: "full" (default, todos os campos autorizados) ou "summary" (poucos
                campos, para triagem antes de pedir detalhe de uma O.S. específica).

        Returns:
            JSON {"items": [...], "total_encontrado": int, "page": int, "page_size": int,
            "has_more": bool}. Cada item inclui order_code, regional, city, neighborhood, sector,
            latitude, longitude, distance_km (só com filtro de raio), service_description,
            technical_report, service_address, datas do ciclo de vida, indicadores de etapa de
            SLA e a meta de equipe vigente na O.S. - recortado por `fields`/`response_mode` quando
            informados.
        """
        user = _current_user()
        with SessionLocal() as db:
            policy = _enforce(enforce_ai_endpoint_for_user, db, user, "ai.search_orders", "mcp")
            resolved_date_field = _enforce(enforce_date_field, policy, ENTITY_OPERATION_ORDERS, date_field, DATE_FIELD_COLUMNS)
            validated_fields = _enforce(validate_ai_search_fields, policy, fields)
            output_fields = resolve_ai_search_output_fields(policy, response_mode, validated_fields)
            return _dump(
                ai_queries.search_orders(
                    db, user, date_from=_parse_date(date_from), date_to=_parse_date(date_to),
                    page=page, page_size=min(page_size, 200), keyword=keyword,
                    date_field=resolved_date_field, fields=output_fields, **_validated_filters(filters),
                )
            )

    @mcp.tool(
        name="opr_order_details",
        annotations={"title": "Detalhe de O.S. por order_code/OS_ID", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_order_details(
        order_codes: list[str] | None = None,
        source_order_ids: list[str] | None = None,
        fields: list[str] | None = None,
        response_mode: str = "full",
    ) -> str:
        """Detalhe de uma ou várias O.S. por `order_code` e/ou `source_order_id` (OS_ID) - use
        quando já se sabe qual(is) O.S. se quer (ex.: após uma triagem com opr_search_orders em
        response_mode="summary"), em vez de `opr_search_orders` com filtro/keyword. Não exige
        período: quem já sabe qual O.S. quer não precisa também acertar a data de abertura/fechamento.

        Args:
            order_codes: lista de order_code (ex.: "IXC-12345"). Até 50 por chamada.
            source_order_ids: lista de OS_ID bruto do IXC. Até 50 por chamada.
                Informe pelo menos um de order_codes/source_order_ids.
            fields: subconjunto de campos a retornar - rejeitado explicitamente se algum nome não
                existir ou não estiver autorizado para este perfil.
            response_mode: "full" (default, todos os detalhes autorizados, incluindo o relato
                técnico/descrição de abertura) ou "summary" (poucos campos).

        Returns:
            JSON {"items": [...], "not_found_order_codes": [...], "not_found_source_order_ids": [...]}.
            Um order_code/source_order_id que não aparece em nenhuma das duas listas de resultado
            foi encontrado normalmente (está em algum item de "items").
        """
        if not order_codes and not source_order_ids:
            raise ValueError("Informe ao menos um order_code ou source_order_id (OS_ID).")
        user = _current_user()
        with SessionLocal() as db:
            policy = _enforce(enforce_ai_endpoint_for_user, db, user, "ai.order_details", "mcp")
            validated_fields = _enforce(enforce_requested_fields, policy, ENTITY_OPERATION_ORDERS, fields, "detail_available")
            output_fields = resolve_ai_order_details_output_fields(policy, response_mode, validated_fields)

            orders = orders_by_identifiers(
                db, user, order_codes=order_codes or [], source_order_ids=source_order_ids or []
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

            return _dump(
                {
                    "items": items,
                    "not_found_order_codes": sorted(set(order_codes or []) - found_order_codes),
                    "not_found_source_order_ids": sorted(set(source_order_ids or []) - found_source_order_ids),
                }
            )

    @mcp.tool(
        name="opr_login_status",
        annotations={"title": "Status de conectividade de login", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_login_status(
        logins: list[str] | None = None,
        online_statuses: list[str] | None = None,
        regionals: list[str] | None = None,
        near_latitude: float | None = None,
        near_longitude: float | None = None,
        radius_km: float | None = None,
        limit: int = 200,
    ) -> str:
        """Status ATUAL de conectividade por login - não é um evento de queda, é o estado agora e
        há quanto tempo está nesse estado. Use para "quais logins estão desconectados perto deste
        ponto/nesta regional" ou "há quanto tempo esse login caiu".

        Args:
            logins: lista de login (ex.: "cliente.teste"). Vazio = sem filtro por login.
            online_statuses: filtra pelo status bruto do IXC - "S" (conectado), "N"
                (desconectado - sinal real de queda recente), "SS" (conectado sem sinal,
                característica crônica de equipamento/login, não é queda recente).
            regionals: filtra pela regional (ex.: "UNI - MACHADINHO DOESTE") - mesma normalização
                usada nas O.S. (radusuarios.id_filial).
            near_latitude, near_longitude, radius_km: busca geográfica por raio - os três juntos,
                ou nenhum.
            limit: até 500 (default 200).

        Returns:
            JSON com lista de {"login_id", "login", "online", "regional", "latitude", "longitude",
            "last_connected_at", "last_disconnected_at", "status_changed_at", "captured_at"}.
            `status_changed_at` só avança quando `online` muda de valor - é o campo certo para
            "quando começou esse estado", não `captured_at` (última vez que o sistema viu o login).
        """
        if (near_latitude is None) != (near_longitude is None) or (radius_km is not None and near_latitude is None):
            raise ValueError("Informe near_latitude, near_longitude e radius_km juntos, ou nenhum dos três.")
        user = _current_user()
        with SessionLocal() as db:
            policy = _enforce(enforce_ai_endpoint_for_user, db, user, "operations.network.logins", "mcp")
            if logins:
                _enforce(enforce_filter_field, policy, ENTITY_LOGIN_CURRENT_STATUS, "login", "filterable")
            if online_statuses:
                _enforce(enforce_filter_field, policy, ENTITY_LOGIN_CURRENT_STATUS, "online", "filterable")
            if regionals:
                _enforce(enforce_filter_field, policy, ENTITY_LOGIN_CURRENT_STATUS, "regional", "filterable")
            if near_latitude is not None:
                _enforce(enforce_filter_field, policy, ENTITY_LOGIN_CURRENT_STATUS, "latitude", "filterable")
                _enforce(enforce_filter_field, policy, ENTITY_LOGIN_CURRENT_STATUS, "longitude", "filterable")
            rows = query_login_status(
                db,
                logins=logins or [],
                online_statuses=online_statuses or [],
                regionals=regionals or [],
                near_latitude=near_latitude,
                near_longitude=near_longitude,
                radius_km=radius_km,
                limit=limit,
            )
            return _dump(
                [
                    {
                        "login_id": row.login_id,
                        "login": row.login,
                        "online": row.online,
                        "regional": row.regional,
                        "latitude": row.latitude,
                        "longitude": row.longitude,
                        "last_connected_at": row.last_connected_at,
                        "last_disconnected_at": row.last_disconnected_at,
                        "status_changed_at": row.status_changed_at,
                        "captured_at": row.captured_at,
                    }
                    for row in rows
                ]
            )

    @mcp.tool(
        name="opr_onu_signal",
        annotations={"title": "Telemetria óptica/ONU e PON", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_onu_signal(
        login_ids: list[int] | None = None,
        last_drop_causes: list[str] | None = None,
        transmitter_ids: list[str] | None = None,
        limit: int = 200,
    ) -> str:
        """Telemetria óptica/ONU (sinal RX/TX em dBm, causa da última queda, transmissor/OLT,
        PON/slot) dos logins já monitorados por opr_login_status. Não cobre a base inteira de ONUs
        do IXC (~90 mil) - só os logins que o sistema já acompanha, para não sobrecarregar a API
        deles.

        Args:
            login_ids: lista de login_id. Vazio = sem filtro.
            last_drop_causes: filtra pela causa da última queda registrada na ONU (ex.: "Link
                Loss", "Power Fail" - os valores existentes variam conforme o hardware).
            transmitter_ids: filtra por id do transmissor/OLT.
            limit: até 500 (default 200).

        Returns:
            JSON com lista de {"login_id", "login", "contract_id", "signal_rx_dbm",
            "signal_tx_dbm", "last_drop_cause", "onu_serial", "onu_model", "transmitter_id",
            "temperature_c", "voltage", "signal_measured_at", "pon_id", "pon_no", "slot_no",
            "latitude", "longitude", "captured_at"}.
        """
        user = _current_user()
        with SessionLocal() as db:
            policy = _enforce(enforce_ai_endpoint_for_user, db, user, "operations.network.onu_signal", "mcp")
            if login_ids:
                _enforce(enforce_filter_field, policy, ENTITY_ONU_SIGNAL_CURRENT, "login_id", "filterable")
            if last_drop_causes:
                _enforce(enforce_filter_field, policy, ENTITY_ONU_SIGNAL_CURRENT, "last_drop_cause", "filterable")
            if transmitter_ids:
                _enforce(enforce_filter_field, policy, ENTITY_ONU_SIGNAL_CURRENT, "transmitter_id", "filterable")
            return _dump(
                query_onu_signal_status(
                    db,
                    login_ids=login_ids or [],
                    last_drop_causes=last_drop_causes or [],
                    transmitter_ids=transmitter_ids or [],
                    limit=limit,
                )
            )

    @mcp.tool(
        name="opr_search_logins",
        annotations={"title": "Buscar logins (paginado)", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_search_logins(
        logins: list[str] | None = None,
        login_query: str | None = None,
        login_ids: list[int] | None = None,
        online_statuses: list[str] | None = None,
        regionals: list[str] | None = None,
        pon_ids: list[str] | None = None,
        transmitter_ids: list[str] | None = None,
        contract_ids: list[str] | None = None,
        near_latitude: float | None = None,
        near_longitude: float | None = None,
        radius_km: float | None = None,
        status_changed_at: dict[str, str] | None = None,
        last_connected_at: dict[str, str] | None = None,
        last_disconnected_at: dict[str, str] | None = None,
        captured_at: dict[str, str] | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> str:
        """Busca paginada de login - equivalente de opr_search_orders para logins. Use para
        "pesquise o login X", "quais logins estão desconectados na regional Y", "quais logins
        caíram nos últimos N minutos", "quais logins estão numa PON/transmissor específico".

        Args:
            logins: lista de login exato. login_query: busca parcial (contém).
            login_ids, online_statuses ("S"/"N"/"SS"), regionals: filtros exatos.
            pon_ids, transmitter_ids, contract_ids: filtram pela telemetria ONU (join) - só logins
                com telemetria capturada aparecem quando usados.
            near_latitude, near_longitude, radius_km: busca geográfica por raio - os três juntos.
            status_changed_at, last_connected_at, last_disconnected_at, captured_at:
                {"gte"/"gt"/"lte"/"lt"/"eq": "AAAA-MM-DDTHH:MM:SS±HH:MM"} - ex.: "caiu nos últimos
                60 minutos" = last_disconnected_at={"gte": "<agora-60min>"}.
            page, page_size: paginação real (até 500 por página).

        Returns:
            JSON {"items": [...], "total_encontrado": int, "page": int, "page_size": int,
            "has_more": bool, "meta": {...}}. Cada item inclui login_id, login, online, regional,
            latitude/longitude, last_connected_at, last_disconnected_at, status_changed_at,
            captured_at, contract_id, pon_id, transmitter_id, last_drop_cause.
        """
        if (near_latitude is None) != (near_longitude is None) or (radius_km is not None and near_latitude is None):
            raise ValueError("Informe near_latitude, near_longitude e radius_km juntos, ou nenhum dos três.")
        user = _current_user()
        with SessionLocal() as db:
            policy = _enforce(enforce_ai_endpoint_for_user, db, user, "ai.search_logins", "mcp")
            if logins or login_query:
                _enforce(enforce_filter_field, policy, ENTITY_LOGIN_CURRENT_STATUS, "login", "filterable")
            if online_statuses:
                _enforce(enforce_filter_field, policy, ENTITY_LOGIN_CURRENT_STATUS, "online", "filterable")
            if regionals:
                _enforce(enforce_filter_field, policy, ENTITY_LOGIN_CURRENT_STATUS, "regional", "filterable")
            if pon_ids:
                _enforce(enforce_filter_field, policy, ENTITY_ONU_SIGNAL_CURRENT, "pon_id", "filterable")
            if transmitter_ids:
                _enforce(enforce_filter_field, policy, ENTITY_ONU_SIGNAL_CURRENT, "transmitter_id", "filterable")
            if contract_ids:
                _enforce(enforce_filter_field, policy, ENTITY_ONU_SIGNAL_CURRENT, "contract_id", "filterable")
            return _dump(
                search_logins(
                    db,
                    logins=logins or [],
                    login_query=login_query,
                    login_ids=login_ids or [],
                    online_statuses=online_statuses or [],
                    regionals=regionals or [],
                    pon_ids=pon_ids or [],
                    transmitter_ids=transmitter_ids or [],
                    contract_ids=contract_ids or [],
                    near_latitude=near_latitude,
                    near_longitude=near_longitude,
                    radius_km=radius_km,
                    status_changed_at=status_changed_at,
                    last_connected_at=last_connected_at,
                    last_disconnected_at=last_disconnected_at,
                    captured_at=captured_at,
                    page=page,
                    page_size=page_size,
                )
            )

    @mcp.tool(
        name="opr_get_login_detail",
        annotations={"title": "Detalhe completo de um login", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_get_login_detail(login: str | None = None, login_id: int | None = None, history_hours: int = 24) -> str:
        """Detalhamento completo de um login - identificação, status de conexão com tempo já
        calculado no estado atual (ex.: "offline há 47 minutos"), telemetria ONU/PON e histórico
        recente de eventos de conexão/desconexão. Use depois de achar o login via
        opr_search_logins/opr_login_status, quando precisar de TODOS os detalhes de um único login.

        Args:
            login ou login_id: pelo menos um dos dois.
            history_hours: janela do histórico de eventos recentes (1 a 168, default 24).

        Returns:
            JSON com identificação, status (`seconds_in_current_state` já calculado), telemetria
            ONU/PON (`onu_serial`, `signal_rx_dbm`, `signal_tx_dbm`, `last_drop_cause`,
            `transmitter_id`, `pon_id`, `pon_no`, `slot_no`) e `recent_events`: lista de
            {"event": "connected"|"disconnected", "at": timestamp} reconstruída do histórico real
            (horário exato registrado pelo IXC, não o intervalo de captura).
        """
        if login is None and login_id is None:
            raise ValueError("Informe login ou login_id.")
        user = _current_user()
        with SessionLocal() as db:
            _enforce(enforce_ai_endpoint_for_user, db, user, "ai.login_detail", "mcp")
            detail = get_login_detail(db, login=login, login_id=login_id, history_hours=history_hours)
            if detail is None:
                raise ValueError(f"Login não encontrado: {login or login_id}")
            return _dump(detail)

    @mcp.tool(
        name="opr_login_aggregate",
        annotations={"title": "Agregar logins por dimensão", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_login_aggregate(
        group_by: str, regionals: list[str] | None = None, online_statuses: list[str] | None = None
    ) -> str:
        """Contagem de logins por dimensão - "quantos offline por regional", "quantos por PON",
        "quantos por transmissor/OLT", "quantos por causa de queda". Use para detectar concentração
        (incidente coletivo) sem baixar registro por registro.

        Args:
            group_by: regional, online, transmitter_id, pon_id ou last_drop_cause. Valor inválido
                levanta erro explícito - nunca cai silenciosamente em outra dimensão.
            regionals, online_statuses: filtros opcionais antes de agregar.

        Returns:
            JSON {"meta": {...}, "data": [{"label": str, "quantity": int, "percentage": float}, ...]},
            `data` ordenado por quantidade decrescente. `meta.applied_filters` mostra o que de fato
            foi usado; `meta.source_last_sync` indica há quanto tempo o snapshot de login é real.
        """
        user = _current_user()
        with SessionLocal() as db:
            _enforce(enforce_ai_endpoint_for_user, db, user, "ai.login_aggregate", "mcp")
            try:
                return _dump(login_aggregate(db, group_by=group_by, regionals=regionals or [], online_statuses=online_statuses or []))
            except ValueError as exc:
                raise ValueError(str(exc)) from exc

    @mcp.tool(
        name="opr_login_outages",
        annotations={"title": "Quedas de login por período", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_login_outages(since: str, until: str | None = None, regionals: list[str] | None = None, limit: int = 200) -> str:
        """Logins que estão OFFLINE agora e caíram dentro de [since, until] - candidatos a
        incidente coletivo quando concentrados na mesma regional. Não pega quedas que já
        reconectaram (para isso, use opr_get_login_detail no login específico).

        Args:
            since: início da janela, ISO8601 (ex.: "2026-08-15T17:00:00-04:00").
            until: fim da janela - default agora.
            regionals: filtro opcional.
            limit: até 1000 (default 200).

        Returns:
            JSON {"meta": {...}, "data": [{"login_id", "login", "regional", "latitude",
            "longitude", "status_changed_at", "last_disconnected_at"}, ...]}, `data` mais recente
            primeiro. `meta.warnings` avisa se o resultado foi truncado pelo teto do endpoint.
        """
        user = _current_user()
        with SessionLocal() as db:
            _enforce(enforce_ai_endpoint_for_user, db, user, "ai.login_outages", "mcp")
            return _dump(
                login_outages(
                    db, since=_parse_datetime(since), until=_parse_datetime(until) if until else None,
                    regionals=regionals or [], limit=limit,
                )
            )

    @mcp.tool(
        name="opr_login_timeseries",
        annotations={"title": "Série temporal de conectividade", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_login_timeseries(since: str, until: str | None = None) -> str:
        """Série temporal de conectados/desconectados/quedas novas/reconexões novas - um ponto por
        captura real do snapshot periódico (a cada ~5-15min em produção, não bucket fixo). Use para
        ver a curva de quedas ao longo do tempo (ex.: "17:00 → 15 desconectados, 17:15 → 47" indica
        incidente coletivo em andamento).

        Args:
            since: início da janela, ISO8601.
            until: fim da janela - default agora.

        Returns:
            JSON {"meta": {...}, "data": [{"captured_at", "connected", "disconnected", "new_drops",
            "new_reconnects"}, ...]}, `data` em ordem cronológica. `new_drops`/`new_reconnects`
            contam só transições NESTA captura (comparado com a captura anterior do mesmo login) -
            o primeiro ponto da série pode superestimar se não houver captura anterior próxima o
            bastante (~20min) para comparar.
        """
        user = _current_user()
        with SessionLocal() as db:
            _enforce(enforce_ai_endpoint_for_user, db, user, "ai.login_timeseries", "mcp")
            return _dump(login_timeseries(db, since=_parse_datetime(since), until=_parse_datetime(until) if until else None))

    @mcp.tool(
        name="opr_offline_login_clusters",
        annotations={"title": "Clusters geográficos de queda de login", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_offline_login_clusters(
        radius_meters: float = 300.0, min_cluster_size: int = 3, window_minutes: int = 30
    ) -> str:
        """Agrupa logins que caíram nos últimos `window_minutes` e estão geograficamente próximos -
        candidato a rompimento de fibra num trecho (distinto de uma queda isolada de um único
        cliente). Já faz o agrupamento espacial no backend (DBSCAN sobre grade), em vez de você
        baixar `opr_login_status`/`opr_login_outages` e agrupar manualmente. Só considera
        proximidade e tempo de desconexão - não filtra por regional/setor/assunto de O.S.

        Args:
            radius_meters: raio de vizinhança entre dois logins pra contarem como próximos
                (10-5000, default 300).
            min_cluster_size: mínimo de logins vizinhos pra formar um cluster (2-100, default 3).
            window_minutes: janela de detecção - só considera quedas dentro desse intervalo (5-1440,
                default 30).

        Returns:
            JSON {"radius_meters", "min_cluster_size", "window_minutes", "clusters": [{
            "center_latitude", "center_longitude", "radius_meters", "size", "logins": [{"login_id",
            "login", "online", "latitude", "longitude", "last_disconnected_at"}, ...]}, ...],
            "meta": {...}}, `clusters` ordenado do maior pro menor.
        """
        user = _current_user()
        with SessionLocal() as db:
            _enforce(enforce_ai_endpoint_for_user, db, user, "ai.offline_login_clusters", "mcp")
            return _dump(
                offline_login_clusters_response(
                    db, radius_meters=radius_meters, min_cluster_size=min_cluster_size, window_minutes=window_minutes
                )
            )

    @mcp.tool(
        name="opr_login_incident_analysis",
        annotations={"title": "Funil de incidente coletivo", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_login_incident_analysis(
        window_minutes: int = 90,
        regionals: list[str] | None = None,
        cluster_radius_meters: float = 300.0,
        cluster_min_size: int = 3,
    ) -> str:
        """Funil de incidente coletivo numa única chamada - quedas novas, ainda offline,
        reconexões, quebra por regional/transmissor/PON/causa de queda e clusters geográficos, já
        agregados no backend. Use esta tool PRIMEIRO ao investigar um possível incidente (evita
        várias chamadas separadas de opr_login_outages/opr_login_aggregate/opr_login_timeseries).

        Args:
            window_minutes: janela de análise (5 a 1440, default 90).
            regionals: filtro opcional - não se aplica aos geo_clusters de propósito (um
                rompimento físico pode atravessar fronteira administrativa de regional).
            cluster_radius_meters, cluster_min_size: parâmetros do agrupamento geográfico (default
                300m, mínimo 3 logins).

        Returns:
            JSON {"window_minutes", "since", "new_drops", "still_offline", "reconnects",
            "by_regional", "by_transmitter", "by_pon", "by_drop_cause": [{"label", "quantity",
            "percentage"}, ...], "geo_clusters": [{"center_latitude", "center_longitude",
            "radius_meters", "size", "logins": [...]}, ...], "meta": {...}}.
        """
        user = _current_user()
        with SessionLocal() as db:
            _enforce(enforce_ai_endpoint_for_user, db, user, "ai.login_incident_analysis", "mcp")
            return _dump(
                login_incident_analysis(
                    db, window_minutes=window_minutes, regionals=regionals or [],
                    cluster_radius_meters=cluster_radius_meters, cluster_min_size=cluster_min_size,
                )
            )

    @mcp.tool(
        name="opr_coordinate_quality_audit",
        annotations={"title": "Auditoria de qualidade de coordenadas", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_coordinate_quality_audit(
        entity: str, outlier_km: float = 300.0, duplicate_threshold: int = 20
    ) -> str:
        """Auditoria de qualidade de latitude/longitude, quebrada por regional - SÓ classifica e
        conta, nenhuma correção automática. Use ANTES de confiar em qualquer cluster geográfico
        (opr_offline_login_clusters, opr_login_incident_analysis) - coordenada ruim produz cluster
        sofisticado e errado sem nenhum aviso.

        Args:
            entity: operations_orders, operations_login_current_status ou
                operations_onu_signal_current.
            outlier_km: distância do centróide dos próprios registros válidos da regional acima da
                qual uma coordenada (dentro do intervalo geográfico possível) é considerada fora de
                lugar (default 300km).
            duplicate_threshold: quantos registros compartilhando a mesma coordenada exata (~1m)
                fazem ela ser "suspeita de valor chumbado" (default 20).

        Returns:
            JSON {"meta": {...}, "data": [{"entity", "regional", "total", "validated", "missing",
            "invalid_range", "zero_zero", "outside_region", "suspicious_duplicates",
            "valid_coverage_pct"}, ...]}, um item de `data` por regional. `validated` = passou
            todas as checagens; os demais campos são mutuamente exclusivos entre si e com
            `validated`.
        """
        user = _current_user()
        with SessionLocal() as db:
            _enforce(enforce_ai_endpoint_for_user, db, user, "ai.coordinate_quality", "mcp")
            try:
                return _dump(
                    coordinate_quality_audit(db, entity=entity, outlier_km=outlier_km, duplicate_threshold=duplicate_threshold)
                )
            except ValueError as exc:
                raise ValueError(str(exc)) from exc

    @mcp.tool(
        name="opr_backlog_aging",
        annotations={"title": "Idade do backlog por dimensão", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_backlog_aging(date_to: str, group_by: str = "regional", filters: dict[str, Any] | None = None) -> str:
        """Idade do backlog (O.S. ainda abertas em date_to) por dimensão: quantidade, idade média
        e mediana em dias, a O.S. mais antiga, e quantas passam de 1/3/5/7/15 dias.

        Args:
            date_to: AAAA-MM-DD.
            group_by: uma dimensão, default "regional". """ + GROUP_BY_DOC + """
            filters: """ + FILTERS_DOC + """

        Returns:
            JSON com lista [{"label": str, "quantity": int, "avg_age_days": float,
            "median_age_days": float, "oldest_order_code": str, "oldest_age_days": float,
            "over_1d"/"over_3d"/"over_5d"/"over_7d"/"over_15d": int}, ...].
        """
        user = _current_user()
        with SessionLocal() as db:
            return _dump(ai_queries.backlog_aging(db, user, group_by=group_by, date_to=_parse_date(date_to), **_validated_filters(filters)))

    @mcp.tool(
        name="opr_backlog_history",
        annotations={"title": "Série histórica de backlog", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_backlog_history(
        date_from: str, date_to: str, metric: str, group_by: str = "none", sector_filter: dict[str, str] | None = None
    ) -> str:
        """Série histórica diária de backlog (ou backlog atrasado), lida de um snapshot capturado
        1x por dia - só tem dado a partir do dia em que essa captura entrou em produção. Diferente
        das outras ferramentas, só quebra/filtra por regional, team_model, sector ou city.

        Args:
            date_from, date_to: AAAA-MM-DD.
            metric: backlog ou backlog_atrasado.
            group_by: none, regional, team_model, sector ou city.
            sector_filter: opcional, {"operator": "contains"|"starts_with"|"ends_with"|
                "not_equals", "value": str}.

        Returns:
            JSON com lista [{"snapshot_date": "AAAA-MM-DD", "quantity": int, "group": str|null}, ...].
        """
        user = _current_user()
        with SessionLocal() as db:
            return _dump(
                ai_queries.backlog_history(
                    db, user, metric=metric, date_from=_parse_date(date_from), date_to=_parse_date(date_to),
                    group_by=group_by, sector_filter=sector_filter,
                )
            )

    @mcp.tool(
        name="opr_filter_options",
        annotations={"title": "Listar valores cadastrados para filtro", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_filter_options(date_from: str, date_to: str) -> str:
        """Lista os valores realmente cadastrados no período (regionais, modelos de equipe,
        setores, assuntos, diagnósticos, responsáveis, status etc.) - use antes de montar um
        filtro exato quando não tiver certeza da grafia correta de um valor.

        Args:
            date_from, date_to: AAAA-MM-DD.

        Returns:
            JSON com listas de valores por categoria.
        """
        user = _current_user()
        with SessionLocal() as db:
            return _dump(ai_queries.filter_options_for_ai(db, user, _parse_date(date_from), _parse_date(date_to)))

    @mcp.tool(
        name="opr_warranty_analytics",
        annotations={"title": "Análise de garantia de ativação", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_warranty_analytics(
        date_from: str,
        date_to: str,
        period_basis: str = "opened",
        denominator: str = "active_origins",
        origin_excluded_diagnoses: list[str] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> str:
        """Garantia de ativação: uma Manutenção é garantia quando abre no mesmo contrato até 30
        dias após o fechamento de uma Ativação/Mud. Endereço/Mud. Tecnologia elegível.

        Args:
            date_from, date_to: AAAA-MM-DD.
            period_basis: opened ou closed.
            denominator: closed_origins, active_origins, maintenance_total ou activation_closed.
            origin_excluded_diagnoses: diagnósticos de origem a excluir, opcional.
            filters: """ + FILTERS_DOC + """

        Returns:
            JSON com numerator, denominator_count, percentage, contracts_with_warranty,
            customers_with_warranty, breakdown por dimensão, items e items_truncated.
        """
        user = _current_user()
        with SessionLocal() as db:
            return _dump(
                ai_queries.warranty_analytics_for_ai(
                    db, user, date_from=_parse_date(date_from), date_to=_parse_date(date_to), period_basis=period_basis,
                    denominator=denominator, origin_excluded_diagnoses=origin_excluded_diagnoses or [], **_validated_filters(filters),
                )
            )

    @mcp.tool(
        name="opr_team_targets",
        annotations={"title": "Metas de equipe vigentes numa data", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_team_targets(reference_date: str) -> str:
        """Metas de equipe (por modelo e tipo de período) vigentes numa data específica - não é a
        configuração atual, é a que valia naquele dia (histórico append-only).

        Args:
            reference_date: AAAA-MM-DD.

        Returns:
            JSON com lista de metas por modelo/tipo de período.
        """
        _current_user()  # exige autenticação, mesmo não sendo escopado por usuário
        with SessionLocal() as db:
            return _dump(ai_queries.team_targets_for_ai(db, _parse_date(reference_date)))

    @mcp.tool(
        name="opr_team_target_performance",
        annotations={"title": "Realizado x meta por modelo de equipe", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_team_target_performance(
        date_from: str, date_to: str, granularity: str = "day", filters: dict[str, Any] | None = None
    ) -> str:
        """Produção realizada (O.S. fechadas) x meta prevista, por modelo de equipe - usa a meta
        que era vigente em cada período, não a de hoje.

        Args:
            date_from, date_to: AAAA-MM-DD.
            granularity: day, week ou month.
            filters: """ + FILTERS_DOC + """

        Returns:
            JSON com lista [{"period_start": "AAAA-MM-DD", "team_model": str, "actual": int,
            "target": int|null, "delta": int|null, "percentage_of_target": float|null}, ...].
        """
        user = _current_user()
        with SessionLocal() as db:
            return _dump(
                ai_queries.team_target_performance(
                    db, user, date_from=_parse_date(date_from), date_to=_parse_date(date_to),
                    granularity=granularity, **_validated_filters(filters),
                )
            )

    @mcp.tool(
        name="opr_list_fields",
        annotations={"title": "Listar campos disponíveis da O.S.", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_list_fields() -> str:
        """Catálogo dinâmico de campos e capacidades - reflete a política de exposição vigente
        (configuração administrativa + restrição por perfil) para quem está chamando, não um
        estado estático do código. Use antes de montar `fields`/`filters`/`group_by` em outra tool
        para confirmar o que está de fato autorizado agora.

        Returns:
            JSON: lista de {"entity", "field", "type", "description", "filterable",
            "text_filterable", "groupable", "returnable", "selectable", "detail_available",
            "sensitive", "enabled_for_api", "enabled_for_mcp", "enabled_for_ai"}.
        """
        user = _current_user()
        with SessionLocal() as db:
            policy = _enforce(enforce_ai_endpoint_for_user, db, user, "ai.list_fields", "mcp")
            return _dump(policy.field_catalog())

    @mcp.tool(
        name="opr_management_cases",
        annotations={"title": "Casos de Gestão Integrada", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_management_cases(
        status: str | None = None,
        severity: str | None = None,
        regional: str | None = None,
        case_type: str | None = None,
        reference_year: int | None = None,
        reference_month: int | None = None,
        only_overdue: bool = False,
        only_open: bool = False,
        search: str | None = None,
    ) -> str:
        """Casos de gestão (desvios cobrados formalmente da matriz - produtividade abaixo da meta,
        dia vermelho do calendário, etc.), com justificativa do supervisor e decisão da matriz.

        Mesmo escopo de visibilidade da tela: quem não tem `management:review` só vê os casos das
        regionais que gerencia (ou dos quais é supervisor direto) - nunca a operação inteira.

        Args:
            status: pending, justified, in_progress, resolved ou rejected.
            severity: high, medium ou low.
            regional: nome da regional (normalizado internamente).
            case_type: productivity_below_target ou daily_performance_below_target.
            reference_year, reference_month: competência do caso.
            only_overdue: só casos abertos com prazo vencido.
            only_open: só casos ainda não encerrados (pending/justified/in_progress).
            search: busca em responsável, regional ou métrica.

        Returns:
            JSON {"summary": {...contadores...}, "items": [{status, severity, responsible_name,
            regional, metric_name, expected_value, actual_value, deviation_value, is_overdue,
            justification_text, action_plan, reviewed_by, ...}, ...]}.
        """
        from app.modules.management import cases as management_cases
        from app.modules.management.models import OPEN_CASE_STATUSES, ManagementCase

        user = _current_user()
        if "management:read" not in permissions_for_user(user):
            raise RuntimeError("Este usuário não tem permissão para consultar a Gestão Integrada (management:read).")
        filters = management_cases.ManagementCaseFilters(
            status=status,
            severity=severity,
            regional=regional,
            case_type=case_type,
            reference_year=reference_year,
            reference_month=reference_month,
            only_overdue=only_overdue,
            search=search,
            statuses=list(OPEN_CASE_STATUSES) if only_open else [],
        )
        with SessionLocal() as db:
            conditions = [*management_cases.case_scope_conditions(user), *management_cases.case_filter_conditions(filters)]
            rows = db.scalars(
                select(ManagementCase)
                .where(*conditions)
                .order_by(ManagementCase.created_at.desc())
                .limit(500)
            ).all()
            return _dump(
                {
                    "summary": management_cases.summarize_cases(db, conditions),
                    "items": [management_cases.case_out(item).model_dump() for item in rows],
                }
            )

    return mcp
