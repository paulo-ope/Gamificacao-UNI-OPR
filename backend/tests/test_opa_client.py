from __future__ import annotations

import json

import httpx

import app.services.opa_client as opa_client_module
from app.services.opa_client import OpaClient


def test_opa_client_uses_bearer_token_and_paginates():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer secret-token"
        body = json.loads(request.content.decode())
        skip = body["options"]["skip"]
        if skip == 0:
            return httpx.Response(200, json={"data": [{"id": "1"}], "total": 2})
        return httpx.Response(200, json={"data": [{"id": "2"}], "total": 2})

    client = OpaClient(
        base_url="https://opa.local",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    records = list(client.iter_attendances(opened_after="2026-08-01", opened_before="2026-08-01", limit=1))

    assert [record["id"] for record in records] == ["1", "2"]
    assert [json.loads(request.content.decode())["options"]["skip"] for request in requests] == [0, 1]
    assert json.loads(requests[0].content.decode())["filter"] == {
        "dataInicialAbertura": "2026-08-01",
        "dataFinalAbertura": "2026-08-01",
    }


def test_opa_client_advances_by_actual_returned_page_size_when_api_ignores_limit():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        skip = json.loads(request.content.decode())["options"]["skip"]
        if skip == 0:
            return httpx.Response(200, json={"data": [{"id": "1"}, {"id": "2"}, {"id": "3"}], "total": 6})
        return httpx.Response(200, json={"data": [{"id": "4"}, {"id": "5"}, {"id": "6"}], "total": 6})

    client = OpaClient(
        base_url="https://opa.local",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    records = list(client.iter_attendances(opened_after="2026-08-16", opened_before="2026-08-16", limit=1))

    assert [record["id"] for record in records] == ["1", "2", "3", "4", "5", "6"]
    assert [json.loads(request.content.decode())["options"]["skip"] for request in requests] == [0, 3]


def test_opa_client_stops_at_safety_record_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "1"}, {"id": "2"}, {"id": "3"}]})

    client = OpaClient(
        base_url="https://opa.local",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    records = list(client.iter_attendances(opened_after="2026-08-16", opened_before="2026-08-16", limit=1, max_records=5))

    assert len(records) == 5


def test_opa_client_lists_dimensions_with_get_body_pagination():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert request.url.path == "/api/v1/usuario/"
        skip = json.loads(request.content.decode())["options"]["skip"]
        if skip == 0:
            return httpx.Response(200, json={"data": [{"_id": "U-1"}], "total": 2})
        return httpx.Response(200, json={"data": [{"_id": "U-2"}], "total": 2})

    client = OpaClient(
        base_url="https://opa.local",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    records = client.list_users()

    # Sem duplicar: este OPA de teste ignora o filtro e devolve os mesmos usuários nas duas consultas.
    assert [record["_id"] for record in records] == ["U-1", "U-2"]
    # Desde 2026-10-08 o OPA exige filtro: uma consulta paginada por `tipo` (user e bot), cada uma
    # com a mesma paginação por skip de antes.
    assert [json.loads(request.content.decode())["options"]["skip"] for request in requests] == [0, 1, 0, 1]
    assert [json.loads(request.content.decode())["filter"] for request in requests][::2] == [{"tipo": "user"}, {"tipo": "bot"}]


def test_opa_client_list_clients_does_not_truncate_past_old_50000_limit():
    # Regressão da causa raiz identificada em
    # docs/auditoria-divergencia-opa-suite-2026-08-25.md: a base real do OPA
    # Suite tem mais de 100.000 clientes, mas `list_clients` cortava em
    # 50.000. Este teste falha com o limite antigo e passa com o corrigido.
    total = 50005

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"_id": str(i)} for i in range(total)], "total": total})

    client = OpaClient(
        base_url="https://opa.local",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    records = client.list_clients()

    assert len(records) == total


def test_opa_client_list_clients_still_respects_a_safety_ceiling(monkeypatch):
    monkeypatch.setattr(opa_client_module, "SUPPORT_OPA_CLIENT_MAX_RECORDS", 7)

    def handler(request: httpx.Request) -> httpx.Response:
        skip = json.loads(request.content.decode())["options"]["skip"]
        limit = json.loads(request.content.decode())["options"]["limit"]
        return httpx.Response(200, json={"data": [{"_id": f"C-{skip + i}"} for i in range(limit)]})

    client = OpaClient(
        base_url="https://opa.local",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    records = client.list_clients()

    assert len(records) == 7


def test_opa_client_unwraps_enveloped_attendance_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/atendimento/OPA-264"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "code": 200,
                "data": {"_id": "OPA-264", "protocolo": "264"},
            },
        )

    client = OpaClient(
        base_url="https://opa.local",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    detail = client.get_attendance_detail("OPA-264")

    assert detail == {"_id": "OPA-264", "protocolo": "264"}


# --- OPA passou a exigir filtro nas listagens (2026-10-08) ------------------------------------


def _client_requiring_filter(records_by_filter: dict):
    """OPA de teste que recusa listagem sem filtro (400) e responde conforme o filtro recebido."""
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        filters = body["filter"]
        seen.append({"path": request.url.path, "filter": filters})
        if not filters:
            return httpx.Response(
                400, json={"status": "error", "code": 400, "data": {"error": "NO_ARGUMENT_ERROR", "message": "At least one valid filter is required"}}
            )
        records = records_by_filter(request.url.path, filters)
        skip = body["options"]["skip"]
        return httpx.Response(200, json={"data": records[skip:]})

    client = OpaClient(base_url="https://opa.local", token="t", transport=httpx.MockTransport(handler))
    return client, seen


def test_list_users_sends_a_filter_and_joins_humans_and_bots():
    def records(path, filters):
        return [{"_id": "u1", "tipo": "user"}] if filters == {"tipo": "user"} else [{"_id": "b1", "tipo": "bot"}]

    client, seen = _client_requiring_filter(records)

    users = client.list_users()

    assert sorted(user["_id"] for user in users) == ["b1", "u1"]
    assert all(call["filter"] for call in seen)  # nunca uma listagem sem filtro


def test_list_users_does_not_duplicate_when_opa_ignores_the_filter():
    # Comportamento real do /usuario hoje: aceita o campo mas devolve todos, qualquer que seja o valor.
    everyone = [{"_id": "u1", "tipo": "user"}, {"_id": "b1", "tipo": "bot"}]
    client, _ = _client_requiring_filter(lambda path, filters: everyone)

    users = client.list_users()

    assert sorted(user["_id"] for user in users) == ["b1", "u1"]


def test_list_departments_covers_both_boolean_values_of_the_enumerable_filter():
    def records(path, filters):
        return [{"_id": "d-on"}] if filters == {"recebeAtendimento": True} else [{"_id": "d-off"}]

    client, seen = _client_requiring_filter(records)

    departments = client.list_departments()

    assert sorted(item["_id"] for item in departments) == ["d-off", "d-on"]
    # `False` precisa chegar ao OPA - não pode ser descartado como "valor vazio".
    assert {"recebeAtendimento": False} in [call["filter"] for call in seen]


def test_list_clients_covers_active_and_inactive_customers():
    def records(path, filters):
        return [{"_id": "c-a"}] if filters == {"status": "A"} else [{"_id": "c-i"}]

    client, seen = _client_requiring_filter(records)

    clients = client.list_clients()

    assert sorted(item["_id"] for item in clients) == ["c-a", "c-i"]
    assert [call["filter"] for call in seen if call["filter"]] == [{"status": "A"}, {"status": "I"}]


def test_list_collection_stops_when_opa_ignores_skip_and_returns_the_same_page_forever():
    # Comportamento real do /usuario filtrado em 2026-10-08: devolve a coleção inteira por página,
    # qualquer que seja o skip. Antes, a listagem repetia a mesma página até o teto de registros.
    everyone = [{"_id": f"u{index}"} for index in range(30)]
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": everyone})

    client = OpaClient(base_url="https://opa.local", token="t", transport=httpx.MockTransport(handler))

    records = client.list_collection("/api/v1/usuario/", filters={"tipo": "user"}, limit=10)

    assert [record["_id"] for record in records] == [f"u{index}" for index in range(30)]
    assert len(requests) == 2  # a 2ª página já não trouxe nenhum _id novo


def test_list_collection_keeps_records_without_id_even_when_pages_repeat_ids():
    pages = {0: [{"_id": "a"}, {"nome": "sem-id-1"}], 2: [{"_id": "b"}, {"nome": "sem-id-2"}]}

    def handler(request: httpx.Request) -> httpx.Response:
        skip = json.loads(request.content.decode())["options"]["skip"]
        return httpx.Response(200, json={"data": pages.get(skip, [])})

    client = OpaClient(base_url="https://opa.local", token="t", transport=httpx.MockTransport(handler))

    records = client.list_collection("/api/v1/x/", filters={"a": "b"}, limit=2)

    assert len(records) == 4
