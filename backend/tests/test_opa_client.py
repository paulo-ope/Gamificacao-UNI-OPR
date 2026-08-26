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

    assert [record["_id"] for record in records] == ["U-1", "U-2"]
    assert [json.loads(request.content.decode())["options"]["skip"] for request in requests] == [0, 1]


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
