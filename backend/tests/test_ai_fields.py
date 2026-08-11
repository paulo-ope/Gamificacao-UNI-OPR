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

    # raw_payload e os identificadores de cliente deste PR nunca foram expostos como
    # dimensão/filtro/texto de IA - devem aparecer como pendência, não somem silenciosamente.
    # latitude/longitude também: são valores contínuos, não fazem sentido como dimensão de
    # agrupamento nem filtro de texto - por design, só aparecem nos campos planos de search-orders.
    for column in ("raw_payload", "customer_login", "customer_id", "latitude", "longitude"):
        assert column in result["not_exposed"], column
