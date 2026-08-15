"""Catálogo de campos e capacidades - item 3/10 do pedido de governança IA/MCP.

A fonte real dos campos é sempre a introspecção dos models SQLAlchemy (`__table__.columns`), nunca
uma lista mantida à mão - evita o catálogo divergir do banco (o problema que `opr_list_fields`
já tentava resolver, mas de forma estática). As capacidades (filterable/text_filterable/groupable/
returnable/selectable/detail_available) refletem o que a API/MCP JÁ FAZEM hoje (lidas de
`operations.queries.FILTER_COLUMNS`, `ai.queries.AGGREGATION_DIMENSIONS`/`TEXT_FILTER_COLUMNS` e do
schema `OperationOrderOut`) - são o "default calculado do código". Overrides administrativos vivem
em `AiFieldPermission` (tabela), nunca aqui; `policy.py` combina as duas coisas.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.ai import queries as ai_queries
from app.modules.operations import queries as operations_queries
from app.modules.operations.models import OperationLoginCurrentStatus, OperationOnuSignalCurrent, OperationOrder
from app.modules.operations.schemas import OperationOrderOut

ENTITY_OPERATION_ORDERS = "operations_orders"
ENTITY_LOGIN_CURRENT_STATUS = "operations_login_current_status"
ENTITY_ONU_SIGNAL_CURRENT = "operations_onu_signal_current"


@dataclass(frozen=True)
class FieldDescriptor:
    entity: str
    field: str
    type: str
    filterable: bool = False
    text_filterable: bool = False
    groupable: bool = False
    returnable: bool = False
    selectable: bool = False
    detail_available: bool = False
    sensitive: bool = False
    # Estado inicial de `AiFieldPermission.enabled` na primeira migração (item 26 do pedido: o que
    # já funciona hoje continua igual; capacidade nova em tabela nova entra desligada até a
    # Administração decidir).
    default_enabled: bool = True


def _operation_order_registry() -> dict[str, FieldDescriptor]:
    filterable_keys = {column.key for column in operations_queries.FILTER_COLUMNS.values()}
    text_filterable_keys = {
        key for column in ai_queries.TEXT_FILTER_COLUMNS.values() if (key := getattr(column, "key", None)) is not None
    }
    groupable_keys = {column.key for column in ai_queries.AGGREGATION_DIMENSIONS.values()}
    # latitude/longitude não são uma dimensão de agrupamento exata (quem existe pra isso é o
    # "geo_cluster" calculado, que não é uma coluna) - mas suportam o filtro geográfico por raio
    # (near_latitude/near_longitude/radius_km), então entram como filtráveis, não agrupáveis.
    filterable_keys |= ai_queries.MANUALLY_EXPOSED_COLUMNS
    # Campos de data usáveis como base de `date_field` (item 7 do pedido) - já eram filtráveis de
    # fato hoje via `date_from`/`date_to` (opened_at/closed_at, na regra fixa "abriu OU fechou no
    # período") ou passam a ser a partir desta fase (scheduled_at, execution_started_at etc., que
    # nenhum endpoint deixava escolher como base antes). Nenhum desses é sensível nem passa a ser
    # retornável por causa disto - `returnable` continua vindo só de `OperationOrderOut` abaixo.
    filterable_keys |= set(operations_queries.DATE_FIELD_COLUMNS.keys())
    column_keys = set(OperationOrder.__table__.columns.keys())
    # `raw_payload` fica fora de propósito - é sempre sensível, tratado à parte abaixo.
    returnable_keys = (set(OperationOrderOut.model_fields) - {"raw_payload"}) & column_keys

    registry: dict[str, FieldDescriptor] = {}
    for column in OperationOrder.__table__.columns:
        key = column.key
        sensitive = key == "raw_payload"
        is_returnable = key in returnable_keys and not sensitive
        registry[key] = FieldDescriptor(
            entity=ENTITY_OPERATION_ORDERS,
            field=key,
            type=str(column.type),
            filterable=key in filterable_keys,
            text_filterable=key in text_filterable_keys,
            groupable=key in groupable_keys,
            returnable=is_returnable,
            selectable=is_returnable,
            # `raw_payload` só aparece no detalhe (redigido) - nunca em listagem, nunca selecionável.
            detail_available=is_returnable or sensitive,
            sensitive=sensitive,
            default_enabled=True,
        )

    # Campos computados a partir de `raw_payload` (item 3 do pedido: "service_description",
    # "technical_report") - não são colunas de `OperationOrder.__table__` (são `@computed_field`
    # em `OperationOrderOut`, ver operations/schemas.py), então precisam de entrada própria aqui
    # pra poderem ser pedidos via `fields`/aparecer no detalhe. `service_description` já é
    # text_filterable hoje (`ai.queries.TEXT_FILTER_COLUMNS["service_description"]`) - os outros
    # três não têm filtro de nenhum tipo hoje.
    for computed_field_name, is_text_filterable in (
        ("service_description", True),
        ("technical_report", False),
        ("service_address", False),
        ("address_is_structured", False),
    ):
        registry[computed_field_name] = FieldDescriptor(
            entity=ENTITY_OPERATION_ORDERS,
            field=computed_field_name,
            type="computed",
            filterable=False,
            text_filterable=is_text_filterable,
            groupable=False,
            returnable=True,
            selectable=True,
            detail_available=True,
            sensitive=False,
            default_enabled=True,
        )
    return registry


_LOGIN_DATETIME_KEYS = {"captured_at", "status_changed_at", "last_connected_at", "last_disconnected_at"}


def _login_current_status_registry() -> dict[str, FieldDescriptor]:
    # Capacidade existe (a tabela é indexada e consultável) - `GET /operations/network/logins`
    # (item 20 do pedido) e os tools opr_login_status/opr_search_logins já sabem filtrar por
    # login/status/regional/raio geográfico/datetime. `default_enabled=True` desde 2026-08-15
    # (pedido explícito do usuário) - o endpoint continua controlando o acesso de fato
    # (enabled_api/enabled_mcp/enabled_ai em AiEndpoint), então habilitar o campo aqui não expõe
    # nada sozinho sem o endpoint também estar ligado.
    filterable_keys = {"login_id", "login", "online", "regional", "latitude", "longitude"} | _LOGIN_DATETIME_KEYS
    registry: dict[str, FieldDescriptor] = {}
    for column in OperationLoginCurrentStatus.__table__.columns:
        key = column.key
        registry[key] = FieldDescriptor(
            entity=ENTITY_LOGIN_CURRENT_STATUS,
            field=key,
            type=str(column.type),
            filterable=key in filterable_keys,
            text_filterable=key == "login",
            groupable=key in {"online", "regional"},
            returnable=True,
            selectable=True,
            detail_available=True,
            sensitive=False,
            default_enabled=True,
        )
    return registry


_ONU_DATETIME_KEYS = {"signal_measured_at", "captured_at"}


def _onu_signal_current_registry() -> dict[str, FieldDescriptor]:
    # Telemetria óptica/ONU (tabela `radpop_radio_cliente_fibra` do IXC, achada por sondagem manual
    # em 2026-08-14 - não documentada publicamente). `default_enabled=True` desde 2026-08-15 (pedido
    # explícito do usuário) - mesmo racional do login_current_status acima: o endpoint (AiEndpoint)
    # continua sendo o controle de acesso de fato. `onu_serial` (MAC da ONU) não é PII de cliente -
    # é identificador de equipamento, mesmo racional de latitude/longitude não serem sensíveis em
    # `operations_orders`.
    filterable_keys = {
        "login_id", "contract_id", "last_drop_cause", "transmitter_id", "pon_id", "pon_no", "slot_no",
        "latitude", "longitude",
    } | _ONU_DATETIME_KEYS
    registry: dict[str, FieldDescriptor] = {}
    for column in OperationOnuSignalCurrent.__table__.columns:
        key = column.key
        registry[key] = FieldDescriptor(
            entity=ENTITY_ONU_SIGNAL_CURRENT,
            field=key,
            type=str(column.type),
            filterable=key in filterable_keys,
            text_filterable=False,
            groupable=key in {"last_drop_cause", "transmitter_id", "pon_id", "pon_no", "slot_no"},
            returnable=True,
            selectable=True,
            detail_available=True,
            sensitive=False,
            default_enabled=True,
        )
    return registry


def build_field_registry() -> dict[str, dict[str, FieldDescriptor]]:
    """Catálogo completo (todas as entidades governadas), chave externa = nome da entidade."""
    return {
        ENTITY_OPERATION_ORDERS: _operation_order_registry(),
        ENTITY_LOGIN_CURRENT_STATUS: _login_current_status_registry(),
        ENTITY_ONU_SIGNAL_CURRENT: _onu_signal_current_registry(),
    }
