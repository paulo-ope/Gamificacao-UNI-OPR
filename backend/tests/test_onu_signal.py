from __future__ import annotations

from datetime import datetime, timezone

from app.modules.ai_governance.models import AiEndpoint, AiFieldPermission
from app.modules.ai_governance.policy import bump_policy_version
from app.modules.operations.models import OperationLoginCurrentStatus, OperationOnuSignalCurrent
from app.modules.operations.onu_signal_snapshot import (
    _parse_ixc_datetime,
    _parse_ixc_float,
    _parse_ixc_text,
    query_onu_signal_status,
)
from app.services.ixc_client import fetch_onu_signal_by_login_ids


def _make_login(db_session, login_id: int, login: str):
    db_session.add(
        OperationLoginCurrentStatus(
            login_id=login_id,
            login=login,
            online="S",
            status_changed_at=datetime.now(timezone.utc),
            captured_at=datetime.now(timezone.utc),
        )
    )


def _make_signal(db_session, login_id: int, **overrides):
    defaults = dict(
        login_id=login_id,
        contract_id="145399",
        signal_rx_dbm=-18.5,
        signal_tx_dbm=2.1,
        last_drop_cause="Link Loss",
        onu_serial="AABBCCDDEEFF",
        onu_model="F670LV9.0",
        transmitter_id="408",
        temperature_c=45.0,
        voltage=3.3,
        signal_measured_at=datetime.now(timezone.utc),
        pon_id="1/1/2",
        pon_no="2",
        slot_no="1",
        latitude=-10.7078271,
        longitude=-62.2652299,
        captured_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    db_session.add(OperationOnuSignalCurrent(**defaults))


def test_ixc_field_parsers_handle_empty_and_zero_markers():
    assert _parse_ixc_datetime("0000-00-00 00:00:00") is None
    assert _parse_ixc_datetime(None) is None
    assert _parse_ixc_datetime("2026-08-14 10:00:00") == datetime(2026, 8, 14, 10, 0, 0, tzinfo=timezone.utc)
    assert _parse_ixc_float("") is None
    assert _parse_ixc_float("-18.50") == -18.5
    assert _parse_ixc_text("") is None
    assert _parse_ixc_text("  Link Loss  ") == "Link Loss"


def test_fetch_onu_signal_by_login_ids_returns_empty_iterator_for_no_ids():
    # Não deve montar nenhuma requisição quando a lista de IDs está vazia.
    assert list(fetch_onu_signal_by_login_ids(client=None, login_ids=[])) == []


def test_query_onu_signal_status_joins_login_name(db_session):
    _make_login(db_session, 1, "cliente.teste")
    _make_signal(db_session, 1)
    db_session.commit()

    results = query_onu_signal_status(db_session, login_ids=[1])
    assert len(results) == 1
    assert results[0]["login"] == "cliente.teste"
    assert results[0]["last_drop_cause"] == "Link Loss"
    assert results[0]["signal_rx_dbm"] == -18.5


def test_query_onu_signal_status_filters_by_drop_cause(db_session):
    _make_login(db_session, 1, "login-a")
    _make_login(db_session, 2, "login-b")
    _make_signal(db_session, 1, last_drop_cause="Link Loss")
    _make_signal(db_session, 2, last_drop_cause="Power Fail")
    db_session.commit()

    results = query_onu_signal_status(db_session, last_drop_causes=["Power Fail"])
    assert [row["login"] for row in results] == ["login-b"]


def test_onu_signal_endpoint_disabled_by_default(client):
    response = client.get("/api/operations/network/onu-signal")
    assert response.status_code == 403


def test_onu_signal_endpoint_works_once_enabled(client, db_session):
    endpoint = db_session.query(AiEndpoint).filter_by(key="operations.network.onu_signal").one()
    endpoint.enabled_api = True
    endpoint.enabled_ai = True
    login_id_field = db_session.query(AiFieldPermission).filter_by(entity="operations_onu_signal_current", field="login_id").one()
    login_id_field.enabled = True
    db_session.commit()
    bump_policy_version(db_session)

    _make_login(db_session, 1, "cliente.teste")
    _make_signal(db_session, 1)
    db_session.commit()

    response = client.get("/api/operations/network/onu-signal?login_ids=1")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["onu_serial"] == "AABBCCDDEEFF"
    assert body[0]["last_drop_cause"] == "Link Loss"
