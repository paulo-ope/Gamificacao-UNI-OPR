from __future__ import annotations

from datetime import datetime, timezone

from app.modules.ai_governance.models import AiEndpoint, AiFieldPermission
from app.modules.ai_governance.policy import bump_policy_version
from app.modules.operations.login_geo_clusters import query_login_status
from app.modules.operations.models import OperationLoginCurrentStatus, OperationOrder
from app.modules.operations.period import current_month_bounds

_DATE_FROM, _DATE_TO = current_month_bounds()
_ORDERS_QUERY = f"date_from={_DATE_FROM.isoformat()}&date_to={_DATE_TO.isoformat()}"


def _make_order(db_session, *, source_order_id, order_code, latitude=None, longitude=None, **overrides):
    defaults = dict(
        source="ixc",
        source_order_id=source_order_id,
        order_code=order_code,
        regional="UNI - JI PARANA",
        os_type="Manutenção",
        os_subject="Reparo",
        sector="Suporte Externo Fibra",
        status="Finalizada",
        status_code="F",
        is_closed=True,
        sla_status="on_time",
        opened_at=datetime(2026, 8, 1, 12, tzinfo=timezone.utc),
        closed_at=datetime(2026, 8, 1, 15, tzinfo=timezone.utc),
        latitude=latitude,
        longitude=longitude,
        raw_payload={"mensagem": "abertura"},
    )
    defaults.update(overrides)
    order = OperationOrder(**defaults)
    db_session.add(order)
    db_session.flush()
    return order


def test_orders_list_geo_radius_filters_and_sorts_by_distance(client, db_session):
    # Ji-Paraná (referência) e um ponto bem próximo devem aparecer; um ponto em Porto Velho (~370km) não.
    _make_order(db_session, source_order_id="GEO-NEAR", order_code="IXC-GEO-NEAR", latitude=-10.885, longitude=-61.9518)
    _make_order(db_session, source_order_id="GEO-FAR", order_code="IXC-GEO-FAR", latitude=-8.7619, longitude=-63.9039)

    response = client.get(
        f"/api/operations/orders?{_ORDERS_QUERY}&near_latitude=-10.88&near_longitude=-61.95&radius_km=5&fields=order_code"
    )
    assert response.status_code == 200
    codes = [item["order_code"] for item in response.json()["items"]]
    assert codes == ["IXC-GEO-NEAR"]


def test_orders_list_geo_requires_all_three_params(client, db_session):
    response = client.get(f"/api/operations/orders?{_ORDERS_QUERY}&near_latitude=-10.88")
    assert response.status_code == 422


def test_login_status_endpoint_disabled_by_default(client):
    response = client.get("/api/operations/network/logins")
    assert response.status_code == 403


def test_login_status_endpoint_works_once_enabled(client, db_session):
    endpoint = db_session.query(AiEndpoint).filter_by(key="operations.network.logins").one()
    # "api" exige enabled_api E enabled_ai juntos (switches independentes, item 11 do pedido) -
    # ligar só um dos dois mantém o endpoint bloqueado para essa origem, de propósito.
    endpoint.enabled_api = True
    endpoint.enabled_ai = True
    # Habilitar o endpoint não habilita os campos sozinho (governança em duas camadas, item 2 do
    # pedido) - o campo "login" também precisa estar habilitado para poder ser usado como filtro.
    login_field = db_session.query(AiFieldPermission).filter_by(entity="operations_login_current_status", field="login").one()
    login_field.enabled = True
    db_session.commit()
    bump_policy_version(db_session)

    db_session.add(
        OperationLoginCurrentStatus(
            login_id=1,
            login="cliente.teste",
            online="S",
            latitude=-10.885,
            longitude=-61.9518,
            status_changed_at=datetime.now(timezone.utc),
            captured_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    response = client.get("/api/operations/network/logins?logins=cliente.teste")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["login"] == "cliente.teste"


def test_query_login_status_filters_by_radius(db_session):
    db_session.add_all(
        [
            OperationLoginCurrentStatus(
                login_id=1, login="perto", online="S", latitude=-10.885, longitude=-61.9518,
                status_changed_at=datetime.now(timezone.utc), captured_at=datetime.now(timezone.utc),
            ),
            OperationLoginCurrentStatus(
                login_id=2, login="longe", online="S", latitude=-8.7619, longitude=-63.9039,
                status_changed_at=datetime.now(timezone.utc), captured_at=datetime.now(timezone.utc),
            ),
        ]
    )
    db_session.commit()

    results = query_login_status(db_session, near_latitude=-10.88, near_longitude=-61.95, radius_km=5)
    assert [row.login for row in results] == ["perto"]
