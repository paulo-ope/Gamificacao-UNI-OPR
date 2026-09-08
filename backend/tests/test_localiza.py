"""UNI Localiza - geração de link de localização para o cliente compartilhar posição por GPS.

`admin_user` (fixture do conftest) tem role="admin", que já inclui `localiza:read`/
`localiza:manage` (ver `ROLE_PERMISSIONS` em `app/core/security.py`).
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, User
from app.modules.localiza.models import LocationRequest
from app.modules.localiza.service import DISTANCE_COMPATIBLE_MAX_METERS, classify_distance, haversine_distance_meters


def _admin_client(db_session, admin_user) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    return TestClient(app)


def _public_client(db_session) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _create(client, **overrides):
    payload = {"order_code": "OS-1001", "customer_name": "Cliente Teste"}
    payload.update(overrides)
    return client.post("/api/localiza", json=payload)


def test_create_location_request_and_token_never_stored_in_clear(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        response = _create(client)
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "pending"
        assert body["order_code"] == "OS-1001"
        raw_token = body["token"]
        assert len(raw_token) > 20
        assert body["public_link"].endswith(f"/l/{raw_token}")
    app.dependency_overrides.clear()

    stored = db_session.query(LocationRequest).filter(LocationRequest.id == body["id"]).one()
    assert stored.token_hash != raw_token
    assert raw_token not in stored.token_hash


def test_non_authorized_role_cannot_create(db_session):
    from app.core.security import hash_password

    viewer = User(name="Sem Permissao", email="sem.permissao.localiza@pytest.local", role="collaborator", active=True, password_hash=hash_password("Qualquer123"))
    db_session.add(viewer)
    db_session.commit()

    with _admin_client(db_session, viewer) as client:
        response = _create(client)
        assert response.status_code == 403
    app.dependency_overrides.clear()


def test_create_rejects_when_no_identifier_at_all_is_provided(db_session, admin_user):
    """O.S. costuma não existir ainda (link enviado antes de abrir o atendimento) - order_code
    sozinho não é mais obrigatório, mas a solicitação precisa de AO MENOS um identificador."""
    with _admin_client(db_session, admin_user) as client:
        response = _create(client, order_code="   ", customer_name="")
        assert response.status_code == 422
    app.dependency_overrides.clear()


def test_create_without_order_code_succeeds_using_opa_protocol(db_session, admin_user):
    """Caso real: atendente ainda está coletando a localização para abrir a O.S. no IXC - só o
    protocolo do atendimento no OPA Suite está disponível nesse momento."""
    with _admin_client(db_session, admin_user) as client:
        response = client.post("/api/localiza", json={"opa_protocol": "OPA-998877", "customer_name": "Cliente Teste"})
        assert response.status_code == 201
        body = response.json()
        assert body["order_code"] is None
        assert body["opa_protocol"] == "OPA-998877"
    app.dependency_overrides.clear()


def test_attach_order_code_fills_in_missing_order_later(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        created = client.post("/api/localiza", json={"opa_protocol": "OPA-112233"})
        assert created.status_code == 201
        item_id = created.json()["id"]
        assert created.json()["order_code"] is None

        attach_response = client.post(f"/api/localiza/{item_id}/attach-order", json={"order_code": "OS-778899"})
        assert attach_response.status_code == 200
        assert attach_response.json()["order_code"] == "OS-778899"
        assert attach_response.json()["opa_protocol"] == "OPA-112233"

        empty_attach = client.post(f"/api/localiza/{item_id}/attach-order", json={"order_code": "   "})
        assert empty_attach.status_code == 422
    app.dependency_overrides.clear()


def test_attach_order_code_rejected_on_invalidated_request(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        created = client.post("/api/localiza", json={"opa_protocol": "OPA-445566"})
        item_id = created.json()["id"]
        client.post(f"/api/localiza/{item_id}/invalidate")

        attach_response = client.post(f"/api/localiza/{item_id}/attach-order", json={"order_code": "OS-000111"})
        assert attach_response.status_code == 409
    app.dependency_overrides.clear()


def test_create_rejects_incomplete_registered_coordinate_pair(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        response = _create(client, registered_latitude=-10.5)
        assert response.status_code == 422
    app.dependency_overrides.clear()


def test_public_status_and_confirm_valid_token(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        created = _create(client, registered_latitude=-10.9472, registered_longitude=-61.9528)
        raw_token = created.json()["token"]
    app.dependency_overrides.clear()

    with _public_client(db_session) as client:
        status_response = client.get(f"/api/public/location/{raw_token}")
        assert status_response.status_code == 200
        body = status_response.json()
        assert body["valid"] is True
        assert body["order_code"] == "OS-1001"

        confirm_response = client.post(
            f"/api/public/location/{raw_token}/confirm",
            json={
                "latitude": -10.9470,
                "longitude": -61.9525,
                "accuracy_meters": 15.0,
                "gps_latitude": -10.9470,
                "gps_longitude": -61.9525,
                "adjusted_manually": False,
            },
        )
        assert confirm_response.status_code == 200
        assert confirm_response.json()["status"] == "confirmed"
    app.dependency_overrides.clear()

    stored = db_session.query(LocationRequest).filter(LocationRequest.order_code == "OS-1001").one()
    assert stored.status == "confirmed"
    assert stored.confirmed_latitude == -10.9470
    assert stored.distance_from_registered_meters is not None
    assert stored.adjusted_manually is False


def test_invalid_token_returns_generic_reason(db_session):
    with _public_client(db_session) as client:
        response = client.get("/api/public/location/token-que-nao-existe")
        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is False
        assert body["reason"] == "TOKEN_INVALID"
    app.dependency_overrides.clear()


def test_expired_token_is_rejected(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        created = _create(client)
        raw_token = created.json()["token"]
        item_id = created.json()["id"]
    app.dependency_overrides.clear()

    item = db_session.query(LocationRequest).filter(LocationRequest.id == item_id).one()
    item.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    with _public_client(db_session) as client:
        status_response = client.get(f"/api/public/location/{raw_token}")
        assert status_response.json()["valid"] is False
        assert status_response.json()["reason"] == "TOKEN_EXPIRED"

        confirm_response = client.post(
            f"/api/public/location/{raw_token}/confirm",
            json={"latitude": -10.0, "longitude": -61.0, "accuracy_meters": 10.0, "gps_latitude": -10.0, "gps_longitude": -61.0},
        )
        assert confirm_response.status_code == 409
        assert confirm_response.json()["detail"] == "TOKEN_EXPIRED"
    app.dependency_overrides.clear()


def test_confirmed_token_cannot_be_reused(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        created = _create(client)
        raw_token = created.json()["token"]
    app.dependency_overrides.clear()

    confirm_payload = {"latitude": -10.0, "longitude": -61.0, "accuracy_meters": 10.0, "gps_latitude": -10.0, "gps_longitude": -61.0}
    with _public_client(db_session) as client:
        first = client.post(f"/api/public/location/{raw_token}/confirm", json=confirm_payload)
        assert first.status_code == 200

        second = client.post(f"/api/public/location/{raw_token}/confirm", json=confirm_payload)
        assert second.status_code == 409
        assert second.json()["detail"] == "ALREADY_CONFIRMED"
    app.dependency_overrides.clear()


def test_invalidated_token_cannot_be_confirmed(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        created = _create(client)
        raw_token = created.json()["token"]
        item_id = created.json()["id"]

        invalidate_response = client.post(f"/api/localiza/{item_id}/invalidate")
        assert invalidate_response.status_code == 200
        assert invalidate_response.json()["status"] == "invalidated"

        second_invalidate = client.post(f"/api/localiza/{item_id}/invalidate")
        assert second_invalidate.status_code == 409
    app.dependency_overrides.clear()

    with _public_client(db_session) as client:
        status_response = client.get(f"/api/public/location/{raw_token}")
        assert status_response.json()["reason"] == "INVALIDATED"
    app.dependency_overrides.clear()


def test_invalid_latitude_and_longitude_are_rejected(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        created = _create(client)
        raw_token = created.json()["token"]
    app.dependency_overrides.clear()

    with _public_client(db_session) as client:
        response = client.post(
            f"/api/public/location/{raw_token}/confirm",
            json={"latitude": 999, "longitude": -61.0, "accuracy_meters": 10.0, "gps_latitude": -10.0, "gps_longitude": -61.0},
        )
        assert response.status_code == 422

        response2 = client.post(
            f"/api/public/location/{raw_token}/confirm",
            json={"latitude": -10.0, "longitude": 999, "accuracy_meters": 10.0, "gps_latitude": -10.0, "gps_longitude": -61.0},
        )
        assert response2.status_code == 422
    app.dependency_overrides.clear()


def test_regenerate_invalidates_old_and_creates_new(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        created = _create(client)
        item_id = created.json()["id"]
        old_token = created.json()["token"]

        regenerate_response = client.post(f"/api/localiza/{item_id}/regenerate")
        assert regenerate_response.status_code == 201
        new_body = regenerate_response.json()
        assert new_body["id"] != item_id
        assert new_body["order_code"] == "OS-1001"
    app.dependency_overrides.clear()

    old_item = db_session.query(LocationRequest).filter(LocationRequest.id == item_id).one()
    assert old_item.status == "invalidated"

    with _public_client(db_session) as client:
        old_status = client.get(f"/api/public/location/{old_token}")
        assert old_status.json()["reason"] == "INVALIDATED"
    app.dependency_overrides.clear()


def test_haversine_distance_and_classification():
    # ~111 km por grau de latitude no equador - distância conhecida para validar a fórmula.
    distance = haversine_distance_meters(0.0, 0.0, 1.0, 0.0)
    assert 110_000 < distance < 112_000

    assert classify_distance(10.0) == "compatible"
    assert classify_distance(DISTANCE_COMPATIBLE_MAX_METERS) == "compatible"
    assert classify_distance(100.0) == "minor_divergence"
    assert classify_distance(300.0) == "relevant_divergence"
    assert classify_distance(1000.0) == "high_divergence"


def test_audit_log_never_stores_raw_token(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        created = _create(client)
        raw_token = created.json()["token"]
    app.dependency_overrides.clear()

    with _public_client(db_session) as client:
        client.post(
            f"/api/public/location/{raw_token}/confirm",
            json={"latitude": -10.0, "longitude": -61.0, "accuracy_meters": 10.0, "gps_latitude": -10.0, "gps_longitude": -61.0},
        )
    app.dependency_overrides.clear()

    entries = db_session.query(AuditLog).filter(AuditLog.entity == "location_request").all()
    assert len(entries) >= 2  # created + geolocation_confirmed
    payload = "".join(str(entry.before_data) + str(entry.after_data) for entry in entries)
    assert raw_token not in payload


def test_list_shows_requester_name(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        _create(client)
        listing = client.get("/api/localiza")
        assert listing.status_code == 200
        assert listing.json()[0]["requested_by_name"] == admin_user.name
    app.dependency_overrides.clear()


def test_list_filters_by_date_range(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        created = _create(client, order_code="OS-DATA-1")
        item_id = created.json()["id"]
    app.dependency_overrides.clear()

    item = db_session.query(LocationRequest).filter(LocationRequest.id == item_id).one()
    item.created_at = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
    db_session.commit()

    with _admin_client(db_session, admin_user) as client:
        inside = client.get("/api/localiza", params={"date_from": "2026-01-05", "date_to": "2026-01-05"})
        assert any(row["id"] == item_id for row in inside.json())

        outside = client.get("/api/localiza", params={"date_from": "2026-01-06", "date_to": "2026-01-10"})
        assert all(row["id"] != item_id for row in outside.json())

        invalid_range = client.get("/api/localiza", params={"date_from": "2026-01-10", "date_to": "2026-01-01"})
        assert invalid_range.status_code == 400
    app.dependency_overrides.clear()


def test_list_filters_by_status(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        pending = _create(client, order_code="OS-STATUS-PENDING")
        confirmed = _create(client, order_code="OS-STATUS-CONFIRMED")
        confirmed_token = confirmed.json()["token"]
    app.dependency_overrides.clear()

    with _public_client(db_session) as client:
        client.post(
            f"/api/public/location/{confirmed_token}/confirm",
            json={"latitude": -10.0, "longitude": -61.0, "accuracy_meters": 10.0, "gps_latitude": -10.0, "gps_longitude": -61.0},
        )
    app.dependency_overrides.clear()

    with _admin_client(db_session, admin_user) as client:
        confirmed_only = client.get("/api/localiza", params={"status": "confirmed"})
        codes = {row["order_code"] for row in confirmed_only.json()}
        assert "OS-STATUS-CONFIRMED" in codes
        assert "OS-STATUS-PENDING" not in codes
    app.dependency_overrides.clear()


def test_link_ttl_setting_defaults_and_can_be_updated(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        default_settings = client.get("/api/localiza/settings")
        assert default_settings.status_code == 200
        assert default_settings.json()["link_ttl_hours"] > 0

        updated = client.put("/api/localiza/settings", json={"link_ttl_hours": 12})
        assert updated.status_code == 200
        assert updated.json()["link_ttl_hours"] == 12

        created = _create(client, order_code="OS-TTL-TEST")
        expires_at = datetime.fromisoformat(created.json()["expires_at"].replace("Z", "+00:00"))
        created_at = datetime.fromisoformat(created.json()["created_at"].replace("Z", "+00:00"))
        assert abs((expires_at - created_at) - timedelta(hours=12)) < timedelta(minutes=1)
    app.dependency_overrides.clear()


def test_link_ttl_setting_rejects_out_of_range_values(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        too_low = client.put("/api/localiza/settings", json={"link_ttl_hours": 0})
        assert too_low.status_code == 422
        too_high = client.put("/api/localiza/settings", json={"link_ttl_hours": 10_000})
        assert too_high.status_code == 422
    app.dependency_overrides.clear()


def test_mine_only_filter_shows_only_own_requests(db_session, admin_user):
    from app.core.security import hash_password
    from app.models import User

    other_user = User(name="Outro Atendente", email="outro.atendente.localiza@pytest.local", role="admin", active=True, password_hash=hash_password("Qualquer123"))
    db_session.add(other_user)
    db_session.commit()

    with _admin_client(db_session, admin_user) as client:
        _create(client, order_code="OS-MINE-ADMIN")
    app.dependency_overrides.clear()

    with _admin_client(db_session, other_user) as client:
        _create(client, order_code="OS-MINE-OTHER")

        mine = client.get("/api/localiza", params={"mine_only": "true"})
        codes = {row["order_code"] for row in mine.json()}
        assert codes == {"OS-MINE-OTHER"}

        everyone = client.get("/api/localiza")
        all_codes = {row["order_code"] for row in everyone.json()}
        assert {"OS-MINE-ADMIN", "OS-MINE-OTHER"} <= all_codes
    app.dependency_overrides.clear()


def test_ixc_identity_fields_are_persisted_and_carried_over_on_regenerate(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        created = _create(
            client,
            order_code="OS-IXC-IDENTITY",
            ixc_cliente_id=112781,
            ixc_login_id=72928,
            ixc_login="paulo.soares_1",
        )
        assert created.status_code == 201
        body = created.json()
        assert body["ixc_cliente_id"] == 112781
        assert body["ixc_login_id"] == 72928
        assert body["ixc_login"] == "paulo.soares_1"
        item_id = body["id"]

        regenerated = client.post(f"/api/localiza/{item_id}/regenerate")
        assert regenerated.status_code == 201
        assert regenerated.json()["ixc_login_id"] == 72928
        assert regenerated.json()["ixc_login"] == "paulo.soares_1"
    app.dependency_overrides.clear()

    # `order_code` se repete no original (agora invalidado) e no regenerado - pega o mais recente.
    stored = db_session.query(LocationRequest).filter(LocationRequest.order_code == "OS-IXC-IDENTITY").order_by(LocationRequest.id.desc()).first()
    assert stored.ixc_cliente_id == 112781
    assert stored.ixc_login_id == 72928
    assert stored.ixc_login == "paulo.soares_1"


def test_search_matches_ixc_login(db_session, admin_user):
    with _admin_client(db_session, admin_user) as client:
        _create(client, order_code="OS-SEARCH-LOGIN", ixc_login="joaosilva_2", opa_protocol=None, customer_name=None)
        response = client.get("/api/localiza", params={"search": "joaosilva"})
        codes = {row["order_code"] for row in response.json()}
        assert "OS-SEARCH-LOGIN" in codes
    app.dependency_overrides.clear()
