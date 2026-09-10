"""Paridade MCP x HTTP das 5 tools novas do 1o pacote de expansão (2026-09-10).

Estes testes existem por causa de um critério explícito do pedido: "uma tool não pode retornar um
número diferente da superfície existente". Aqui a MESMA consulta é feita pelos dois caminhos - a
rota HTTP que a tela chama e a tool MCP - com os MESMOS parâmetros, e os números são comparados
campo a campo.

É o teste que pega o tipo de regressão que os testes de unidade de cada lado não pegam: alguém
mexer no serviço e só um dos dois consumidores acompanhar.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.modules.mcp_connector import server as mcp_server
from app.modules.operations.models import OperationImportRun, OperationOrder
from app.modules.support.models import SupportOpaAttendance
from app.modules.support.opa_filters import SUPPORT_TIMEZONE


class SessionLocalStub:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.fixture()
def mcp_tool(monkeypatch, db_session, admin_user):
    from app.core.config import get_settings

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://test.local")
    get_settings.cache_clear()
    server = mcp_server.build_mcp_server()
    monkeypatch.setattr(mcp_server, "SessionLocal", SessionLocalStub(db_session))
    monkeypatch.setattr(mcp_server, "get_access_token", lambda: SimpleNamespace(subject=str(admin_user.id)))
    monkeypatch.setattr(mcp_server, "resolve_user_for_access_token", lambda token: admin_user)

    def _call(name: str, **kwargs):
        registered = server._tool_manager.get_tool(name)
        assert registered is not None, f"tool {name} não está registrada"
        return json.loads(registered.fn(**kwargs))

    yield _call
    get_settings.cache_clear()


def _make_open_order(db_session, code: str, *, regional: str, elapsed_hours: float, target: float | None) -> None:
    db_session.add(
        OperationOrder(
            source="ixc",
            source_order_id=code,
            order_code=code,
            regional=regional,
            city="Jaru",
            os_type="Manutencao",
            os_subject="Reparo",
            status="Em execucao",
            responsible="Tecnico Um",
            is_closed=False,
            opened_at=datetime.now(timezone.utc) - timedelta(hours=3),
            elapsed_hours=elapsed_hours,
            sla_target_hours=target,
        )
    )


def _make_attendance(db_session, source_id: str, *, day: date, attendant_id: str, tma: int, tmr: int) -> None:
    opened_at = datetime.combine(day, time(12, 0), tzinfo=SUPPORT_TIMEZONE).astimezone(timezone.utc)
    db_session.add(
        SupportOpaAttendance(
            source_id=source_id,
            attendant_id=attendant_id,
            attendant_name=f"Atendente {attendant_id}",
            department_id="D-1",
            department_name="Suporte N1",
            reason_id="R-1",
            reason_name="Sem conexão",
            channel="whatsapp",
            status="encerrado",
            customer_id="C-1",
            customer_name="Cliente Um",
            opened_at=opened_at,
            closed_at=opened_at + timedelta(seconds=tma),
            first_response_at=opened_at + timedelta(seconds=tmr),
            rating=4.0,
            tma_seconds=tma,
            tmr_seconds=tmr,
            tmr_all_responses_seconds=tmr - 10,
        )
    )


# --- opr_data_freshness x GET /operations/data-freshness ----------------------------------------


def test_freshness_bate_com_a_rota_da_tela(client, db_session, mcp_tool):
    db_session.add(
        OperationImportRun(
            status="completed",
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 10),
            finished_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
    )
    db_session.commit()

    http = client.get("/api/operations/data-freshness").json()
    tool = mcp_tool("opr_data_freshness")

    # Os 4 campos da origem são idênticos; a tool só ACRESCENTA checked_at/age_seconds/has_data.
    for campo in ("last_successful_import_at", "status", "date_from", "date_to"):
        assert tool[campo] == http[campo], f"divergência em {campo}"
    assert set(tool) - set(http) == {"checked_at", "age_seconds", "has_data"}


# --- opr_operations_now x GET /operations/in-progress* ------------------------------------------


def test_operations_now_bate_com_as_rotas_de_em_andamento(client, db_session, mcp_tool):
    _make_open_order(db_session, "OS-1", regional="UNI JARU", elapsed_hours=12.0, target=10.0)
    _make_open_order(db_session, "OS-2", regional="UNI JARU", elapsed_hours=9.0, target=10.0)
    _make_open_order(db_session, "OS-3", regional="UNI ARIQUEMES", elapsed_hours=1.0, target=10.0)
    _make_open_order(db_session, "OS-4", regional="UNI ARIQUEMES", elapsed_hours=5.0, target=None)
    db_session.commit()

    http_risk = client.get("/api/operations/in-progress/sla-risk").json()
    http_breakdown = client.get("/api/operations/in-progress?group_by=regional").json()
    tool = mcp_tool("opr_operations_now", group_by="regional")

    assert tool["sla_risk"] == http_risk
    assert tool["breakdown"]["items"] == http_breakdown
    assert tool["total_in_progress"] == sum(item["quantity"] for item in http_risk) == 4


def test_operations_now_bate_com_a_rota_sob_o_mesmo_filtro(client, db_session, mcp_tool):
    _make_open_order(db_session, "OS-JARU-1", regional="UNI JARU", elapsed_hours=12.0, target=10.0)
    _make_open_order(db_session, "OS-JARU-2", regional="UNI JARU", elapsed_hours=1.0, target=10.0)
    _make_open_order(db_session, "OS-ARIQ", regional="UNI ARIQUEMES", elapsed_hours=1.0, target=10.0)
    db_session.commit()

    http_risk = client.get("/api/operations/in-progress/sla-risk?regionals=UNI JARU").json()
    http_breakdown = client.get("/api/operations/in-progress?group_by=city&regionals=UNI JARU").json()
    tool = mcp_tool("opr_operations_now", group_by="city", filters={"regionals": ["UNI JARU"]})

    assert tool["sla_risk"] == http_risk
    assert tool["breakdown"]["items"] == http_breakdown
    assert tool["total_in_progress"] == 2


def test_operations_now_pagina_igual_a_rota_de_os(client, db_session, mcp_tool):
    for indice in range(4):
        _make_open_order(db_session, f"OS-{indice}", regional="UNI JARU", elapsed_hours=12.0, target=10.0)
    db_session.commit()

    http = client.get("/api/operations/in-progress/orders?page=1&page_size=10&sla_risk=breached").json()
    tool = mcp_tool(
        "opr_operations_now",
        include_orders=True,
        page=1,
        page_size=10,
        sla_risk="breached",
        response_mode="full",
    )

    assert tool["orders"]["total"] == http["total"]
    assert tool["orders"]["total_pages"] == http["total_pages"]
    # Mesmo conjunto de O.S., na mesma ordem - a tool não reordena.
    assert [item["order_code"] for item in tool["orders"]["items"]] == [
        item["order_code"] for item in http["items"]
    ]


# --- tools do SGP Suporte x GET /support/opa/* --------------------------------------------------


def test_support_overview_bate_com_a_rota_da_tela(client, db_session, mcp_tool):
    _make_attendance(db_session, "AT-1", day=date(2026, 9, 2), attendant_id="A-1", tma=600, tmr=120)
    _make_attendance(db_session, "AT-2", day=date(2026, 9, 3), attendant_id="A-1", tma=900, tmr=200)
    _make_attendance(db_session, "AT-3", day=date(2026, 9, 3), attendant_id="A-2", tma=300, tmr=60)
    # Período anterior (25-31/08), pra o comparativo não ser trivialmente zero dos dois lados.
    _make_attendance(db_session, "AT-ANT", day=date(2026, 8, 27), attendant_id="A-1", tma=1200, tmr=300)
    db_session.commit()

    http = client.get(
        "/api/support/opa/overview?date_from=2026-09-01&date_to=2026-09-07&date_basis=opened_at"
    ).json()
    tool = mcp_tool("opr_support_overview", date_from="2026-09-01", date_to="2026-09-07")

    assert tool["current_period"] == http["current_period"]
    assert tool["previous_period"] == http["previous_period"]
    for campo in (
        "total_attendances",
        "closed_attendances",
        "open_attendances",
        "closure_rate",
        "average_duration_seconds",
        "average_tmr_seconds",
        "average_tmr_all_responses_seconds",
        "average_rating",
        "distinct_attendants",
        "distinct_departments",
    ):
        assert tool[campo] == http[campo], f"divergência em {campo}"
    assert tool["by_channel"] == http["by_channel"]
    assert tool["by_status"] == http["by_status"]
    assert tool["top_reasons"] == http["top_reasons"]
    assert tool["bot_human"] == http["bot_human"]


def test_support_overview_bate_com_a_rota_sob_filtro_e_closed_at(client, db_session, mcp_tool):
    _make_attendance(db_session, "AT-1", day=date(2026, 9, 2), attendant_id="A-1", tma=600, tmr=120)
    _make_attendance(db_session, "AT-2", day=date(2026, 9, 3), attendant_id="A-2", tma=900, tmr=200)
    db_session.commit()

    http = client.get(
        "/api/support/opa/overview?date_from=2026-09-01&date_to=2026-09-07"
        "&date_basis=closed_at&attendant_id=A-1"
    ).json()
    tool = mcp_tool(
        "opr_support_overview",
        date_from="2026-09-01",
        date_to="2026-09-07",
        date_basis="closed_at",
        support_filters={"attendant_id": "A-1"},
    )

    assert tool["total_attendances"] == http["total_attendances"]
    assert tool["average_duration_seconds"] == http["average_duration_seconds"]


@pytest.mark.parametrize("dimension", ["attendant", "department", "reason", "channel", "status", "customer"])
def test_support_breakdowns_bate_com_a_rota_em_cada_dimensao(client, db_session, mcp_tool, dimension):
    _make_attendance(db_session, "AT-1", day=date(2026, 9, 2), attendant_id="A-1", tma=600, tmr=120)
    _make_attendance(db_session, "AT-2", day=date(2026, 9, 3), attendant_id="A-1", tma=900, tmr=200)
    _make_attendance(db_session, "AT-3", day=date(2026, 9, 3), attendant_id="A-2", tma=300, tmr=60)
    db_session.commit()

    http = client.get(
        f"/api/support/opa/breakdowns?dimension={dimension}"
        "&date_from=2026-09-01&date_to=2026-09-07&sort_by=total&sort_dir=desc&limit=20"
    ).json()
    tool = mcp_tool(
        "opr_support_breakdowns",
        dimension=dimension,
        date_from="2026-09-01",
        date_to="2026-09-07",
        sort_by="total",
        sort_dir="desc",
        limit=20,
    )

    assert tool["dimension"] == http["dimension"]
    assert tool["total"] == http["total"]
    assert tool["items"] == http["items"]


def test_support_timeseries_bate_com_a_rota_da_tela(client, db_session, mcp_tool):
    _make_attendance(db_session, "AT-1", day=date(2026, 9, 1), attendant_id="A-1", tma=600, tmr=120)
    _make_attendance(db_session, "AT-2", day=date(2026, 9, 1), attendant_id="A-2", tma=900, tmr=200)
    _make_attendance(db_session, "AT-3", day=date(2026, 9, 3), attendant_id="A-1", tma=300, tmr=60)
    db_session.commit()

    http = client.get(
        "/api/support/opa/timeseries?date_from=2026-09-01&date_to=2026-09-05&date_basis=opened_at"
    ).json()
    tool = mcp_tool("opr_support_timeseries", date_from="2026-09-01", date_to="2026-09-05")

    assert tool["date_basis"] == http["date_basis"]
    assert tool["points"] == http["points"]
    # Inclui os dias vazios preenchidos com zero pelo backend - 5 dias, 5 pontos.
    assert len(tool["points"]) == 5


# --- somente leitura ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, kwargs",
    [
        ("opr_data_freshness", {}),
        ("opr_operations_now", {}),
        ("opr_operations_now", {"include_orders": True}),
        ("opr_support_overview", {"date_from": "2026-09-01", "date_to": "2026-09-07"}),
        ("opr_support_breakdowns", {"dimension": "attendant"}),
        ("opr_support_timeseries", {"date_from": "2026-09-01", "date_to": "2026-09-07"}),
    ],
)
def test_tools_novas_nao_escrevem_nada_no_banco(db_session, mcp_tool, name, kwargs):
    """`readOnlyHint=True` é uma promessa ao cliente MCP; este teste verifica que ela é verdade,
    contando as linhas de TODAS as tabelas antes e depois da chamada.

    Pega o que a anotação não pega: um serviço reusado que grava log, cria snapshot, marca "última
    leitura" ou dispara qualquer efeito colateral operacional."""
    from sqlalchemy import func, select

    from app.db.base import Base

    _make_open_order(db_session, "OS-RO", regional="UNI JARU", elapsed_hours=12.0, target=10.0)
    _make_attendance(db_session, "AT-RO", day=date(2026, 9, 2), attendant_id="A-1", tma=600, tmr=120)
    db_session.commit()

    def _snapshot() -> dict[str, int]:
        return {
            table.name: int(db_session.scalar(select(func.count()).select_from(table)) or 0)
            for table in Base.metadata.sorted_tables
        }

    antes = _snapshot()
    mcp_tool(name, **kwargs)
    depois = _snapshot()

    mudou = {tabela: (antes[tabela], depois[tabela]) for tabela in antes if antes[tabela] != depois[tabela]}
    assert mudou == {}, f"{name} alterou linhas em {mudou}"
