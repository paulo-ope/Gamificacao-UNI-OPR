"""Busca de colaborador com justificativa pendente e leitura das justificativas por regional /
colaborador / data - pedido do usuário em 2026-09-10 ("criar endpoints para o MCP e a API
conseguirem buscar colaborador com justificativa pendente de forma mais fácil ... e ela ler essas
justificativas também por regional, colaborador, data").

Cobre as três superfícies: os filtros novos no motor (fonte única), as duas rotas novas da tela e
as tools MCP - mais a lacuna de permissão que existia em `opr_management_cases_diagnostics`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import User
from app.modules.management import cases as cases_engine
from app.modules.management.models import ManagementCase, ManagementCaseComment, ManagementCaseReason


def _make_case(db_session, **overrides) -> ManagementCase:
    defaults = dict(
        case_type=cases_engine.CASE_TYPE_DAILY_BELOW,
        source_module="operations",
        reference_date=date(2026, 9, 3),
        reference_month=9,
        reference_year=2026,
        regional="UNI JARU",
        responsible_name="Joao Campo",
        metric_name=cases_engine.METRIC_DAILY_COUNT,
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


def _conditions(**kwargs) -> list:
    return cases_engine.case_filter_conditions(cases_engine.ManagementCaseFilters(**kwargs))


# --- filtros novos no motor ---------------------------------------------------------------------


def test_responsible_name_casa_a_pessoa_exata_enquanto_search_casa_parcial(db_session):
    """`search` faz ILIKE em responsável OU regional OU métrica ao mesmo tempo - buscar "ANA"
    trazia também quem não se chama Ana. `responsible_name` é o casamento exato da pessoa."""
    ana = _make_case(db_session, responsible_name="Ana Souza")
    _make_case(db_session, responsible_name="Mariana Lima")
    db_session.commit()

    exatos = db_session.scalars(
        cases_engine.select(ManagementCase).where(*_conditions(responsible_name="ana souza"))
    ).all()
    assert [item.id for item in exatos] == [ana.id]

    parciais = db_session.scalars(
        cases_engine.select(ManagementCase).where(*_conditions(search="ana"))
    ).all()
    assert len(parciais) == 2  # "Ana Souza" e "Mariana Lima" - o problema que o filtro exato resolve


def test_faixa_de_reference_date_recorta_por_dia(db_session):
    dentro = _make_case(db_session, reference_date=date(2026, 9, 3))
    _make_case(db_session, reference_date=date(2026, 9, 10))
    db_session.commit()

    rows = db_session.scalars(
        cases_engine.select(ManagementCase).where(
            *_conditions(reference_date_from=date(2026, 9, 1), reference_date_to=date(2026, 9, 5))
        )
    ).all()
    assert [item.id for item in rows] == [dentro.id]


def test_faixa_de_reference_date_e_inclusiva_nas_duas_pontas(db_session):
    inicio = _make_case(db_session, reference_date=date(2026, 9, 1))
    fim = _make_case(db_session, reference_date=date(2026, 9, 5))
    db_session.commit()

    rows = db_session.scalars(
        cases_engine.select(ManagementCase).where(
            *_conditions(reference_date_from=date(2026, 9, 1), reference_date_to=date(2026, 9, 5))
        )
    ).all()
    assert {item.id for item in rows} == {inicio.id, fim.id}


def test_pending_justification_e_awaiting_review_separam_os_dois_estados(db_session):
    pendente = _make_case(db_session, status="pending", justification_text=None)
    justificado = _make_case(db_session, status="justified", justification_text="Estava de férias.")
    db_session.commit()

    so_pendente = db_session.scalars(
        cases_engine.select(ManagementCase).where(*_conditions(pending_justification=True))
    ).all()
    assert [item.id for item in so_pendente] == [pendente.id]

    so_aguardando = db_session.scalars(
        cases_engine.select(ManagementCase).where(*_conditions(awaiting_review=True))
    ).all()
    assert [item.id for item in so_aguardando] == [justificado.id]


def test_has_justification_trata_texto_vazio_como_ausencia(db_session):
    """Um caso pode ter `justification_text=""` (string vazia, não NULL) - contar isso como
    "justificado" faria a fila de cobrança perder gente que não escreveu nada."""
    com_texto = _make_case(db_session, status="justified", justification_text="Faltou por atestado.")
    _make_case(db_session, status="pending", justification_text="")
    _make_case(db_session, status="pending", justification_text=None)
    db_session.commit()

    com = db_session.scalars(
        cases_engine.select(ManagementCase).where(*_conditions(has_justification=True))
    ).all()
    assert [item.id for item in com] == [com_texto.id]

    sem = db_session.scalars(
        cases_engine.select(ManagementCase).where(*_conditions(has_justification=False))
    ).all()
    assert len(sem) == 2


def test_min_days_pending_ignora_caso_encerrado(db_session):
    velho_aberto = _make_case(
        db_session, status="pending", created_at=datetime.now(timezone.utc) - timedelta(days=30)
    )
    _make_case(db_session, status="resolved", created_at=datetime.now(timezone.utc) - timedelta(days=30))
    _make_case(db_session, status="pending", created_at=datetime.now(timezone.utc))
    db_session.commit()

    rows = db_session.scalars(
        cases_engine.select(ManagementCase).where(*_conditions(min_days_pending=10))
    ).all()
    assert [item.id for item in rows] == [velho_aberto.id]


@pytest.mark.parametrize(
    "kwargs, trecho",
    [
        ({"pending_justification": True, "awaiting_review": True}, "mutuamente"),
        ({"pending_justification": True, "status": "resolved"}, "pending_justification"),
        ({"awaiting_review": True, "status": "pending"}, "awaiting_review"),
        ({"pending_justification": True, "has_justification": True}, "has_justification"),
        (
            {"reference_date_from": date(2026, 9, 10), "reference_date_to": date(2026, 9, 1)},
            "invertida",
        ),
        (
            {"reference_year": 2025, "reference_date_from": date(2026, 9, 1)},
            "reference_year",
        ),
    ],
)
def test_filtro_contraditorio_erra_em_vez_de_devolver_lista_vazia(kwargs, trecho):
    """Mesmo racional do aviso que já existia para status + only_open: uma combinação impossível
    que "tem sucesso" com 0 resultados é lida por quem chamou - IA inclusive - como "não há
    pendência", que é o oposto da verdade."""
    with pytest.raises(ValueError) as exc:
        _conditions(**kwargs)
    assert trecho in str(exc.value)


