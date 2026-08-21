"""Validação ponta a ponta do histórico de sinal ONU: captura do IXC, motor de consulta, e as
três portas de entrega (API operacional, API de IA/ChatGPT via api-key, tool MCP) - pedido do
usuário em 2026-08-20."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.security import hash_api_key
from app.models import User
from app.modules.ai_governance.models import AiApiToken
from app.modules.operations.models import OperationOnuSignalSnapshot
from app.modules.operations.onu_signal_snapshot import (
    capture_onu_signal_snapshot,
    query_onu_signal_history,
    record_onu_signal_history,
)


def _make_snapshot(db_session, **overrides) -> OperationOnuSignalSnapshot:
    defaults = dict(
        login_id=1,
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
    item = OperationOnuSignalSnapshot(**defaults)
    db_session.add(item)
    return item


# --- Ingestão do IXC (capture_onu_signal_snapshot grava tanto o estado atual quanto o histórico) -


def test_record_onu_signal_history_bulk_inserts_rows(db_session):
    row = {
        "login_id": 1,
        "contract_id": "145399",
        "signal_rx_dbm": -18.5,
        "signal_tx_dbm": 2.1,
        "last_drop_cause": "Link Loss",
        "onu_serial": "AABBCCDDEEFF",
        "onu_model": "F670LV9.0",
        "transmitter_id": "408",
        "transmitter_name": "Radio Central",
        "temperature_c": 45.0,
        "voltage": 3.3,
        "signal_measured_at": datetime.now(timezone.utc),
        "pon_id": "1/1/2",
        "pon_no": "2",
        "slot_no": "1",
        "latitude": -10.7078271,
        "longitude": -62.2652299,
        "captured_at": datetime.now(timezone.utc),
    }
    record_onu_signal_history(db_session, [row])
    db_session.commit()

    saved = db_session.query(OperationOnuSignalSnapshot).one()
    assert saved.login_id == 1
    assert saved.onu_serial == "AABBCCDDEEFF"
    assert saved.transmitter_name == "Radio Central"


def test_capture_onu_signal_snapshot_pulls_from_ixc_and_records_both_tables(db_session, monkeypatch):
    from app.modules.operations import onu_signal_snapshot as module
    from app.modules.operations.models import OperationLoginCurrentStatus

    db_session.add(
        OperationLoginCurrentStatus(
            login_id=1,
            login="cliente.teste",
            online="N",
            status_changed_at=datetime.now(timezone.utc),
            captured_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    ixc_record = {
        "id_login": "1",
        "id_contrato": "145399",
        "sinal_rx": "-18.50",
        "sinal_tx": "2.10",
        "causa_ultima_queda": "Link Loss",
        "mac": "AABBCCDDEEFF",
        "onu_tipo": "F670LV9.0",
        "id_transmissor": "408",
        "temperatura": "45.0",
        "voltagem": "3.3",
        "data_sinal": "2026-08-14 10:00:00",
        "ponid": "1/1/2",
        "ponno": "2",
        "slotno": "1",
        "latitude": "-10.7078271",
        "longitude": "-62.2652299",
    }
    monkeypatch.setattr(module, "fetch_onu_signal_by_login_ids", lambda client, login_ids: iter([ixc_record]))
    monkeypatch.setattr(module, "fetch_radios_by_ids", lambda client, ids: iter([]))

    captured = capture_onu_signal_snapshot(db_session, client=object())

    assert captured == 1
    current = db_session.execute(
        __import__("sqlalchemy").select(module.OperationOnuSignalCurrent)
    ).scalar_one()
    assert current.onu_serial == "AABBCCDDEEFF"
    history = db_session.query(OperationOnuSignalSnapshot).one()
    assert history.login_id == 1
    assert history.last_drop_cause == "Link Loss"


# --- Motor de consulta -------------------------------------------------------------------------


def test_query_onu_signal_history_requires_an_identifier(db_session):
    assert query_onu_signal_history(db_session, login_ids=None, onu_serials=None) == []


def test_query_onu_signal_history_filters_by_login_and_date_range(db_session):
    old_point = datetime.now(timezone.utc) - timedelta(days=10)
    recent_point = datetime.now(timezone.utc) - timedelta(hours=1)
    _make_snapshot(db_session, login_id=1, captured_at=old_point, signal_rx_dbm=-25.0)
    _make_snapshot(db_session, login_id=1, captured_at=recent_point, signal_rx_dbm=-18.0)
    _make_snapshot(db_session, login_id=2, captured_at=recent_point, signal_rx_dbm=-30.0)
    db_session.commit()

    results = query_onu_signal_history(db_session, login_ids=[1], date_from=datetime.now(timezone.utc) - timedelta(days=1))

    assert len(results) == 1
    assert results[0]["login_id"] == 1
    assert results[0]["signal_rx_dbm"] == -18.0


def test_query_onu_signal_history_filters_by_onu_serial(db_session):
    _make_snapshot(db_session, login_id=1, onu_serial="SERIAL-A")
    _make_snapshot(db_session, login_id=2, onu_serial="SERIAL-B")
    db_session.commit()

    results = query_onu_signal_history(db_session, onu_serials=["SERIAL-B"])

    assert [row["onu_serial"] for row in results] == ["SERIAL-B"]


# --- Porta 1: API operacional (GET /operations/network/onu-signal/history) ---------------------
# default_enabled=True no AI Governance (ver bootstrap.py) - diferente do estado atual, o
# histórico já nasce liberado, sem precisar habilitar nada na tela de Administração.


def test_operations_history_endpoint_delivers_data_by_default(client, db_session):
    _make_snapshot(db_session, login_id=1)
    db_session.commit()

    response = client.get("/api/operations/network/onu-signal/history?login_ids=1")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["onu_serial"] == "AABBCCDDEEFF"


def test_operations_history_endpoint_requires_at_least_one_identifier(client, db_session):
    response = client.get("/api/operations/network/onu-signal/history")

    assert response.status_code == 200
    assert response.json() == []


# --- Porta 2: API de IA/ChatGPT (POST /ai/infra/onu-signal-history, autenticada por api-key) ----


def test_ai_history_endpoint_delivers_data_to_a_scoped_api_key(client, db_session):
    service_user = User(name="Servico IA Teste", email="ai-onu-history@pytest.local", role="ai_service", active=True, password_hash="x")
    db_session.add(service_user)
    db_session.flush()

    raw_key = "raw-key-for-onu-history-test-0"
    db_session.add(
        AiApiToken(
            user_id=service_user.id,
            name="Leitura infra",
            scopes=["infra.read"],
            key_prefix=raw_key[:12],
            key_hash=hash_api_key(raw_key),
        )
    )
    _make_snapshot(db_session, login_id=1)
    db_session.commit()

    response = client.post(
        "/api/ai/infra/onu-signal-history",
        json={"login_ids": [1]},
        headers={"x-api-key": raw_key},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["onu_serial"] == "AABBCCDDEEFF"


def test_ai_history_endpoint_rejects_a_key_without_infra_scope(client, db_session):
    service_user = User(name="Servico IA Sem Escopo", email="ai-onu-history-no-scope@pytest.local", role="ai_service", active=True, password_hash="x")
    db_session.add(service_user)
    db_session.flush()

    raw_key = "raw-key-for-onu-history-no-scope"
    db_session.add(
        AiApiToken(
            user_id=service_user.id,
            name="Somente pedidos",
            scopes=["orders.read"],
            key_prefix=raw_key[:12],
            key_hash=hash_api_key(raw_key),
        )
    )
    db_session.commit()

    response = client.post(
        "/api/ai/infra/onu-signal-history",
        json={"login_ids": [1]},
        headers={"x-api-key": raw_key},
    )

    assert response.status_code == 403


# --- Porta 3: tool MCP (opr_onu_signal_history, mesmo conector remoto usado pelo ChatGPT/Claude) -


def test_mcp_tool_opr_onu_signal_history_is_registered_and_read_only(monkeypatch):
    from app.modules.mcp_connector.server import build_mcp_server

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://operacao.souuni.com")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        server = build_mcp_server()
        tool = server._tool_manager.get_tool("opr_onu_signal_history")
        assert tool is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
    finally:
        get_settings.cache_clear()
