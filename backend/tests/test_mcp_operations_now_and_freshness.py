"""Tools MCP `opr_data_freshness` e `opr_operations_now` - 1o pacote de expansão da exposição
MCP, pedido do usuário em 2026-09-10.

Nenhuma das duas tem regra própria: elas expõem `operations_queries.data_freshness`,
`in_progress_sla_risk`, `in_progress_breakdown` e `in_progress_order_page`, as mesmas funções que
as rotas `GET /operations/data-freshness` e `/operations/in-progress*` chamam. Por isso os testes
aqui comparam a tool contra a função de origem (não contra um número recopiado à mão) e cobrem o
que é responsabilidade EXCLUSIVA da tool: validação de parâmetro, permissão, governança e a
serialização.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models import User, UserPermissionOverride
from app.modules.mcp_connector import server as mcp_server
from app.modules.operations import queries as operations_queries
from app.modules.operations.models import OperationImportRun, OperationOrder


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
def tool(mcp_instance, monkeypatch, db_session):
    """Devolve `tool_fn(nome)` já com sessão e usuário admin ligados."""
    monkeypatch.setattr(mcp_server, "SessionLocal", SessionLocalStub(db_session))

    def _get(name: str):
        registered = mcp_instance._tool_manager.get_tool(name)
        assert registered is not None, f"tool {name} não está registrada"
        return registered.fn

    return _get


def _make_open_order(
    db_session,
    source_order_id: str,
    *,
    regional: str = "UNI JARU",
    city: str = "Jaru",
    os_type: str = "Manutencao",
    os_subject: str = "Reparo",
    status: str = "Em execucao",
    elapsed_hours: float | None = 1.0,
    sla_target_hours: float | None = 10.0,
    responsible: str = "Tecnico Um",
) -> OperationOrder:
    order = OperationOrder(
        source="ixc",
        source_order_id=source_order_id,
        order_code=source_order_id,
        regional=regional,
        city=city,
        os_type=os_type,
        os_subject=os_subject,
        status=status,
        responsible=responsible,
        customer_name="Cliente Teste",
        customer_login="cliente.teste",
        is_closed=False,
        opened_at=datetime.now(timezone.utc) - timedelta(hours=2),
        elapsed_hours=elapsed_hours,
        sla_target_hours=sla_target_hours,
    )
    db_session.add(order)
    db_session.flush()
    return order


def _bucket_map(payload: dict) -> dict[str, int]:
    return {item["bucket"]: item["quantity"] for item in payload["sla_risk"]}


# --- opr_data_freshness -------------------------------------------------------------------------


def test_freshness_registrada_como_somente_leitura(mcp_instance):
    registered = mcp_instance._tool_manager.get_tool("opr_data_freshness")
    assert registered is not None
    assert registered.annotations.readOnlyHint is True
    assert registered.annotations.destructiveHint is False


def test_freshness_propaga_a_ultima_importacao_bem_sucedida(tool, db_session, admin_user, monkeypatch):
    _authenticate_as(monkeypatch, admin_user)
    finished = datetime.now(timezone.utc) - timedelta(minutes=30)
    db_session.add(
        OperationImportRun(
            status="completed_with_warnings",
            date_from=datetime(2026, 9, 1).date(),
            date_to=datetime(2026, 9, 10).date(),
            finished_at=finished,
        )
    )
    db_session.commit()

    payload = json.loads(tool("opr_data_freshness")())

    # Confere contra a própria função de origem, não contra valores recopiados.
    origin = operations_queries.data_freshness(db_session)
    assert payload["status"] == origin["status"] == "completed_with_warnings"
    assert payload["date_from"] == origin["date_from"].isoformat()
    assert payload["date_to"] == origin["date_to"].isoformat()
    assert payload["has_data"] is True
    # ~30 min de idade, com folga pro tempo de execução do teste.
    assert 1750 <= payload["age_seconds"] <= 1900


def test_freshness_distingue_nunca_importou_de_importacao_velha(tool, db_session, admin_user, monkeypatch):
    """Banco sem nenhuma run bem-sucedida: todos os campos de data nulos e `has_data=false`. Sem
    esse sinal, a IA leria `last_successful_import_at=null` como um erro de leitura."""
    _authenticate_as(monkeypatch, admin_user)
    db_session.commit()

    payload = json.loads(tool("opr_data_freshness")())

    assert payload["has_data"] is False
    assert payload["last_successful_import_at"] is None
    assert payload["status"] is None
    assert payload["age_seconds"] is None
    assert payload["checked_at"] is not None


def test_freshness_ignora_importacao_que_nao_terminou_bem(tool, db_session, admin_user, monkeypatch):
    _authenticate_as(monkeypatch, admin_user)
    db_session.add(
        OperationImportRun(
            status="failed",
            finished_at=datetime.now(timezone.utc),
            date_from=datetime(2026, 9, 1).date(),
            date_to=datetime(2026, 9, 10).date(),
        )
    )
    db_session.add(
        OperationImportRun(
            status="running",
            finished_at=None,
            date_from=datetime(2026, 9, 1).date(),
            date_to=datetime(2026, 9, 10).date(),
        )
    )
    db_session.commit()

    payload = json.loads(tool("opr_data_freshness")())

    assert payload["has_data"] is False


def test_freshness_respeita_o_desligamento_na_governanca(tool, db_session, admin_user, monkeypatch):
    _authenticate_as(monkeypatch, admin_user)
    _disable_endpoint(db_session, "ai.data_freshness")
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_data_freshness")()
    assert "ai.data_freshness" in str(exc.value)


def _disable_endpoint(db_session, key: str) -> None:
    """Desliga a capacidade como a tela de governança desliga, com o bump de versão - sem ele
    `resolve_effective_policy` devolve a política do cache (ver `policy.py`)."""
    from sqlalchemy import select

    from app.modules.ai_governance.models import AiEndpoint
    from app.modules.ai_governance.policy import bump_policy_version

    endpoint = db_session.scalar(select(AiEndpoint).where(AiEndpoint.key == key))
    endpoint.enabled_api = False
    endpoint.enabled_mcp = False
    endpoint.enabled_ai = False
    db_session.flush()
    bump_policy_version(db_session)


# --- opr_operations_now: resumo -----------------------------------------------------------------


def test_operations_now_registrada_como_somente_leitura(mcp_instance):
    registered = mcp_instance._tool_manager.get_tool("opr_operations_now")
    assert registered is not None
    assert registered.annotations.readOnlyHint is True
    assert registered.annotations.destructiveHint is False


def test_operations_now_reproduz_o_resumo_das_rotas_da_tela(tool, db_session, admin_user, monkeypatch):
    _authenticate_as(monkeypatch, admin_user)
    _make_open_order(db_session, "OS-1", regional="UNI JARU")
    _make_open_order(db_session, "OS-2", regional="UNI JARU")
    _make_open_order(db_session, "OS-3", regional="UNI ARIQUEMES")
    db_session.commit()

    payload = json.loads(tool("opr_operations_now")())

    assert payload["sla_risk"] == json.loads(json.dumps(operations_queries.in_progress_sla_risk(db_session, admin_user)))
    assert payload["breakdown"]["items"] == json.loads(
        json.dumps(operations_queries.in_progress_breakdown(db_session, admin_user, "regional"))
    )
    assert payload["total_in_progress"] == 3
    assert payload["orders"] is None  # include_orders=false por default


def test_operations_now_conta_cada_classificacao_de_risco(tool, db_session, admin_user, monkeypatch):
    """As cinco classificações reais da aplicação, incluindo `no_target` - que não é "tranquilo",
    é "sem meta de SLA cadastrada"."""
    _authenticate_as(monkeypatch, admin_user)
    _make_open_order(db_session, "OS-BREACHED", elapsed_hours=12.0, sla_target_hours=10.0)
    _make_open_order(db_session, "OS-CRITICAL", elapsed_hours=9.0, sla_target_hours=10.0)
    _make_open_order(db_session, "OS-ATTENTION", elapsed_hours=6.0, sla_target_hours=10.0)
    _make_open_order(db_session, "OS-ON-TRACK", elapsed_hours=1.0, sla_target_hours=10.0)
    _make_open_order(db_session, "OS-NO-TARGET", elapsed_hours=99.0, sla_target_hours=None)
    db_session.commit()

    payload = json.loads(tool("opr_operations_now")())

    assert _bucket_map(payload) == {
        "breached": 1,
        "critical": 1,
        "attention": 1,
        "on_track": 1,
        "no_target": 1,
    }
    assert payload["total_in_progress"] == 5


def test_operations_now_devolve_os_cinco_baldes_mesmo_zerados(tool, db_session, admin_user, monkeypatch):
    """Balde ausente da resposta seria lido como "não sei", não como zero - por isso os cinco
    aparecem sempre, e é a garantia que `in_progress_sla_risk` já dá."""
    _authenticate_as(monkeypatch, admin_user)
    _make_open_order(db_session, "OS-ONLY", elapsed_hours=1.0, sla_target_hours=10.0)
    db_session.commit()

    payload = json.loads(tool("opr_operations_now")())

    assert [item["bucket"] for item in payload["sla_risk"]] == [
        "breached",
        "critical",
        "attention",
        "on_track",
        "no_target",
    ]
    assert _bucket_map(payload)["breached"] == 0


def test_operations_now_sem_registros_e_consulta_valida_e_nao_erro(tool, db_session, admin_user, monkeypatch):
    _authenticate_as(monkeypatch, admin_user)
    db_session.commit()

    payload = json.loads(tool("opr_operations_now")())

    assert payload["total_in_progress"] == 0
    assert payload["breakdown"]["items"] == []
    assert all(item["quantity"] == 0 for item in payload["sla_risk"])


def test_operations_now_ignora_os_ja_fechada(tool, db_session, admin_user, monkeypatch):
    _authenticate_as(monkeypatch, admin_user)
    _make_open_order(db_session, "OS-ABERTA")
    fechada = _make_open_order(db_session, "OS-FECHADA")
    fechada.is_closed = True
    fechada.closed_at = datetime.now(timezone.utc)
    db_session.commit()

    payload = json.loads(tool("opr_operations_now")())

    assert payload["total_in_progress"] == 1


# --- opr_operations_now: filtros e validação ----------------------------------------------------


def test_operations_now_aplica_filtro_e_ecoa_o_que_aplicou(tool, db_session, admin_user, monkeypatch):
    _authenticate_as(monkeypatch, admin_user)
    _make_open_order(db_session, "OS-JARU", regional="UNI JARU")
    _make_open_order(db_session, "OS-ARIQ", regional="UNI ARIQUEMES")
    db_session.commit()

    payload = json.loads(tool("opr_operations_now")(filters={"regionals": ["UNI JARU"]}))

    assert payload["total_in_progress"] == 1
    assert payload["applied_filters"] == {"regionals": ["UNI JARU"]}
    assert payload["breakdown"]["items"] == [{"label": "UNI JARU", "quantity": 1, "percentage": 100.0}]


@pytest.mark.parametrize("group_by", ["regional", "city", "os_type", "subject", "status"])
def test_operations_now_aceita_cada_dimensao_real_de_resumo(tool, db_session, admin_user, monkeypatch, group_by):
    _authenticate_as(monkeypatch, admin_user)
    _make_open_order(db_session, "OS-1")
    db_session.commit()

    payload = json.loads(tool("opr_operations_now")(group_by=group_by))

    assert payload["breakdown"]["group_by"] == group_by
    assert len(payload["breakdown"]["items"]) == 1


def test_operations_now_rejeita_group_by_que_a_query_trataria_como_regional(tool, db_session, admin_user, monkeypatch):
    """`in_progress_breakdown` faz `allowed_groups.get(group_by, regional)`: "responsible" (que a
    tela NÃO oferece nesta superfície) viraria um agrupamento por regional com aparência de
    legítimo. A tool erra antes."""
    _authenticate_as(monkeypatch, admin_user)
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_operations_now")(group_by="responsible")
    assert "group_by inválido" in str(exc.value)


def test_operations_now_rejeita_filtro_desconhecido_em_vez_de_ignorar(tool, db_session, admin_user, monkeypatch):
    _authenticate_as(monkeypatch, admin_user)
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_operations_now")(filters={"regional": ["UNI JARU"]})  # singular, nome errado
    assert "regional" in str(exc.value)
    assert "Aceitos" in str(exc.value)


def test_operations_now_rejeita_filtro_geografico_com_mensagem_que_aponta_a_alternativa(
    tool, db_session, admin_user, monkeypatch
):
    """`near_*`/`text_filters` existem em `AiOrderFilters` mas `_dimension_conditions` não os
    aplica - aceitá-los aqui seria descartá-los em silêncio."""
    _authenticate_as(monkeypatch, admin_user)
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_operations_now")(filters={"near_latitude": -10.4, "near_longitude": -62.4, "radius_km": 5})
    message = str(exc.value)
    assert "opr_search_orders" in message


def test_operations_now_rejeita_lista_onde_espera_valor_unico(tool, db_session, admin_user, monkeypatch):
    _authenticate_as(monkeypatch, admin_user)
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_operations_now")(filters={"search": ["abc"]})
    assert "valor único" in str(exc.value)


def test_operations_now_rejeita_sla_risk_invalido(tool, db_session, admin_user, monkeypatch):
    _authenticate_as(monkeypatch, admin_user)
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_operations_now")(sla_risk="vencido", include_orders=True)
    assert "sla_risk inválido" in str(exc.value)


def test_operations_now_avisa_quando_sla_risk_nao_teria_efeito(tool, db_session, admin_user, monkeypatch):
    """`sla_risk` só recorta a lista individual. Com include_orders=false ele seria aceito e
    ignorado - a IA concluiria "há 0 vencidas" a partir de um parâmetro que nunca foi aplicado."""
    _authenticate_as(monkeypatch, admin_user)
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_operations_now")(sla_risk="breached")
    assert "include_orders" in str(exc.value)


def test_operations_now_rejeita_sort_by_que_a_query_trataria_como_opened_at(tool, db_session, admin_user, monkeypatch):
    _authenticate_as(monkeypatch, admin_user)
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_operations_now")(include_orders=True, sort_by="prioridade")
    assert "sort_by inválido" in str(exc.value)


# --- opr_operations_now: drill de O.S. ----------------------------------------------------------


def test_operations_now_pagina_as_os_individuais_e_informa_o_total(tool, db_session, admin_user, monkeypatch):
    _authenticate_as(monkeypatch, admin_user)
    for indice in range(5):
        _make_open_order(db_session, f"OS-{indice}")
    db_session.commit()

    payload = json.loads(tool("opr_operations_now")(include_orders=True, page=1, page_size=10))

    assert payload["orders"]["total"] == 5
    assert len(payload["orders"]["items"]) == 5
    assert payload["orders"]["page"] == 1
    assert payload["orders"]["total_pages"] == 1


def test_operations_now_recorta_as_os_pelo_balde_de_risco(tool, db_session, admin_user, monkeypatch):
    _authenticate_as(monkeypatch, admin_user)
    _make_open_order(db_session, "OS-BREACHED", elapsed_hours=12.0, sla_target_hours=10.0)
    _make_open_order(db_session, "OS-OK", elapsed_hours=1.0, sla_target_hours=10.0)
    db_session.commit()

    payload = json.loads(tool("opr_operations_now")(include_orders=True, sla_risk="breached"))

    assert payload["orders"]["total"] == 1
    assert payload["orders"]["items"][0]["order_code"] == "OS-BREACHED"
    assert payload["orders"]["sla_risk_filter"] == "breached"
    # Os contadores continuam do universo inteiro, não do recorte da lista.
    assert payload["total_in_progress"] == 2


def test_operations_now_summary_devolve_menos_campos_que_full(tool, db_session, admin_user, monkeypatch):
    """Mesma política de campo de `ai.order_details`: `response_mode` decide o recorte, e "summary"
    é o default aqui pra uma leitura de estado não despejar a O.S. inteira."""
    _authenticate_as(monkeypatch, admin_user)
    _make_open_order(db_session, "OS-1")
    db_session.commit()

    resumo = json.loads(tool("opr_operations_now")(include_orders=True, response_mode="summary"))
    completo = json.loads(tool("opr_operations_now")(include_orders=True, response_mode="full"))

    campos_resumo = set(resumo["orders"]["items"][0])
    campos_completo = set(completo["orders"]["items"][0])
    assert campos_resumo < campos_completo


def test_operations_now_rejeita_campo_nao_autorizado(tool, db_session, admin_user, monkeypatch):
    _authenticate_as(monkeypatch, admin_user)
    _make_open_order(db_session, "OS-1")
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_operations_now")(include_orders=True, fields=["campo_que_nao_existe"])
    assert "campo_que_nao_existe" in str(exc.value)


def test_operations_now_rejeita_page_size_fora_da_faixa(tool, db_session, admin_user, monkeypatch):
    _authenticate_as(monkeypatch, admin_user)
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_operations_now")(include_orders=True, page_size=500)
    assert "page_size" in str(exc.value)


# --- opr_operations_now: autorização ------------------------------------------------------------


def test_operations_now_exige_permissao_de_backlog(tool, db_session, monkeypatch):
    sem_permissao = User(
        name="Sem Backlog", email="sem.backlog@pytest.local", role="collaborator", active=True, password_hash="x"
    )
    db_session.add(sem_permissao)
    db_session.flush()
    db_session.commit()
    _authenticate_as(monkeypatch, sem_permissao)

    with pytest.raises(RuntimeError) as exc:
        tool("opr_operations_now")()
    assert "operations:view_backlog" in str(exc.value)


def test_operations_now_exige_permissao_extra_para_listar_as_os(tool, db_session, monkeypatch):
    """Quem vê backlog mas NÃO detalhe de O.S. recebe o resumo e não a lista individual - mesma
    dupla de permissões das rotas `/operations/in-progress` e `/in-progress/orders`.

    Montado com `UserPermissionOverride` porque nenhum papel legado tem essa combinação: hoje só
    `admin` tem `operations:view_backlog`, e `operator` tem `view_order_details` sem o backlog
    (o inverso). O override individual é o mecanismo real do sistema pra essa granularidade.
    """
    from app.core.security import permissions_for_user

    operador = User(
        name="Operador", email="operador@pytest.local", role="operator", active=True, password_hash="x"
    )
    db_session.add(operador)
    db_session.flush()
    db_session.add(
        UserPermissionOverride(user_id=operador.id, permission="operations:view_backlog", effect="grant")
    )
    db_session.add(
        UserPermissionOverride(user_id=operador.id, permission="operations:view_order_details", effect="deny")
    )
    db_session.commit()
    db_session.refresh(operador)
    permissoes = permissions_for_user(operador)
    assert "operations:view_backlog" in permissoes
    assert "operations:view_order_details" not in permissoes
    _authenticate_as(monkeypatch, operador)

    assert json.loads(tool("opr_operations_now")())["orders"] is None

    with pytest.raises(RuntimeError) as exc:
        tool("opr_operations_now")(include_orders=True)
    assert "operations:view_order_details" in str(exc.value)


def test_operations_now_respeita_o_escopo_regional_do_usuario(tool, db_session, monkeypatch):
    """`_dimension_conditions` impõe o escopo do USUÁRIO, não o filtro recebido - uma tool nova não
    pode virar porta lateral pro que a tela não mostraria."""
    gestor = User(
        name="Gestor Jaru",
        email="gestor.jaru@pytest.local",
        role="base_manager",
        active=True,
        password_hash="x",
        managed_regionals=["UNI JARU"],
    )
    db_session.add(gestor)
    db_session.flush()
    # `base_manager` não tem `operations:view_backlog` no papel legado - o override individual dá
    # só essa permissão, sem virar admin (que enxergaria todas as regionais).
    db_session.add(
        UserPermissionOverride(user_id=gestor.id, permission="operations:view_backlog", effect="grant")
    )
    _make_open_order(db_session, "OS-JARU", regional="UNI JARU")
    _make_open_order(db_session, "OS-ARIQ", regional="UNI ARIQUEMES")
    db_session.commit()
    _authenticate_as(monkeypatch, gestor)

    payload = json.loads(tool("opr_operations_now")())

    assert payload["total_in_progress"] == 1
    assert [item["label"] for item in payload["breakdown"]["items"]] == ["UNI JARU"]


def test_operations_now_respeita_o_desligamento_na_governanca(tool, db_session, admin_user, monkeypatch):
    _authenticate_as(monkeypatch, admin_user)
    _disable_endpoint(db_session, "ai.operations_now")
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_operations_now")()
    assert "ai.operations_now" in str(exc.value)
