from app.modules.ai import queries as ai_queries
from app.modules.operations.models import OperationOrder


def test_available_fields_covers_every_table_column_exactly_once():
    result = ai_queries.available_fields()

    all_columns = set(OperationOrder.__table__.columns.keys())
    assert set(result["all_fields"]) == all_columns
    assert set(result["exposed_to_ai"]) | set(result["not_exposed"]) == all_columns
    assert set(result["exposed_to_ai"]).isdisjoint(result["not_exposed"])


def test_available_fields_flags_known_exposed_and_not_exposed_columns():
    result = ai_queries.available_fields()

    # Colunas usadas em AGGREGATION_DIMENSIONS, TEXT_FILTER_COLUMNS ou nos filtros exatos de
    # AiOrderFilters (ver AI_ORDER_FILTER_FIELDS) - já cobertas hoje pelas ferramentas de IA.
    # contract_type/person_type/company_id entram por já existirem como filtro exato
    # (contract_types/person_types/companies), mesmo sem serem dimensão de agrupamento.
    for column in ("regional", "os_subject", "diagnosis", "responsible", "status", "sla_status", "contract_type", "person_type", "company_id"):
        assert column in result["exposed_to_ai"], column

    # neighborhood (bairro) é dimensão de agrupamento E filtro de texto (ver AGGREGATION_DIMENSIONS/
    # TEXT_FILTER_COLUMNS) - confirmado como campo separado contra amostra real (migration
    # 20260811_0048).
    assert "neighborhood" in result["exposed_to_ai"]

    # latitude/longitude são valores contínuos - não entram como dimensão de agrupamento exata nem
    # filtro de texto, mas SÃO usados pelo filtro geográfico de raio (near_latitude/near_longitude/
    # radius_km) e pela dimensão calculada "geo_cluster" - por isso contam como expostos via
    # MANUALLY_EXPOSED_COLUMNS, não como pendência.
    assert "latitude" in result["exposed_to_ai"]
    assert "longitude" in result["exposed_to_ai"]

    # customer_login (login PPPoE/fibra, identificador de conexão) passou a ser filtro exato de IA
    # (AiOrderFilters.customer_logins) por pedido explícito do usuário em 2026-08-15 - fechar o
    # fluxo "login caiu -> buscar O.S. do cliente" (ver commit 5aae3b9, operations/queries.py
    # FILTER_COLUMNS["customer_logins"]). Não é senha/CPF/documento.
    assert "customer_login" in result["exposed_to_ai"]

    # raw_payload e customer_id (id interno do IXC, sem uso operacional direto pela IA) nunca foram
    # expostos como dimensão/filtro/texto de IA - devem continuar aparecendo como pendência.
    for column in ("raw_payload", "customer_id"):
        assert column in result["not_exposed"], column
