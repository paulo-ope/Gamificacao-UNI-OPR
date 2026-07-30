from app.modules.operations import ixc_ingestion
from app.services.ixc_client import IxcClient, IxcPage, IxcQueryLimitError, fetch_service_orders


class FakeIxcClient(IxcClient):
    """Cliente IXC em memória para testes: reaproveita `IxcClient.list_all` de verdade (que só chama
    `self.list(...)` em loop), só troca a fonte de dados por uma lista local em vez de HTTP real."""

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
                result = [r for r in result if int(r[field]) >= int(value)]
            elif op == "<=":
                result = [r for r in result if int(r[field]) <= int(value)]
            elif op == "=":
                result = [r for r in result if str(r[field]) == str(value)]
            elif op == "IN":
                allowed = set(value.split(","))
                result = [r for r in result if str(r[field]) in allowed]
        return result

    def list(self, table, *, grid_param=None, page=1, rp=100, sortname=None, sortorder="asc"):
        self.calls.append({"page": page, "rp": rp, "grid_param": grid_param})
        filtered = self._apply_filters(self.records, grid_param or [])
        if sortname:
            filtered = sorted(filtered, key=lambda r: int(r["id"]), reverse=sortorder == "desc")
        total = len(filtered)
        start = (page - 1) * rp
        page_records = filtered[start : start + rp]
        return IxcPage(records=page_records, total=total, page=page)


def _order(order_id, sector="5", status="A"):
    return {"id": str(order_id), "protocolo": f"P{order_id}", "setor": sector, "status": status}


def test_fetch_service_orders_below_limit_returns_all_records():
    records = [_order(i) for i in range(1, 11)]
    client = FakeIxcClient(records)

    result = list(fetch_service_orders(client, setor_ids=["5"], statuses=["A"], max_records=100))

    assert {r["id"] for r in result} == {str(i) for i in range(1, 11)}


def test_fetch_backlog_partition_splits_query_above_limit(monkeypatch):
    monkeypatch.setattr(ixc_ingestion, "MAX_IXC_RECORDS_PER_QUERY", 5)
    records = [_order(i) for i in range(1, 21)]  # 20 registros, acima do limite de 5
    client = FakeIxcClient(records)

    result = list(ixc_ingestion._fetch_backlog_partition(client, "5", "A"))

    assert {r["id"] for r in result} == {str(i) for i in range(1, 21)}
    # nenhuma página individual pode ter excedido o limite de segurança configurado
    assert all(call["rp"] <= 200 for call in client.calls)


def test_fetch_open_backlog_records_dedupes_across_sector_status_partitions(monkeypatch):
    monkeypatch.setattr(ixc_ingestion, "MAX_IXC_RECORDS_PER_QUERY", 3)
    # Mesmas O.S. poderiam, em tese, aparecer em mais de uma fatia se a bissecção não fosse
    # estritamente por faixas não sobrepostas - o dict por id em _fetch_open_backlog_records garante
    # que o resultado final não duplica independentemente disso.
    records = [_order(i) for i in range(1, 8)]
    client = FakeIxcClient(records)

    result = ixc_ingestion._fetch_open_backlog_records(client, ["5"])

    ids = [r["id"] for r in result]
    assert sorted(ids, key=int) == [str(i) for i in range(1, 8)]
    assert len(ids) == len(set(ids)), "não deve haver O.S. duplicada no resultado"


def test_fetch_backlog_partition_propagates_error_when_id_range_cannot_shrink(monkeypatch):
    monkeypatch.setattr(ixc_ingestion, "MAX_IXC_RECORDS_PER_QUERY", 3)
    # Seis O.S. compartilhando o mesmo id (cenário patológico/improvável na prática) - a faixa de id
    # não consegue encolher (id_min == id_max) e a consulta continua acima do limite mesmo assim.
    records = [_order(1) for _ in range(6)]
    client = FakeIxcClient(records)

    try:
        list(ixc_ingestion._fetch_backlog_partition(client, "5", "A"))
        assert False, "deveria ter propagado IxcQueryLimitError"
    except IxcQueryLimitError:
        pass


def test_fetch_id_range_partitioned_propagates_error_when_depth_exceeded(monkeypatch):
    monkeypatch.setattr(ixc_ingestion, "MAX_IXC_RECORDS_PER_QUERY", 1)
    monkeypatch.setattr(ixc_ingestion, "MAX_ID_PARTITION_DEPTH", 1)
    records = [_order(i) for i in range(1, 21)]
    client = FakeIxcClient(records)

    try:
        list(ixc_ingestion._fetch_id_range_partitioned(client, "5", "A", id_min=1, id_max=20))
        assert False, "deveria ter propagado IxcQueryLimitError ao atingir a profundidade maxima"
    except IxcQueryLimitError:
        pass
