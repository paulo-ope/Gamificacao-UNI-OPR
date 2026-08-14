from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.modules.ai.auth import ApiKeyContext
from app.modules.ai.router import ai_fields_route, order_details_route
from app.modules.ai.schemas import AiOrderDetailsRequest
from app.modules.ai_governance.models import AiEndpoint
from app.modules.ai_governance.policy import bump_policy_version
from app.modules.operations.models import OperationOrder


def _context(user, scopes=None, token_id=None):
    # `scopes=None` = mesmo comportamento de uma chave legado (ApiKeyCredential) - irrestrito,
    # ver app/modules/ai/auth.py:ApiKeyContext.
    return ApiKeyContext(user=user, scopes=scopes, token_id=token_id)


def _make_order(db_session, *, source_order_id, order_code, **overrides):
    defaults = dict(
        source="ixc",
        source_order_id=source_order_id,
        order_code=order_code,
        regional="UNI - JI PARANA",
        os_type="Manutenção",
        os_subject="Reparo",
        sector="Suporte Externo Fibra",
        responsible="Técnico A",
        status="Finalizada",
        status_code="F",
        is_closed=True,
        sla_status="on_time",
        opened_at=datetime(2026, 8, 1, 12, tzinfo=timezone.utc),
        closed_at=datetime(2026, 8, 1, 15, tzinfo=timezone.utc),
        raw_payload={"mensagem": "abertura", "mensagem_resposta": "fechamento", "cpf_cliente": "000.000.000-00"},
    )
    defaults.update(overrides)
    order = OperationOrder(**defaults)
    db_session.add(order)
    db_session.flush()
    return order


def test_field_catalog_reflects_capabilities_dynamically(db_session, admin_user):
    catalog = ai_fields_route(db=db_session, user=admin_user)
    by_key = {(row["entity"], row["field"]): row for row in catalog}

    assert by_key[("operations_orders", "order_code")]["selectable"] is True
    assert by_key[("operations_orders", "raw_payload")]["sensitive"] is True
    assert by_key[("operations_orders", "raw_payload")]["selectable"] is False
    assert by_key[("operations_orders", "raw_payload")]["detail_available"] is True
    assert by_key[("operations_orders", "service_description")]["text_filterable"] is True
    # Capacidade nova (item 26) entra desabilitada por padrão.
    assert by_key[("operations_login_current_status", "login")]["enabled_for_api"] is False


def test_order_details_finds_by_order_code_and_reports_missing(db_session, admin_user):
    _make_order(db_session, source_order_id="D-1", order_code="IXC-D-1")

    payload = AiOrderDetailsRequest(order_codes=["IXC-D-1", "IXC-NAO-EXISTE"])
    result = order_details_route(payload=payload, db=db_session, context=_context(admin_user))

    assert len(result["items"]) == 1
    assert result["items"][0]["order_code"] == "IXC-D-1"
    assert result["items"][0]["raw_payload"]["cpf_cliente"] == "***"
    assert result["not_found_order_codes"] == ["IXC-NAO-EXISTE"]
    assert result["not_found_source_order_ids"] == []


def test_order_details_finds_by_source_order_id_batch(db_session, admin_user):
    _make_order(db_session, source_order_id="D-2", order_code="IXC-D-2")
    _make_order(db_session, source_order_id="D-3", order_code="IXC-D-3")

    payload = AiOrderDetailsRequest(source_order_ids=["D-2", "D-3"])
    result = order_details_route(payload=payload, db=db_session, context=_context(admin_user))

    assert {item["order_code"] for item in result["items"]} == {"IXC-D-2", "IXC-D-3"}


def test_order_details_summary_mode_hides_raw_payload(db_session, admin_user):
    _make_order(db_session, source_order_id="D-4", order_code="IXC-D-4")

    payload = AiOrderDetailsRequest(order_codes=["IXC-D-4"], response_mode="summary")
    result = order_details_route(payload=payload, db=db_session, context=_context(admin_user))

    item = result["items"][0]
    assert "raw_payload" not in item
    assert item["order_code"] == "IXC-D-4"


def test_order_details_explicit_fields_can_include_raw_payload_in_detail(db_session, admin_user):
    _make_order(db_session, source_order_id="D-5", order_code="IXC-D-5")

    payload = AiOrderDetailsRequest(order_codes=["IXC-D-5"], fields=["order_code", "raw_payload"])
    result = order_details_route(payload=payload, db=db_session, context=_context(admin_user))

    assert set(result["items"][0].keys()) == {"order_code", "raw_payload"}


def test_order_details_rejects_request_with_no_identifiers():
    with pytest.raises(Exception):
        AiOrderDetailsRequest()


def test_order_details_respects_endpoint_disabled_in_governance(db_session, admin_user):
    _make_order(db_session, source_order_id="D-6", order_code="IXC-D-6")

    endpoint = db_session.query(AiEndpoint).filter_by(key="ai.order_details").one()
    endpoint.enabled_api = False
    db_session.commit()
    bump_policy_version(db_session)

    with pytest.raises(Exception):
        order_details_route(payload=AiOrderDetailsRequest(order_codes=["IXC-D-6"]), db=db_session, context=_context(admin_user))