# --- pending_justifications_by_collaborator -----------------------------------------------------


def test_pendencias_agrupam_por_pessoa_e_regional_separadamente(db_session):
    """A mesma pessoa pode ter caso em duas regionais (ver o mapa de identidade em
    `management/models.py`). Somar as duas esconderia em qual regional está a pendência."""
    _make_case(db_session, responsible_name="Joao Campo", regional="UNI JARU")
    _make_case(db_session, responsible_name="Joao Campo", regional="UNI JARU")
    _make_case(db_session, responsible_name="Joao Campo", regional="UNI ARIQUEMES")
    db_session.commit()

    result = cases_engine.pending_justifications_by_collaborator(db_session, [])

    assert result["total_collaborators"] == 2
    assert result["total_cases"] == 3
    por_regional = {item["regional"]: item for item in result["items"]}
    assert por_regional["UNI JARU"]["pending_cases"] == 2
    assert por_regional["UNI ARIQUEMES"]["pending_cases"] == 1


def test_pendencias_contam_status_idade_e_ids_dos_casos_abertos(db_session, admin_user):
    aberto_antigo = _make_case(
        db_session,
        status="pending",
        reference_date=date(2026, 8, 1),
        created_at=datetime.now(timezone.utc) - timedelta(days=12),
        due_date=date.today() - timedelta(days=2),
        supervisor_user_id=admin_user.id,
    )
    justificado = _make_case(
        db_session,
        status="justified",
        reference_date=date(2026, 9, 3),
        justification_text="Equipe reduzida.",
        justified_at=datetime.now(timezone.utc),
    )
    _make_case(db_session, status="resolved", reference_date=date(2026, 7, 1))
    db_session.commit()

    item = cases_engine.pending_justifications_by_collaborator(db_session, [])["items"][0]

    assert item["responsible_name"] == "Joao Campo"
    assert item["total_cases"] == 3
    assert item["open_cases"] == 2
    assert item["pending_cases"] == 1
    assert item["justified_cases"] == 1
    assert item["closed_cases"] == 1
    assert item["overdue_cases"] == 1
    assert item["high_severity_open"] == 2
    assert item["oldest_pending_date"] == date(2026, 8, 1)
    assert item["max_days_pending"] >= 12
    assert item["supervisor_name"] == admin_user.name
    assert item["last_justified_at"] is not None
    # Só os abertos entram na lista de ids - o encerrado não é pendência de ninguém.
    assert set(item["open_case_ids"]) == {aberto_antigo.id, justificado.id}


