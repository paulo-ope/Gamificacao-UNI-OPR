from __future__ import annotations

from datetime import datetime, time, timezone

from app.modules.ai_governance.gate import enforce_ai_endpoint_for_user
from app.modules.ai_governance.models import AiEndpoint, AiFieldPermission
from app.modules.ai_governance.policy import bump_policy_version
from app.modules.operations.models import OperationOrder
from app.modules.operations.period import OPERATIONS_TIMEZONE, current_month_bounds


def _utc_at(day, hour=12):
    return datetime.combine(day, time(hour=hour), tzinfo=OPERATIONS_TIMEZONE).astimezone(timezone.utc)


def _make_order(db_session, *, source_order_id, order_code, opened_at, closed_at=None, **overrides):
    defaults = dict(
        source="ixc",
        source_order_id=source_order_id,
        order_code=order_code,
        regional="UNI - JI PARANA",
        state="RO",
        city="Ji-Paraná",
        os_type="Manutenção",
        os_subject="Reparo",
        sector="Suporte Externo Fibra",
        creator="Atendente A",
        responsible="Técnico A",
        status="Finalizada" if closed_at else "Em execução",
        status_code="F" if closed_at else "EX",
        is_closed=closed_at is not None,
        sla_status="on_time",
        opened_at=opened_at,
        closed_at=closed_at,
        raw_payload={"mensagem": "Relato de abertura", "cpf_cliente": "000.000.000-00"},
    )
    defaults.update(overrides)
    order = OperationOrder(**defaults)
    db_session.add(order)
    db_session.flush()
    return order


def test_orders_list_supports_field_selection(client, db_session):
    date_from, date_to = current_month_bounds()
    _make_order(db_session, source_order_id="F2-1", order_code="IXC-F2-1", opened_at=_utc_at(date_from, 9))

    query = f"date_from={date_from.isoformat()}&date_to={date_to.isoformat()}"
    response = client.get(f"/api/operations/orders?{query}&fields=order_code&fields=regional")
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == [{"order_code": "IXC-F2-1", "regional": "UNI - JI PARANA"}]


def test_orders_list_rejects_unauthorized_field_explicitly(client, db_session):
    date_from, date_to = current_month_bounds()
    _make_order(db_session, source_order_id="F2-2", order_code="IXC-F2-2", opened_at=_utc_at(date_from, 9))

    query = f"date_from={date_from.isoformat()}&date_to={date_to.isoformat()}"
    response = client.get(f"/api/operations/orders?{query}&fields=raw_payload")
    assert response.status_code == 422
    assert "raw_payload" in response.json()["detail"]


def test_orders_list_summary_mode_returns_curated_subset(client, db_session):
    date_from, date_to = current_month_bounds()
    _make_order(db_session, source_order_id="F2-3", order_code="IXC-F2-3", opened_at=_utc_at(date_from, 9))

    query = f"date_from={date_from.isoformat()}&date_to={date_to.isoformat()}"
    response = client.get(f"/api/operations/orders?{query}&response_mode=summary")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["order_code"] == "IXC-F2-3"
    # Modo summary deve ser bem mais enxuto que o full (item 6 do pedido - evitar payload excessivo).
    assert "raw_payload" not in item
    assert "normalization_notes" not in item
    assert set(item) <= {
        "order_code", "regional", "city", "os_type", "os_subject", "sector", "status",
        "sla_status", "opened_at", "closed_at", "responsible", "priority",
    }


def test_orders_list_date_field_filters_by_closed_at_only(client, db_session):
    date_from, date_to = current_month_bounds()
    # Aberta no período mas fechada fora dele - com date_field=closed_at NÃO deve aparecer.
    _make_order(
        db_session, source_order_id="F2-OPEN-ONLY", order_code="IXC-F2-OPEN-ONLY",
        opened_at=_utc_at(date_from, 9), closed_at=None,
    )
    # Fechada dentro do período - deve aparecer.
    _make_order(
        db_session, source_order_id="F2-CLOSED", order_code="IXC-F2-CLOSED",
        opened_at=_utc_at(date_from, 9), closed_at=_utc_at(date_from, 15),
    )

    query = f"date_from={date_from.isoformat()}&date_to={date_to.isoformat()}"
    response = client.get(f"/api/operations/orders?{query}&date_field=closed_at&fields=order_code")
    assert response.status_code == 200
    codes = {item["order_code"] for item in response.json()["items"]}
    assert codes == {"IXC-F2-CLOSED"}


def test_orders_list_rejects_invalid_date_field(client, db_session):
    date_from, date_to = current_month_bounds()
    query = f"date_from={date_from.isoformat()}&date_to={date_to.isoformat()}"
    response = client.get(f"/api/operations/orders?{query}&date_field=not_a_real_field")
    assert response.status_code == 422


def test_order_detail_supports_field_selection_and_summary_mode(client, db_session):
    date_from, _ = current_month_bounds()
    _make_order(db_session, source_order_id="F2-DETAIL", order_code="IXC-F2-DETAIL", opened_at=_utc_at(date_from, 9))

    full = client.get("/api/operations/orders/F2-DETAIL")
    assert full.status_code == 200
    assert "raw_payload" in full.json()

    filtered = client.get("/api/operations/orders/F2-DETAIL?fields=order_code")
    assert filtered.status_code == 200
    assert filtered.json() == {"order_code": "IXC-F2-DETAIL"}

    summary = client.get("/api/operations/orders/F2-DETAIL?response_mode=summary")
    assert summary.status_code == 200
    assert "raw_payload" not in summary.json()
    assert summary.json()["order_code"] == "IXC-F2-DETAIL"


def test_disabling_endpoint_in_governance_blocks_it_immediately(client, db_session):
    date_from, date_to = current_month_bounds()
    _make_order(db_session, source_order_id="F2-GATE", order_code="IXC-F2-GATE", opened_at=_utc_at(date_from, 9))

    endpoint = db_session.query(AiEndpoint).filter_by(key="operations.orders.list").one()
    endpoint.enabled_api = False
    db_session.commit()
    bump_policy_version(db_session)

    query = f"date_from={date_from.isoformat()}&date_to={date_to.isoformat()}"
    response = client.get(f"/api/operations/orders?{query}")
    assert response.status_code == 403

    # Reabilitar deve liberar de novo imediatamente (sem reiniciar o processo).
    endpoint.enabled_api = True
    db_session.commit()
    bump_policy_version(db_session)
    response = client.get(f"/api/operations/orders?{query}")
    assert response.status_code == 200


def test_disabling_field_in_governance_removes_it_from_selectable_output(client, db_session, admin_user):
    date_from, date_to = current_month_bounds()
    _make_order(db_session, source_order_id="F2-FIELD-OFF", order_code="IXC-F2-FIELD-OFF", opened_at=_utc_at(date_from, 9))

    permission = db_session.query(AiFieldPermission).filter_by(entity="operations_orders", field="responsible").one()
    permission.selectable = False
    permission.returnable = False
    db_session.commit()
    bump_policy_version(db_session)

    query = f"date_from={date_from.isoformat()}&date_to={date_to.isoformat()}"
    rejected = client.get(f"/api/operations/orders?{query}&fields=responsible")
    assert rejected.status_code == 422

    policy = enforce_ai_endpoint_for_user(db_session, admin_user, "operations.orders.list", "api")
    assert "responsible" not in policy.selectable_fields("operations_orders")
