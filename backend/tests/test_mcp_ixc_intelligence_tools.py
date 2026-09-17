"""Tools MCP do Atendimento IXC - `opr_ixc_brief`/`opr_ixc_signals` (Fase 5 do plano de evolução
analítica, 2026-09-15). Mesmo padrão de fixtures/asserts de `test_mcp_support_tools.py` - a tool
não recalcula nada, só chama `ixc_ticket_intelligence` (já testado em `test_ixc_ticket_
intelligence.py`) atrás do gate de permissão (`support:read`) e de governança (`ai.ixc_*`)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.models import User
from app.modules.mcp_connector import server as mcp_server
from app.modules.support.models import SupportIxcTicket

REGIONAL = "UNI - NOVA BRASILANDIA DOESTE"


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
def mcp_instance(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://test.local")
    get_settings.cache_clear()
    server = mcp_server.build_mcp_server()
    yield server
    get_settings.cache_clear()


def _authenticate_as(monkeypatch, user):
    monkeypatch.setattr(mcp_server, "get_access_token", lambda: SimpleNamespace(subject=str(user.id)))
    monkeypatch.setattr(mcp_server, "resolve_user_for_access_token", lambda token: user)


@pytest.fixture()
def tool(mcp_instance, monkeypatch, db_session, admin_user):
    monkeypatch.setattr(mcp_server, "SessionLocal", SessionLocalStub(db_session))
    _authenticate_as(monkeypatch, admin_user)

    def _get(name: str):
        registered = mcp_instance._tool_manager.get_tool(name)
        assert registered is not None, f"tool {name} não está registrada"
        return registered.fn

    return _get


def _disable_endpoint(db_session, key: str) -> None:
    from sqlalchemy import select

    from app.modules.ai_governance.models import AiEndpoint
    from app.modules.ai_governance.policy import bump_policy_version

    endpoint = db_session.scalar(select(AiEndpoint).where(AiEndpoint.key == key))
    endpoint.enabled_api = False
    endpoint.enabled_mcp = False
    endpoint.enabled_ai = False
    db_session.flush()
    bump_policy_version(db_session)


@pytest.mark.parametrize("name", ["opr_ixc_brief", "opr_ixc_signals"])
def test_tools_registradas_como_somente_leitura(mcp_instance, name):
    registered = mcp_instance._tool_manager.get_tool(name)
    assert registered is not None
    assert registered.annotations.readOnlyHint is True
    assert registered.annotations.destructiveHint is False


@pytest.mark.parametrize("name", ["opr_ixc_brief", "opr_ixc_signals"])
def test_tools_exigem_permissao_do_modulo(mcp_instance, monkeypatch, db_session, name):
    monkeypatch.setattr(mcp_server, "SessionLocal", SessionLocalStub(db_session))
    sem_permissao = User(
        name="Sem SGP", email="sem.sgp.ixc@pytest.local", role="collaborator", active=True, password_hash="x"
    )
    db_session.add(sem_permissao)
    db_session.flush()
    db_session.commit()
    _authenticate_as(monkeypatch, sem_permissao)

    with pytest.raises(RuntimeError) as exc:
        mcp_instance._tool_manager.get_tool(name).fn()
    assert "support:read" in str(exc.value)


@pytest.mark.parametrize("name, key", [("opr_ixc_brief", "ai.ixc_brief"), ("opr_ixc_signals", "ai.ixc_signals")])
def test_tools_respeitam_o_desligamento_na_governanca(tool, db_session, name, key):
    _disable_endpoint(db_session, key)
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool(name)()
    assert key in str(exc.value)


def test_brief_reflete_o_escopo_pedido(tool, db_session):
    row = SupportIxcTicket(
        source_id="T1", regional=REGIONAL, subject_name="Sem conexão",
        created_at=datetime(2026, 9, 14, 10, tzinfo=timezone.utc),
    )
    db_session.add(row)
    db_session.commit()

    payload = json.loads(tool("opr_ixc_brief")(regional=REGIONAL))

    assert payload["scope"] == {"type": "regional", "id": REGIONAL}
    assert payload["ticket_count"] >= 1


def test_brief_sem_regional_usa_escopo_global(tool, db_session):
    db_session.commit()

    payload = json.loads(tool("opr_ixc_brief")())

    assert payload["scope"] == {"type": "global", "id": None}


def test_signals_devolve_lista_de_sinais(tool, db_session):
    db_session.commit()

    payload = json.loads(tool("opr_ixc_signals")())

    assert "signals" in payload
    assert isinstance(payload["signals"], list)
