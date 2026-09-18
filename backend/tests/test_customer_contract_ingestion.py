from __future__ import annotations

from app.modules.operations.customer_contract_ingestion import import_customer_contracts
from app.modules.operations.models import OperationCustomerContract
from app.services.ixc_client import IxcClient, IxcPage


class FakeIxcClient(IxcClient):
    """Cliente IXC em memória cobrindo `cliente_contrato` e `cidade` - mesmo padrão dos outros
    fakes do projeto (list_all real, só troca a fonte de dado por tabela)."""

    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables
        self.calls: list[dict] = []

    def _field(self, tb):
        return tb.split(".")[-1]

    def _apply_filters(self, records, grid_param):
        result = records
        for item in grid_param:
            field = self._field(item["TB"])
            op = item["OP"]
            value = item["P"]
            if op == "=":
                result = [r for r in result if str(r.get(field)) == str(value)]
            elif op == "IN":
                allowed = set(value.split(","))
                result = [r for r in result if str(r.get(field)) in allowed]
        return result

    def list(self, table, *, grid_param=None, page=1, rp=100, sortname=None, sortorder="asc"):
        self.calls.append({"table": table, "grid_param": grid_param})
        records = self.tables.get(table, [])
        filtered = self._apply_filters(records, grid_param or [])
        if sortname:
            filtered = sorted(filtered, key=lambda r: int(r["id"]), reverse=sortorder == "desc")
        total = len(filtered)
        start = (page - 1) * rp
        page_records = filtered[start : start + rp]
        return IxcPage(records=page_records, total=total, page=page)


def _contract(contract_id, filial="11", status="A", status_internet="AA", cidade="60", bairro="Centro"):
    return {
        "id": str(contract_id),
        "id_cliente": str(1000 + contract_id),
        "id_filial": filial,
        # `cidade` é o id_cidade (FK pra tabela `cidade`), não o nome - achado real em produção
        # (2026-09-11), mesmo caso já corrigido em `ixc_ticket_ingestion.py`.
        "cidade": cidade,
        "bairro": bairro,
        "status": status,
        "status_internet": status_internet,
    }


def _cidade(cidade_id, nome):
    return {"id": str(cidade_id), "nome": nome}


def _cliente(cliente_id, cidade="0", bairro=""):
    return {"id": str(cliente_id), "cidade": cidade, "bairro": bairro}


def _client_with(contracts, cidades=None, clientes=None):
    return FakeIxcClient({
        "cliente_contrato": contracts,
        "cidade": cidades if cidades is not None else [_cidade(60, "Nova Brasilândia D'Oeste")],
        "cliente": clientes or [],
    })


def test_import_customer_contracts_creates_records(db_session):
    client = _client_with([_contract(1), _contract(2)])

    result = import_customer_contracts(db_session, client)

    assert result == {"fetched": 2, "created": 2, "updated": 0, "unchanged": 0, "rejected": 0}
    assert db_session.query(OperationCustomerContract).count() == 2
    row = db_session.query(OperationCustomerContract).filter_by(source_contract_id="1").one()
    assert row.regional == "UNI - NOVA BRASILANDIA DOESTE"
    assert row.city == "Nova Brasilândia D'Oeste"
    assert row.neighborhood == "Centro"
    assert row.status == "A"
    assert row.status_internet == "AA"


def test_import_customer_contracts_is_idempotent(db_session):
    client = _client_with([_contract(1)])
    import_customer_contracts(db_session, client)

    result = import_customer_contracts(db_session, client)

    assert result["created"] == 0
    assert result["unchanged"] == 1
    assert db_session.query(OperationCustomerContract).count() == 1


def test_import_customer_contracts_updates_status_change(db_session):
    client = _client_with([_contract(1, status="A")])
    import_customer_contracts(db_session, client)

    client.tables["cliente_contrato"][0]["status"] = "D"
    result = import_customer_contracts(db_session, client)

    assert result["updated"] == 1
    row = db_session.query(OperationCustomerContract).one()
    assert row.status == "D"


def test_import_customer_contracts_filters_by_filial(db_session):
    client = _client_with([_contract(1, filial="11"), _contract(2, filial="18")])

    result = import_customer_contracts(db_session, client, filial_ids=["11"])

    assert result["fetched"] == 1
    row = db_session.query(OperationCustomerContract).one()
    assert row.source_contract_id == "1"


def test_import_customer_contracts_resolves_city_id_to_name(db_session):
    client = _client_with(
        [_contract(1, cidade="60")],
        cidades=[_cidade(60, "Nova Brasilândia D'Oeste"), _cidade(61, "Rolim de Moura")],
    )

    import_customer_contracts(db_session, client)

    row = db_session.query(OperationCustomerContract).one()
    assert row.city == "Nova Brasilândia D'Oeste"


def test_import_customer_contracts_leaves_city_null_when_city_id_unknown(db_session):
    client = _client_with([_contract(1, cidade="999")], cidades=[_cidade(60, "Nova Brasilândia D'Oeste")])

    import_customer_contracts(db_session, client)

    row = db_session.query(OperationCustomerContract).one()
    assert row.city is None


def test_import_customer_contracts_falls_back_to_customer_registration_for_city_and_neighborhood(db_session):
    """Achado real em produção (2026-09-11, pedido explícito do usuário depois de eu ter desistido
    cedo demais): `cliente_contrato.cidade` vem "0" na grande maioria dos contratos reais, mas o
    CADASTRO do cliente tem a informação - confirmado ao vivo contra a API (10 de 10 numa amostra
    real). O fallback deve buscar aí antes de marcar como "sem cidade"."""
    client = _client_with(
        [_contract(1, cidade="0", bairro="")],
        cidades=[_cidade(60, "Nova Brasilândia D'Oeste"), _cidade(61, "Rolim de Moura")],
        clientes=[_cliente(1001, cidade="61", bairro="Setor 2")],  # id_cliente do _contract(1) é 1001
    )

    import_customer_contracts(db_session, client)

    row = db_session.query(OperationCustomerContract).one()
    assert row.city == "Rolim de Moura"
    assert row.neighborhood == "Setor 2"


def test_import_customer_contracts_does_not_look_up_customer_when_contract_already_has_city_and_neighborhood(db_session):
    """Nunca deve consultar `cliente` quando o contrato já tem cidade E bairro - evita chamada
    extra à API do IXC por contrato que não precisa (achado real: chamadas grandes já falharam
    nesta sessão, não vale gastar em quem não precisa)."""
    client = _client_with([_contract(1, cidade="60", bairro="Centro")])

    import_customer_contracts(db_session, client)

    assert not any(call["table"] == "cliente" for call in client.calls)