def test_pendencias_ordenam_atrasado_antes_do_resto(db_session):
    _make_case(db_session, responsible_name="Sem Atraso", regional="UNI JARU")
    _make_case(
        db_session,
        responsible_name="Com Atraso",
        regional="UNI JARU",
        due_date=date.today() - timedelta(days=3),
    )
    db_session.commit()

    result = cases_engine.pending_justifications_by_collaborator(db_session, [])

    assert result["items"][0]["responsible_name"] == "Com Atraso"


def test_pendencias_sinalizam_truncamento_em_vez_de_cortar_em_silencio(db_session):
    for indice in range(3):
        _make_case(db_session, responsible_name=f"Pessoa {indice}", regional="UNI JARU")
    db_session.commit()

    result = cases_engine.pending_justifications_by_collaborator(db_session, [], limit=2)

    assert len(result["items"]) == 2
    assert result["total_collaborators"] == 3
    assert result["truncated"] is True


def test_pendencias_respeitam_o_recorte_de_filtro(db_session):
    _make_case(db_session, responsible_name="Do Dia", reference_date=date(2026, 9, 3))
    _make_case(db_session, responsible_name="De Outro Dia", reference_date=date(2026, 9, 20))
    db_session.commit()

    conditions = _conditions(reference_date_from=date(2026, 9, 1), reference_date_to=date(2026, 9, 5))
    result = cases_engine.pending_justifications_by_collaborator(db_session, conditions)

    assert [item["responsible_name"] for item in result["items"]] == ["Do Dia"]


# --- justification_rows -------------------------------------------------------------------------


def test_justificativas_trazem_texto_motivo_e_decisao_da_matriz(db_session, admin_user):
    reason = ManagementCaseReason(name="Ausência justificada", active=True, requires_description=False)
    db_session.add(reason)
    db_session.flush()
    case = _make_case(
        db_session,
        status="resolved",
        reason_id=reason.id,
        justification_text="Colaborador em treinamento na matriz.",
        action_plan="Repor produção na semana seguinte.",
        justified_at=datetime.now(timezone.utc),
        reviewed_by=admin_user.id,
        reviewed_at=datetime.now(timezone.utc),
        supervisor_user_id=admin_user.id,
    )
    db_session.commit()

    result = cases_engine.justification_rows(db_session, [])

    assert result["total"] == 1
    item = result["items"][0]
    assert item["case_id"] == case.id
    assert item["reason_name"] == "Ausência justificada"
    assert item["justification_text"] == "Colaborador em treinamento na matriz."
    assert item["action_plan"] == "Repor produção na semana seguinte."
    assert item["supervisor_name"] == admin_user.name
    # Supervisor e revisor são duas FKs distintas pra `users` - sem o alias, o join devolveria o
    # nome errado numa das duas colunas.
    assert item["reviewer_name"] == admin_user.name
    assert item["is_overdue"] is False
    assert item["comments"] is None  # não foi pedido include_comments


