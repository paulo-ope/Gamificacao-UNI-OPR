from datetime import datetime, time, timezone

from app.modules.operations.models import OperationOrder
from app.modules.operations.period import OPERATIONS_TIMEZONE, current_month_bounds


def _utc_at(day, hour=12):
    return datetime.combine(day, time(hour=hour), tzinfo=OPERATIONS_TIMEZONE).astimezone(timezone.utc)


def test_orders_search_finds_matches_inside_raw_payload_description(client, db_session):
    """Item 13: busca livre precisa achar termo dentro da descrição de abertura, que só existe no
    JSON bruto (raw_payload) - não numa coluna própria."""
    date_from, _ = current_month_bounds()
    opened_at = _utc_at(date_from, 8)
    db_session.add_all(
        [
            OperationOrder(
                source="ixc",
                source_order_id="RAW-SEARCH-HIT",
                order_code="RAW-SEARCH-HIT",
                sector="Suporte Externo Fibra",
                opened_at=opened_at,
                raw_payload={"mensagem": "Cliente relatou queda de sinal na fibra ontem à noite"},
            ),
            OperationOrder(
                source="ixc",
                source_order_id="RAW-SEARCH-MISS",
                order_code="RAW-SEARCH-MISS",
                sector="Suporte Externo Fibra",
                opened_at=opened_at,
                raw_payload={"mensagem": "Solicitação de mudança de endereço"},
            ),
        ]
    )
    db_session.flush()

    response = client.get(
        "/api/operations/orders",
        params={
            "date_from": date_from.isoformat(),
            "date_to": date_from.isoformat(),
            "search": "queda de sinal",
        },
    )

    assert response.status_code == 200
    assert [item["order_code"] for item in response.json()["items"]] == ["RAW-SEARCH-HIT"]


def test_orders_search_only_checks_the_confirmed_mensagem_key(client, db_session):
    """"descricao"/"descricao_servico" foram candidatas antigas em RAW_PAYLOAD_DESCRIPTION_KEYS -
    confirmado contra uma amostra real de 104.203 O.S. que NUNCA aparecem na fonte (0 ocorrências),
    diferente de "mensagem" (~99,99% preenchido). Removidas: a busca não deve mais achar nada só
    porque o valor está guardado sob uma dessas duas chaves mortas."""
    date_from, _ = current_month_bounds()
    opened_at = _utc_at(date_from, 8)
    db_session.add_all(
        [
            OperationOrder(
                source="ixc",
                source_order_id="RAW-SEARCH-DEAD-KEY",
                order_code="RAW-SEARCH-DEAD-KEY",
                sector="Suporte Externo Fibra",
                opened_at=opened_at,
                raw_payload={"descricao": "Roteador reiniciando sozinho", "descricao_servico": "Instalação de novo ponto"},
            ),
            OperationOrder(
                source="ixc",
                source_order_id="RAW-SEARCH-LIVE-KEY",
                order_code="RAW-SEARCH-LIVE-KEY",
                sector="Suporte Externo Fibra",
                opened_at=opened_at,
                raw_payload={"mensagem": "Roteador reiniciando sozinho"},
            ),
        ]
    )
    db_session.flush()

    response = client.get(
        "/api/operations/orders",
        params={"date_from": date_from.isoformat(), "date_to": date_from.isoformat(), "search": "reiniciando"},
    )
    assert [item["order_code"] for item in response.json()["items"]] == ["RAW-SEARCH-LIVE-KEY"]
