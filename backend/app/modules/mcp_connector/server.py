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
from datetime import date
from typing import Any
from urllib.parse import urlparse

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.modules.ai import queries as ai_queries

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
                    date_from=_parse_date(date_from), date_to=_parse_date(date_to), **(filters or {}),
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
                    group_by=group_by, **(filters or {}),
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
    ) -> str:
        """Busca paginada de O.S. individuais, com texto qualitativo (descrição de abertura,
        relato técnico) e todos os campos de SLA/tempo já calculados.

        Args:
            date_from, date_to: AAAA-MM-DD.
            page: página (1-indexado).
            page_size: itens por página (10-200).
            keyword: busca livre opcional.
            filters: """ + FILTERS_DOC + """ (inclui o filtro geográfico de raio, útil para "O.S.
                perto deste ponto/desta O.S.").

        Returns:
            JSON {"items": [...], "total_encontrado": int, "page": int, "page_size": int,
            "has_more": bool}. Cada item inclui order_code, regional, city, neighborhood,
            latitude, longitude, distance_km (só com filtro de raio), service_description,
            technical_report, service_address, datas do ciclo de vida, indicadores de etapa de
            SLA e a meta de equipe vigente na O.S.
        """
        user = _current_user()
        with SessionLocal() as db:
            return _dump(
                ai_queries.search_orders(
                    db, user, date_from=_parse_date(date_from), date_to=_parse_date(date_to),
                    page=page, page_size=min(page_size, 200), keyword=keyword, **(filters or {}),
                )
            )

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
            return _dump(ai_queries.backlog_aging(db, user, group_by=group_by, date_to=_parse_date(date_to), **(filters or {})))

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
                    denominator=denominator, origin_excluded_diagnoses=origin_excluded_diagnoses or [], **(filters or {}),
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
                    granularity=granularity, **(filters or {}),
                )
            )

    @mcp.tool(
        name="opr_list_fields",
        annotations={"title": "Listar campos disponíveis da O.S.", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    )
    def opr_list_fields() -> str:
        """Lista todos os campos da tabela de Ordens de Serviço e mostra quais já estão expostos
        às ferramentas de IA e quais ainda não estão.

        Returns:
            JSON {"all_fields": [...], "exposed_to_ai": [...], "not_exposed": [...]}.
        """
        _current_user()
        return _dump(ai_queries.available_fields())

    return mcp