def test_justificativas_pagina_de_verdade_e_reporta_o_total(db_session):
    for dia in range(1, 6):
        _make_case(db_session, reference_date=date(2026, 9, dia))
    db_session.commit()

    primeira = cases_engine.justification_rows(db_session, [], page=1, page_size=2)
    segunda = cases_engine.justification_rows(db_session, [], page=2, page_size=2)

    assert primeira["total"] == segunda["total"] == 5
    assert len(primeira["items"]) == len(segunda["items"]) == 2
    # Mais recente primeiro, e sem repetir linha entre as páginas.
    assert primeira["items"][0]["reference_date"] == date(2026, 9, 5)
    assert {item["case_id"] for item in primeira["items"]}.isdisjoint(
        {item["case_id"] for item in segunda["items"]}
    )


def test_justificativas_incluem_comentarios_quando_pedido(db_session, admin_user):
    case = _make_case(db_session, status="justified", justification_text="Justificado.")
    db_session.add(
        ManagementCaseComment(case_id=case.id, user_id=admin_user.id, comment="Falta detalhar o plano.")
    )
    db_session.commit()

    sem = cases_engine.justification_rows(db_session, [])["items"][0]
    assert sem["comment_count"] == 1
    assert sem["comments"] is None

    com = cases_engine.justification_rows(db_session, [], include_comments=True)["items"][0]
    assert [comment["comment"] for comment in com["comments"]] == ["Falta detalhar o plano."]
    assert com["comments"][0]["author_name"] == admin_user.name


# --- rotas da tela ------------------------------------------------------------------------------


