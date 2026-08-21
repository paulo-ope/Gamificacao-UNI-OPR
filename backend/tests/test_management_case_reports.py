"""Ferramentas de matriz sobre casos de gestão: aprovação em lote, exportação CSV e diagnóstico
agregado (pedido do usuário em 2026-08-20 - não precisar tratar caso por caso na tabela)."""
from __future__ import annotations

from datetime import date, timedelta

from app.core.security import get_current_user
from app.main import app
from app.models import User
from app.modules.management import cases as cases_engine
from app.modules.management.models import ManagementCase, ManagementCaseComment, ManagementCaseReason


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


# --- bulk_review_cases (motor) -------------------------------------------------------------------


def test_bulk_review_resolves_only_justified_cases(db_session, admin_user):
    justified = _make_case(db_session, responsible_name="Justificado", status="justified", justification_text="ok")
    pending = _make_case(db_session, responsible_name="Pendente", status="pending")
    db_session.commit()

    result = cases_engine.bulk_review_cases(
        db_session,
        case_ids=[justified.id, pending.id],
        status="resolved",
        review_note="Aprovado em lote.",
        reviewer_id=admin_user.id,
        scope_conditions=[],
    )
    db_session.commit()

    assert result == {"updated_cases": 1, "skipped_pending": 1, "not_found": 0}
    db_session.refresh(justified)
    db_session.refresh(pending)
    assert justified.status == "resolved"
    assert justified.reviewed_by == admin_user.id
    assert pending.status == "pending"
    comment = db_session.query(ManagementCaseComment).filter_by(case_id=justified.id).one()
    assert comment.comment == "Aprovado em lote."


def test_bulk_review_respects_scope_conditions(db_session, admin_user):
    mine = _make_case(db_session, responsible_name="Meu Caso", status="justified", regional="UNI JARU")
    theirs = _make_case(db_session, responsible_name="Outro Caso", status="justified", regional="UNI ARIQUEMES")
    db_session.commit()

    result = cases_engine.bulk_review_cases(
        db_session,
        case_ids=[mine.id, theirs.id],
        status="resolved",
        review_note=None,
        reviewer_id=admin_user.id,
        scope_conditions=[ManagementCase.regional == "UNI JARU"],
    )
    db_session.commit()

    assert result["updated_cases"] == 1
    assert result["not_found"] == 1
    db_session.refresh(theirs)
    assert theirs.status == "justified"


def test_bulk_review_endpoint_updates_multiple_cases(client, db_session, admin_user):
    first = _make_case(db_session, responsible_name="Um", status="justified")
    second = _make_case(db_session, responsible_name="Dois", status="justified")
    db_session.commit()

    response = client.post(
        "/api/management/cases/bulk-review",
        json={"case_ids": [first.id, second.id], "status": "resolved", "review_note": "Ok, aprovados."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["updated_cases"] == 2
    assert body["skipped_pending"] == 0


# --- case_diagnostics (motor) -------------------------------------------------------------------


def test_case_diagnostics_aggregates_by_regional_responsible_and_reason(db_session):
    reason = ManagementCaseReason(name="Ausência", active=True, requires_description=False)
    db_session.add(reason)
    db_session.flush()

    _make_case(db_session, responsible_name="Joao", regional="UNI JARU", status="pending", reason_id=None)
    _make_case(db_session, responsible_name="Joao", regional="UNI JARU", status="pending", reason_id=reason.id, due_date=date.today() - timedelta(days=1))
    _make_case(db_session, responsible_name="Maria", regional="UNI ARIQUEMES", status="resolved", reason_id=reason.id)
    db_session.commit()

    result = cases_engine.case_diagnostics(db_session, [])

    assert result["total_cases"] == 3
    regional_keys = {bucket["key"]: bucket for bucket in result["by_regional"]}
    assert regional_keys["UNI JARU"]["total"] == 2
    assert regional_keys["UNI JARU"]["open_cases"] == 2
    assert regional_keys["UNI JARU"]["overdue_cases"] == 1
    responsible_keys = {bucket["key"] for bucket in result["by_responsible"]}
    assert responsible_keys == {"Joao", "Maria"}
    reason_keys = {bucket["key"]: bucket["total"] for bucket in result["by_reason"]}
    assert reason_keys == {"Ausência": 2}


def test_case_diagnostics_endpoint_reflects_filters(client, db_session):
    _make_case(db_session, responsible_name="Joao", regional="UNI JARU")
    _make_case(db_session, responsible_name="Maria", regional="UNI ARIQUEMES")
    db_session.commit()

    response = client.get("/api/management/cases/diagnostics?regional=UNI JARU")
    assert response.status_code == 200
    body = response.json()
    assert body["total_cases"] == 1
    assert body["by_responsible"][0]["key"] == "Joao"


# --- export CSV ------------------------------------------------------------------------------


def test_export_cases_returns_csv_with_the_filtered_rows(client, db_session):
    _make_case(db_session, responsible_name="Joao Exportado", regional="UNI JARU")
    db_session.commit()

    response = client.get("/api/management/cases/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    body = response.text
    assert "Joao Exportado" in body
    assert "id;tipo;responsavel" in body


# --- tool MCP (opr_management_cases_diagnostics) --------------------------------------------


def test_mcp_tool_opr_management_cases_diagnostics_is_registered_and_read_only(monkeypatch):
    from app.modules.mcp_connector.server import build_mcp_server
    from app.core.config import get_settings

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://operacao.souuni.com")
    get_settings.cache_clear()
    try:
        server = build_mcp_server()
        tool = server._tool_manager.get_tool("opr_management_cases_diagnostics")
        assert tool is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
    finally:
        get_settings.cache_clear()
