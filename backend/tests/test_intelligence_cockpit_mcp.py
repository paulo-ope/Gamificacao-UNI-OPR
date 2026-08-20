"""F2: tool MCP `opr_publish_cockpit_content` (app/modules/mcp_connector/server.py).

Testa a tool chamando a função Python subjacente diretamente (`tool.fn`, mesmo objeto registrado
via `@mcp.tool`) - evita depender do comportamento de serialização de erro do FastMCP e testa
exatamente a mesma função que o protocolo MCP de verdade invoca. Monkeypatcha só a resolução de
usuário (`get_access_token`/`resolve_user_for_access_token`, o mecanismo real de auth do OAuth do
conector) e o `SessionLocal`, no mesmo espírito de test_opa_scheduler.py."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.modules.intelligence.models import IntelligenceCockpitContent
from app.modules.intelligence import cockpit
from app.modules.mcp_connector import server as mcp_server


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
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://test.local")
    from app.core.config import get_settings

    get_settings.cache_clear()
    server = mcp_server.build_mcp_server()
    yield server
    get_settings.cache_clear()


def _publish_tool_fn(mcp_instance):
    tool = mcp_instance._tool_manager.get_tool("opr_publish_cockpit_content")
    assert tool is not None, "tool opr_publish_cockpit_content nao esta registrada"
    return tool.fn


def _authenticate_as(monkeypatch, user):
    monkeypatch.setattr(mcp_server, "get_access_token", lambda: SimpleNamespace(subject=str(user.id)))
    monkeypatch.setattr(mcp_server, "resolve_user_for_access_token", lambda token: user)


def test_tool_is_registered_with_write_hints(mcp_instance):
    tool = mcp_instance._tool_manager.get_tool("opr_publish_cockpit_content")
    assert tool is not None
    assert tool.annotations.readOnlyHint is False
    assert tool.annotations.destructiveHint is False


def test_tool_publishes_valid_content(mcp_instance, monkeypatch, db_session, admin_user):
    cockpit.ensure_default_dashboard_profile(db_session)
    monkeypatch.setattr(mcp_server, "SessionLocal", SessionLocalStub(db_session))
    _authenticate_as(monkeypatch, admin_user)

    fn = _publish_tool_fn(mcp_instance)
    result = fn(
        content_type="AI_INSIGHT",
        title="Teste UNI Intelligence via MCP",
        body="Mensagem de validação do canal de inteligência operacional.",
        profile_key="uni-geral",
        severity="INFO",
    )

    assert "Teste UNI Intelligence via MCP" in result
    content = db_session.query(IntelligenceCockpitContent).one()
    assert content.source_type == "MCP"
    assert content.source_key == f"mcp:{admin_user.email}"
    assert content.author_user_id == admin_user.id


def test_tool_blocks_publish_without_permission(mcp_instance, monkeypatch, db_session):
    from app.models import User

    limited_user = User(name="Sem Permissao", email="sem-permissao-mcp@pytest.local", role="viewer", active=True, password_hash="x")
    db_session.add(limited_user)
    db_session.flush()

    monkeypatch.setattr(mcp_server, "SessionLocal", SessionLocalStub(db_session))
    _authenticate_as(monkeypatch, limited_user)

    fn = _publish_tool_fn(mcp_instance)
    with pytest.raises(RuntimeError, match="intelligence:publish"):
        fn(content_type="INFO", title="t", body="b")


def test_tool_rejects_invalid_content_type(mcp_instance, monkeypatch, db_session, admin_user):
    monkeypatch.setattr(mcp_server, "SessionLocal", SessionLocalStub(db_session))
    _authenticate_as(monkeypatch, admin_user)

    fn = _publish_tool_fn(mcp_instance)
    with pytest.raises(ValueError):
        fn(content_type="NAO_EXISTE", title="t", body="b")


def test_tool_cannot_write_outside_cockpit_content(mcp_instance):
    """A tool só expõe publicação de conteúdo - não existe nenhuma tool de escrita para alertas,
    O.S., agenda ou rede neste servidor (verificação estrutural: todas as OUTRAS tools continuam
    readOnlyHint=True)."""
    tools = mcp_instance._tool_manager.list_tools()
    write_tools = [t.name for t in tools if not t.annotations.readOnlyHint]
    assert write_tools == ["opr_publish_cockpit_content"]


# --- F4: opr_get_cockpit_context (somente leitura, para a analise horaria) ----------------------


def _context_tool_fn(mcp_instance):
    tool = mcp_instance._tool_manager.get_tool("opr_get_cockpit_context")
    assert tool is not None, "tool opr_get_cockpit_context nao esta registrada"
    return tool.fn


def test_context_tool_is_registered_read_only(mcp_instance):
    tool = mcp_instance._tool_manager.get_tool("opr_get_cockpit_context")
    assert tool is not None
    assert tool.annotations.readOnlyHint is True
    assert tool.annotations.destructiveHint is False
    assert tool.annotations.idempotentHint is True


def test_context_tool_requires_intelligence_read_permission(mcp_instance, monkeypatch, db_session):
    from app.models import User

    limited_user = User(name="Sem Permissao", email="sem-permissao-context@pytest.local", role="collaborator", active=True, password_hash="x")
    db_session.add(limited_user)
    db_session.flush()

    monkeypatch.setattr(mcp_server, "SessionLocal", SessionLocalStub(db_session))
    _authenticate_as(monkeypatch, limited_user)

    fn = _context_tool_fn(mcp_instance)
    with pytest.raises(RuntimeError, match="intelligence:read"):
        fn(profile_key="uni-geral")


def test_context_tool_unknown_profile_raises(mcp_instance, monkeypatch, db_session, admin_user):
    monkeypatch.setattr(mcp_server, "SessionLocal", SessionLocalStub(db_session))
    _authenticate_as(monkeypatch, admin_user)

    fn = _context_tool_fn(mcp_instance)
    with pytest.raises(ValueError, match="não encontrado"):
        fn(profile_key="nao-existe")


def test_context_tool_returns_full_global_context(mcp_instance, monkeypatch, db_session, admin_user):
    cockpit.ensure_default_dashboard_profile(db_session)
    monkeypatch.setattr(mcp_server, "SessionLocal", SessionLocalStub(db_session))
    _authenticate_as(monkeypatch, admin_user)

    fn = _context_tool_fn(mcp_instance)
    result = json.loads(fn(profile_key="uni-geral"))

    for key in ("profile", "scope", "generated_at", "overall_status", "production", "backlog", "sla", "alerts", "incidents", "content", "monitor_health", "data_freshness", "meta", "last_ai_insight"):
        assert key in result, f"chave ausente no contexto: {key}"
    assert result["scope"] == {"regionals": []}
    assert result["last_ai_insight"] is None  # nenhum AI_INSIGHT publicado ainda


def test_context_tool_regional_scope_reflects_profile(mcp_instance, monkeypatch, db_session, admin_user):
    cockpit.ensure_default_dashboard_profile(db_session)
    monkeypatch.setattr(mcp_server, "SessionLocal", SessionLocalStub(db_session))
    _authenticate_as(monkeypatch, admin_user)

    fn = _context_tool_fn(mcp_instance)
    result = json.loads(fn(profile_key="machadinho-operacional"))

    assert result["scope"] == {"regionals": ["UNI - MACHADINHO DOESTE"]}
    assert result["profile"]["key"] == "machadinho-operacional"


def test_context_tool_reflects_last_published_insight(mcp_instance, monkeypatch, db_session, admin_user):
    cockpit.ensure_default_dashboard_profile(db_session)
    monkeypatch.setattr(mcp_server, "SessionLocal", SessionLocalStub(db_session))
    _authenticate_as(monkeypatch, admin_user)

    context_fn = _context_tool_fn(mcp_instance)
    publish_fn = _publish_tool_fn(mcp_instance)

    before = json.loads(context_fn(profile_key="uni-geral"))
    assert before["last_ai_insight"] is None

    publish_fn(
        content_type="AI_INSIGHT", profile_key="uni-geral", title="Pipeline F4",
        body="Insight de teste do pipeline sem LLM.", severity="HIGH",
    )

    after = json.loads(context_fn(profile_key="uni-geral"))
    assert after["last_ai_insight"] is not None
    assert after["last_ai_insight"]["title"] == "Pipeline F4"
    assert after["last_ai_insight"]["source_type"] == "MCP"


# --- F4: pipeline completo sem LLM - contexto -> publicacao -> TV, global e regional ------------


def test_full_pipeline_context_publish_cockpit_global(mcp_instance, monkeypatch, db_session, admin_user):
    cockpit.ensure_default_dashboard_profile(db_session)
    monkeypatch.setattr(mcp_server, "SessionLocal", SessionLocalStub(db_session))
    _authenticate_as(monkeypatch, admin_user)

    context_fn = _context_tool_fn(mcp_instance)
    publish_fn = _publish_tool_fn(mcp_instance)

    context = json.loads(context_fn(profile_key="uni-geral"))
    assert context["overall_status"]["status"] in ("NORMAL", "ATTENTION", "RISK", "CRITICAL")

    publish_fn(
        content_type="AI_INSIGHT", profile_key="uni-geral", title="Analise horaria simulada",
        body=f"Status observado: {context['overall_status']['status']}.", severity="INFO",
    )

    profile = cockpit.get_profile(db_session, "uni-geral")
    payload = cockpit.build_cockpit_payload(db_session, profile)
    assert any(item["title"] == "Analise horaria simulada" for item in payload["content"])


def test_full_pipeline_context_publish_cockpit_regional_isolated(mcp_instance, monkeypatch, db_session, admin_user):
    cockpit.ensure_default_dashboard_profile(db_session)
    monkeypatch.setattr(mcp_server, "SessionLocal", SessionLocalStub(db_session))
    _authenticate_as(monkeypatch, admin_user)

    context_fn = _context_tool_fn(mcp_instance)
    publish_fn = _publish_tool_fn(mcp_instance)

    context = json.loads(context_fn(profile_key="machadinho-operacional"))
    assert context["scope"] == {"regionals": ["UNI - MACHADINHO DOESTE"]}

    publish_fn(
        content_type="AI_INSIGHT", profile_key="machadinho-operacional",
        title="Analise regional simulada", body="Insight regional de teste.", severity="INFO",
    )

    machadinho = cockpit.get_profile(db_session, "machadinho-operacional")
    executivo = cockpit.get_profile(db_session, "executivo-uni")

    machadinho_payload = cockpit.build_cockpit_payload(db_session, machadinho)
    executivo_payload = cockpit.build_cockpit_payload(db_session, executivo)

    assert any(item["title"] == "Analise regional simulada" for item in machadinho_payload["content"])
    assert not any(item["title"] == "Analise regional simulada" for item in executivo_payload["content"]), (
        "insight direcionado a machadinho-operacional nao pode vazar para outro profile"
    )
