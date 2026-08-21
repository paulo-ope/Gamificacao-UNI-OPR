"""Diagnóstico agregado de casos de gestão exposto para IA (POST /ai/management/cases-diagnostics)
- pedido do usuário em 2026-08-20."""
from __future__ import annotations

from datetime import date, timedelta

from app.core.security import hash_api_key
from app.models import User
from app.modules.ai_governance.models import AiApiToken
from app.modules.management import cases as cases_engine
from app.modules.management.models import ManagementCase


def _make_case(db_session, **overrides) -> ManagementCase:
    defaults = dict(
        case_type=cases_engine.CASE_TYPE_PRODUCTIVITY,
        source_module="operations",
        reference_year=2026,
        reference_month=7,
        regional="UNI JARU",
        responsible_name="Joao Campo",
        metric_name=cases_engine.METRIC_DAILY_AVERAGE,
        expected_value=5.0,
        actual_value=2.0,
        deviation_value=60.0,
        severity="high",
        status="pending",
        due_date=date.today() + timedelta(days=7),
    )
    defaults.update(overrides)
    item = ManagementCase(**defaults)
    db_session.add(item)
    db_session.flush()
    return item


def _make_service_user_with_scope(db_session, scopes: list[str], raw_key: str) -> None:
    service_user = User(name="Servico IA Cases", email=f"ai-cases-{raw_key[:6]}@pytest.local", role="ai_service", active=True, password_hash="x")
    db_session.add(service_user)
    db_session.flush()
    db_session.add(
        AiApiToken(
            user_id=service_user.id,
            name="Leitura gestao",
            scopes=scopes,
            key_prefix=raw_key[:12],
            key_hash=hash_api_key(raw_key),
        )
    )


def test_ai_diagnostics_endpoint_delivers_data_to_a_scoped_api_key(client, db_session):
    raw_key = "raw-key-for-cases-diagnostics-0"
    _make_service_user_with_scope(db_session, ["management.read"], raw_key)
    _make_case(db_session, responsible_name="Joao Campo", regional="UNI JARU")
    _make_case(db_session, responsible_name="Maria Silva", regional="UNI JARU")
    db_session.commit()

    response = client.post(
        "/api/ai/management/cases-diagnostics",
        json={"regional": "UNI JARU"},
        headers={"x-api-key": raw_key},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_cases"] == 2
    responsible_keys = {bucket["key"] for bucket in body["by_responsible"]}
    assert responsible_keys == {"Joao Campo", "Maria Silva"}


def test_ai_diagnostics_endpoint_rejects_a_key_without_management_scope(client, db_session):
    raw_key = "raw-key-for-cases-diagnostics-no-scope"
    _make_service_user_with_scope(db_session, ["orders.read"], raw_key)
    db_session.commit()

    response = client.post(
        "/api/ai/management/cases-diagnostics",
        json={},
        headers={"x-api-key": raw_key},
    )

    assert response.status_code == 403
