"""Cobre os fetchers novos de `su_ticket` (atendimento real do IXC, que dispara a O.S.) e
`cliente_contrato` (base de clientes por filial) - primeira fatia do plano de
docs/STATUS.md (atendimento IXC por regional), validado ao vivo contra a API em 2026-09-11
antes de qualquer código. Reaproveita o `FakeIxcClient` de `test_ixc_client_partitioning.py`
(mesmo padrão: `list_all` de verdade, só troca a fonte de dados por uma lista local)."""

from app.services.ixc_client import (
    IxcClient,
    IxcPage,
    fetch_customer_contracts,
    fetch_ticket_id_bounds,
    fetch_tickets,
)


class FakeIxcClient(IxcClient):
    def __init__(self, records):
        self.records = records
        self.calls = []

    def _field(self, tb):
        return tb.split(".")[-1]

    def _apply_filters(self, records, grid_param):
        result = records
        for item in grid_param:
            field = self._field(item["TB"])
            op = item["OP"]
            value = item["P"]
            if op == ">=":
                result = [r for r in result if str(r[field]) >= str(value)]
            elif op == "<=":
                result = [r for r in result if str(r[field]) <= str(value)]
            elif op == "=":
                result = [r for r in result if str(r[field]) == str(value)]
            elif op == "IN":
                allowed = set(value.split(","))
                result = [r for r in result if str(r[field]) in allowed]
        return result

    def list(self, table, *, grid_param=None, page=1, rp=100, sortname=None, sortorder="asc"):
        self.calls.append({"table": table, "page": page, "rp": rp, "grid_param": grid_param})
        filtered = self._apply_filters(self.records, grid_param or [])
        if sortname:
            filtered = sorted(filtered, key=lambda r: int(r["id"]), reverse=sortorder == "desc")
        total = len(filtered)
        start = (page - 1) * rp
        page_records = filtered[start : start + rp]
        return IxcPage(records=page_records, total=total, page=page)


def _ticket(ticket_id, filial="11", assunto="90"):
    return {
        "id": str(ticket_id),
        "protocolo": f"T{ticket_id}",
        "id_filial": filial,
        "id_cliente": "173833",
        "id_contrato": "50000",
        "id_assunto": assunto,
        "status": "OSAB",
        "su_status": "EP",
        "data_criacao": "2026-09-01 08:00:00",
        "data_ultima_alteracao": "2026-09-01 08:05:00",
    }


def _contract(contract_id, filial="11", status="A"):
    return {
        "id": str(contract_id),
        "id_filial": filial,
        "id_cliente": str(1000 + contract_id),
        "cidade": "Nova Brasilândia D'Oeste",
        "status": status,
        "status_internet": "AA",
    }


def test_fetch_tickets_filters_by_filial():
    records = [_ticket(1, filial="11"), _ticket(2, filial="18"), _ticket(3, filial="11")]
    client = FakeIxcClient(records)

    result = list(fetch_tickets(client, filial_ids=["11"]))

    assert {r["id"] for r in result} == {"1", "3"}
    assert client.calls[0]["table"] == "su_ticket"


def test_fetch_tickets_filters_by_created_window():
    records = [_ticket(i) for i in range(1, 4)]
    records[0]["data_criacao"] = "2026-08-31 23:00:00"
    client = FakeIxcClient(records)

    result = list(fetch_tickets(client, created_after="2026-09-01 00:00:00"))

    assert {r["id"] for r in result} == {"2", "3"}


def test_fetch_ticket_id_bounds_returns_min_and_max():
    records = [_ticket(i) for i in [5, 12, 30]]
    client = FakeIxcClient(records)

    bounds = fetch_ticket_id_bounds(client)

    assert bounds == (5, 30)


def test_fetch_ticket_id_bounds_returns_none_when_empty():
    client = FakeIxcClient([])

    assert fetch_ticket_id_bounds(client) is None


def test_fetch_customer_contracts_filters_by_filial_and_status():
    records = [
        _contract(1, filial="11", status="A"),
        _contract(2, filial="11", status="D"),
        _contract(3, filial="18", status="A"),
    ]
    client = FakeIxcClient(records)

    result = list(fetch_customer_contracts(client, filial_ids=["11"], statuses=["A"]))

    assert {r["id"] for r in result} == {"1"}
    assert client.calls[0]["table"] == "cliente_contrato"


def test_fetch_customer_contracts_without_filters_returns_all():
    records = [_contract(1), _contract(2)]
    client = FakeIxcClient(records)

    result = list(fetch_customer_contracts(client))

    assert {r["id"] for r in result} == {"1", "2"}