def test_rota_pending_by_collaborator_recorta_por_regional_e_data(client, db_session):
    _make_case(db_session, responsible_name="Joao Jaru", regional="UNI JARU", reference_date=date(2026, 9, 3))
    _make_case(db_session, responsible_name="Maria Ariquemes", regional="UNI ARIQUEMES", reference_date=date(2026, 9, 3))
    _make_case(db_session, responsible_name="Joao Jaru", regional="UNI JARU", reference_date=date(2026, 12, 1))
    db_session.commit()

    response = client.get(
        "/api/management/cases/pending-by-collaborator",
        params={"regional": "UNI JARU", "reference_date_from": "2026-09-01", "reference_date_to": "2026-09-30"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_collaborators"] == 1
    assert body["items"][0]["responsible_name"] == "Joao Jaru"
    assert body["items"][0]["pending_cases"] == 1


def test_rota_justifications_filtra_por_colaborador_exato(client, db_session):
    _make_case(db_session, responsible_name="Ana Souza", status="justified", justification_text="Motivo da Ana.")
    _make_case(db_session, responsible_name="Mariana Lima", status="justified", justification_text="Motivo da Mariana.")
    db_session.commit()

    response = client.get(
        "/api/management/cases/justifications",
        params={"responsible_name": "Ana Souza", "has_justification": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["justification_text"] == "Motivo da Ana."


def test_rota_justifications_devolve_422_em_filtro_contraditorio(client, db_session):
    response = client.get(
        "/api/management/cases/justifications",
        params={"pending_justification": "true", "has_justification": "true"},
    )
    assert response.status_code == 422
    assert "has_justification" in response.json()["detail"]


def test_rotas_novas_nao_colidem_com_a_rota_de_caso_por_id(client, db_session):
    """`/cases/{case_id}` é declarada depois das duas estáticas - se a ordem inverter, "justifications"
    cairia no path param e viraria 422 de tipo."""
    case = _make_case(db_session)
    db_session.commit()

    assert client.get("/api/management/cases/justifications").status_code == 200
    assert client.get("/api/management/cases/pending-by-collaborator").status_code == 200
    assert client.get(f"/api/management/cases/{case.id}").json()["id"] == case.id


def test_escopo_de_visibilidade_vale_nas_rotas_novas(client, db_session):
    """Supervisor sem `management:review` só enxerga a própria regional - a rota nova não pode ser
    uma porta lateral pro que a tela não mostraria."""
    from app.core.security import get_current_user
    from app.main import app

    # `base_manager` tem `management:read` mas NÃO `management:review` - exatamente o perfil que o
    # escopo por regional precisa limitar (a matriz, com review, enxerga tudo por definição).
    supervisor = User(
        name="Supervisor Jaru",
        email="sup.jaru@pytest.local",
        role="base_manager",
        active=True,
        password_hash="x",
        managed_regionals=["UNI JARU"],
    )
    db_session.add(supervisor)
    db_session.flush()
    _make_case(db_session, responsible_name="Joao Jaru", regional="UNI JARU")
    _make_case(db_session, responsible_name="Maria Ariquemes", regional="UNI ARIQUEMES")
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: supervisor
    try:
        body = client.get("/api/management/cases/pending-by-collaborator").json()
        assert [item["regional"] for item in body["items"]] == ["UNI JARU"]

        justificativas = client.get("/api/management/cases/justifications").json()
        assert {item["regional"] for item in justificativas["items"]} == {"UNI JARU"}
    finally:
        app.dependency_overrides[get_current_user] = lambda: db_session.get(User, 1)


# --- tools MCP ----------------------------------------------------------------------------------


@pytest.fixture()
def mcp_server(monkeypatch):
    from app.core.config import get_settings
    from app.modules.mcp_connector.server import build_mcp_server

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://operacao.souuni.com")
    get_settings.cache_clear()
    try:
        yield build_mcp_server()
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    "tool_name",
    ["opr_management_pending_justifications", "opr_management_justifications", "opr_management_cases"],
)
def test_tools_de_gestao_estao_registradas_como_somente_leitura(mcp_server, tool_name):
    tool = mcp_server._tool_manager.get_tool(tool_name)
    assert tool is not None
    assert tool.annotations.readOnlyHint is True
    assert tool.annotations.destructiveHint is False


@pytest.mark.parametrize(
    "tool_name",
    [
        "opr_management_pending_justifications",
        "opr_management_justifications",
        "opr_management_cases",
        "opr_management_cases_diagnostics",
    ],
)
def test_tools_de_gestao_aceitam_o_recorte_por_colaborador_e_data(mcp_server, tool_name):
    """O pedido era justamente "por regional, colaborador, data" - se um dos parâmetros faltar no
    schema da tool, o Claude não tem como pedir esse recorte."""
    schema = mcp_server._tool_manager.get_tool(tool_name).parameters["properties"]
    assert {"regional", "responsible_name", "reference_date_from", "reference_date_to"} <= set(schema)


def test_diagnostico_mcp_passou_a_exigir_permissao_do_modulo(mcp_server, db_session, monkeypatch):
    """Achado real desta rodada: `opr_management_cases_diagnostics` só exigia token OAuth válido -
    nem `management:read`, nem o gate de governança de IA (que é o botão pelo qual o admin
    desligaria a capacidade). As outras tools de gestão já checavam."""
    from app.modules.mcp_connector import server as server_module

    sem_permissao = User(
        name="Sem Gestão", email="sem.gestao@pytest.local", role="ai_service", active=True, password_hash="x"
    )
    db_session.add(sem_permissao)
    db_session.flush()
    monkeypatch.setattr(server_module, "_current_user", lambda: sem_permissao)

    fn = mcp_server._tool_manager.get_tool("opr_management_cases_diagnostics").fn
    with pytest.raises(RuntimeError) as exc:
        fn()
    assert "management:read" in str(exc.value)
