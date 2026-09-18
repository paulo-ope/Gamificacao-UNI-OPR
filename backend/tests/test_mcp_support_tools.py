"""Tools MCP do SGP Suporte / OPA Suite - `opr_support_overview`, `opr_support_breakdowns` e
`opr_support_timeseries`, 1o pacote de expansão da exposição MCP (pedido do usuário em
2026-09-10). Até aqui o módulo tinha 23 rotas na tela e nenhuma tool.

Nenhuma métrica é recalculada: as tools chamam `opa_overview_service.expanded_overview`,
`daily_timeseries` e `support_router._opa_breakdown_rows`, as MESMAS funções das rotas
`/support/opa/overview`, `/opa/timeseries` e `/opa/breakdowns`. Os testes comparam a resposta da
tool contra a função de origem (TMA/TMR, comparativo de período) e cobrem o que é da tool:
validação de parâmetro, permissão `support:read`, governança e o contrato de período/fuso.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models import User
from app.modules.mcp_connector import server as mcp_server
from app.modules.support import opa_overview_service
from app.modules.support.models import SupportOpaAttendance
from app.modules.support.opa_filters import SUPPORT_TIMEZONE, OpaAttendanceFilters


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


def _local_noon(day: date) -> datetime:
    """Meio-dia LOCAL (America/Porto_Velho) convertido pra UTC - o dado é persistido em UTC e o
    filtro de período interpreta o dia no fuso operacional."""
    return datetime.combine(day, time(12, 0), tzinfo=SUPPORT_TIMEZONE).astimezone(timezone.utc)


def _make_attendance(
    db_session,
    source_id: str,
    *,
    day: date,
    closed: bool = True,
    attendant_id: str = "A-1",
    attendant_name: str = "Atendente Um",
    department_id: str = "D-1",
    department_name: str = "Suporte N1",
    reason_id: str = "R-1",
    reason_name: str = "Sem conexão",
    channel: str = "whatsapp",
    status: str = "encerrado",
    customer_id: str = "C-1",
    customer_name: str = "Cliente Um",
    tma_seconds: int | None = 600,
    tmr_seconds: int | None = 120,
    tmr_all_responses_seconds: int | None = 90,
    rating: float | None = 5.0,
) -> SupportOpaAttendance:
    opened_at = _local_noon(day)
    item = SupportOpaAttendance(
        source_id=source_id,
        protocol=f"P-{source_id}",
        customer_id=customer_id,
        customer_name=customer_name,
        attendant_id=attendant_id,
        attendant_name=attendant_name,
        department_id=department_id,
        department_name=department_name,
        reason_id=reason_id,
        reason_name=reason_name,
        channel=channel,
        status=status,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(seconds=tma_seconds or 0) if closed else None,
        first_response_at=opened_at + timedelta(seconds=tmr_seconds or 0) if tmr_seconds else None,
        rating=rating,
        tma_seconds=tma_seconds if closed else None,
        tmr_seconds=tmr_seconds,
        tmr_all_responses_seconds=tmr_all_responses_seconds,
    )
    db_session.add(item)
    db_session.flush()
    return item


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


# --- registro e permissão -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["opr_support_overview", "opr_support_breakdowns", "opr_support_timeseries"]
)
def test_tools_registradas_como_somente_leitura(mcp_instance, name):
    registered = mcp_instance._tool_manager.get_tool(name)
    assert registered is not None
    assert registered.annotations.readOnlyHint is True
    assert registered.annotations.destructiveHint is False


@pytest.mark.parametrize(
    "name, kwargs",
    [
        ("opr_support_overview", {"date_from": "2026-09-01", "date_to": "2026-09-07"}),
        ("opr_support_breakdowns", {"dimension": "attendant"}),
        ("opr_support_timeseries", {"date_from": "2026-09-01", "date_to": "2026-09-07"}),
    ],
)
def test_tools_exigem_permissao_do_modulo(mcp_instance, monkeypatch, db_session, name, kwargs):
    """`support:read` é a MESMA permissão que o router do módulo exige em todas as rotas - a tool
    não pode ser uma porta lateral pra quem não tem acesso ao SGP na tela."""
    monkeypatch.setattr(mcp_server, "SessionLocal", SessionLocalStub(db_session))
    sem_permissao = User(
        name="Sem SGP", email="sem.sgp@pytest.local", role="collaborator", active=True, password_hash="x"
    )
    db_session.add(sem_permissao)
    db_session.flush()
    db_session.commit()
    _authenticate_as(monkeypatch, sem_permissao)

    with pytest.raises(RuntimeError) as exc:
        mcp_instance._tool_manager.get_tool(name).fn(**kwargs)
    assert "support:read" in str(exc.value)


@pytest.mark.parametrize(
    "name, key, kwargs",
    [
        ("opr_support_overview", "ai.support_overview", {"date_from": "2026-09-01", "date_to": "2026-09-07"}),
        ("opr_support_breakdowns", "ai.support_breakdowns", {"dimension": "attendant"}),
        ("opr_support_timeseries", "ai.support_timeseries", {"date_from": "2026-09-01", "date_to": "2026-09-07"}),
    ],
)
def test_tools_respeitam_o_desligamento_na_governanca(tool, db_session, name, key, kwargs):
    _disable_endpoint(db_session, key)
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool(name)(**kwargs)
    assert key in str(exc.value)


# --- opr_support_overview -----------------------------------------------------------------------


def test_overview_reproduz_as_metricas_da_tela(tool, db_session):
    for indice in range(3):
        _make_attendance(db_session, f"AT-{indice}", day=date(2026, 9, 3), tma_seconds=600, tmr_seconds=120)
    _make_attendance(db_session, "AT-ABERTO", day=date(2026, 9, 4), closed=False)
    db_session.commit()

    payload = json.loads(tool("opr_support_overview")(date_from="2026-09-01", date_to="2026-09-07"))

    origin = opa_overview_service.expanded_overview(
        db_session,
        OpaAttendanceFilters(date_from=date(2026, 9, 1), date_to=date(2026, 9, 7), date_basis="opened_at"),
    )
    assert payload["total_attendances"]["current"] == origin["total_attendances"]["current"] == 4
    assert payload["closed_attendances"]["current"] == 3
    assert payload["open_attendances"]["current"] == 1
    # TMA e TMR em segundos, iguais aos da origem.
    assert payload["average_duration_seconds"]["current"] == origin["average_duration_seconds"]["current"] == 600.0
    assert payload["average_tmr_seconds"]["current"] == origin["average_tmr_seconds"]["current"] == 120.0
    assert payload["date_basis"] == "opened_at"


def test_overview_deriva_o_periodo_anterior_de_mesma_duracao(tool, db_session):
    """O comparativo não é parâmetro: é o período imediatamente anterior de mesma duração, com os
    mesmos filtros. 01-07/09 (7 dias) => 25-31/08."""
    _make_attendance(db_session, "AT-ATUAL", day=date(2026, 9, 3))
    _make_attendance(db_session, "AT-ANTERIOR-1", day=date(2026, 8, 27))
    _make_attendance(db_session, "AT-ANTERIOR-2", day=date(2026, 8, 28))
    db_session.commit()

    payload = json.loads(tool("opr_support_overview")(date_from="2026-09-01", date_to="2026-09-07"))

    assert payload["current_period"] == {"date_from": "2026-09-01", "date_to": "2026-09-07"}
    assert payload["previous_period"] == {"date_from": "2026-08-25", "date_to": "2026-08-31"}
    assert payload["total_attendances"]["current"] == 1
    assert payload["total_attendances"]["previous"] == 2
    # Nomes reais de `metric_comparison`: absolute_change / percentage_change.
    assert payload["total_attendances"]["absolute_change"] == -1
    assert payload["total_attendances"]["percentage_change"] == -50.0


def test_overview_respeita_o_dia_local_e_nao_utc(tool, db_session):
    """23h local de 30/09 é 03h UTC de 01/10. Se o período fosse interpretado em UTC, este
    atendimento cairia fora do filtro de setembro."""
    late = datetime.combine(date(2026, 9, 30), time(23, 30), tzinfo=SUPPORT_TIMEZONE).astimezone(timezone.utc)
    assert late.date() == date(2026, 10, 1), "pré-condição: o instante já virou o dia em UTC"
    item = _make_attendance(db_session, "AT-VIRADA", day=date(2026, 9, 30))
    item.opened_at = late
    item.closed_at = late + timedelta(seconds=600)
    db_session.commit()

    payload = json.loads(tool("opr_support_overview")(date_from="2026-09-24", date_to="2026-09-30"))

    assert payload["total_attendances"]["current"] == 1


def test_overview_com_date_basis_closed_at_exclui_atendimento_aberto(tool, db_session):
    _make_attendance(db_session, "AT-FECHADO", day=date(2026, 9, 3), closed=True)
    _make_attendance(db_session, "AT-ABERTO", day=date(2026, 9, 3), closed=False)
    db_session.commit()

    por_abertura = json.loads(tool("opr_support_overview")(date_from="2026-09-01", date_to="2026-09-07"))
    por_encerramento = json.loads(
        tool("opr_support_overview")(date_from="2026-09-01", date_to="2026-09-07", date_basis="closed_at")
    )

    assert por_abertura["total_attendances"]["current"] == 2
    # `closed_at` é NULL no atendimento aberto - ele não existe nesse recorte, por definição.
    assert por_encerramento["total_attendances"]["current"] == 1


def test_overview_sem_dados_devolve_zero_e_media_nula(tool, db_session):
    """Consulta válida sem registros: contadores em zero, MÉDIAS em `null`. Média zero diria
    "o TMA foi de 0 segundos", que é falso."""
    db_session.commit()

    payload = json.loads(tool("opr_support_overview")(date_from="2026-09-01", date_to="2026-09-07"))

    assert payload["total_attendances"]["current"] == 0
    assert payload["average_duration_seconds"]["current"] is None
    assert payload["average_tmr_seconds"]["current"] is None


def test_overview_aplica_filtro_do_modulo(tool, db_session):
    _make_attendance(db_session, "AT-A1", day=date(2026, 9, 3), attendant_id="A-1")
    _make_attendance(db_session, "AT-A2", day=date(2026, 9, 3), attendant_id="A-2")
    db_session.commit()

    payload = json.loads(
        tool("opr_support_overview")(
            date_from="2026-09-01", date_to="2026-09-07", support_filters={"attendant_id": "A-1"}
        )
    )

    assert payload["total_attendances"]["current"] == 1


def test_overview_aceita_varios_ids_separados_por_virgula(tool, db_session):
    """`_selected_values` do módulo aceita "A-1,A-2" numa única string, em OU - preservado aqui."""
    _make_attendance(db_session, "AT-A1", day=date(2026, 9, 3), attendant_id="A-1")
    _make_attendance(db_session, "AT-A2", day=date(2026, 9, 3), attendant_id="A-2")
    _make_attendance(db_session, "AT-A3", day=date(2026, 9, 3), attendant_id="A-3")
    db_session.commit()

    payload = json.loads(
        tool("opr_support_overview")(
            date_from="2026-09-01", date_to="2026-09-07", support_filters={"attendant_id": "A-1,A-2"}
        )
    )

    assert payload["total_attendances"]["current"] == 2


def test_overview_rejeita_periodo_acima_do_teto_do_modulo(tool, db_session):
    """32 dias é o teto real de `validate_opa_period` - a tool preserva a regra e a mensagem."""
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_support_overview")(date_from="2026-01-01", date_to="2026-03-01")
    assert "32 dias" in str(exc.value)


def test_overview_rejeita_periodo_invertido(tool, db_session):
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_support_overview")(date_from="2026-09-07", date_to="2026-09-01")
    assert "data inicial" in str(exc.value).lower()


def test_overview_rejeita_date_basis_invalido(tool, db_session):
    """`apply_opa_attendance_filters` faz `DATE_BASIS_COLUMNS.get(basis, opened_at)` - um valor
    errado viraria "opened_at" em silêncio e devolveria um recorte diferente do pedido."""
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_support_overview")(date_from="2026-09-01", date_to="2026-09-07", date_basis="finished_at")
    assert "date_basis inválido" in str(exc.value)


def test_overview_rejeita_filtro_desconhecido(tool, db_session):
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_support_overview")(
            date_from="2026-09-01", date_to="2026-09-07", support_filters={"atendente": "A-1"}
        )
    assert "atendente" in str(exc.value)
    assert "Aceitos" in str(exc.value)


def test_overview_avisa_quando_periodo_vai_no_dicionario_de_filtros(tool, db_session):
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_support_overview")(
            date_from="2026-09-01", date_to="2026-09-07", support_filters={"date_from": "2026-09-02"}
        )
    assert "parâmetros próprios da tool" in str(exc.value)


def test_overview_data_malformada_erra_com_mensagem_de_formato(tool, db_session):
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_support_overview")(date_from="01/09/2026", date_to="2026-09-07")
    assert "AAAA-MM-DD" in str(exc.value)


# --- opr_support_breakdowns ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "dimension, esperado",
    [
        ("attendant", "Atendente Um"),
        ("department", "Suporte N1"),
        ("reason", "Sem conexão"),
        ("channel", "whatsapp"),
        ("status", "encerrado"),
        ("customer", "Cliente Um"),
    ],
)
def test_breakdown_cobre_cada_dimensao_real(tool, db_session, dimension, esperado):
    _make_attendance(db_session, "AT-1", day=date(2026, 9, 3))
    _make_attendance(db_session, "AT-2", day=date(2026, 9, 3))
    db_session.commit()

    payload = json.loads(
        tool("opr_support_breakdowns")(dimension=dimension, date_from="2026-09-01", date_to="2026-09-07")
    )

    assert payload["dimension"] == dimension
    assert payload["total"] == 2
    assert payload["items"][0]["label"] == esperado
    assert payload["items"][0]["total"] == 2


def test_breakdown_rejeita_dimensao_nao_suportada(tool, db_session):
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_support_breakdowns")(dimension="regional")
    assert "Dimensão de breakdown inválida" in str(exc.value)


def test_breakdown_rejeita_ordenacao_nao_suportada(tool, db_session):
    _make_attendance(db_session, "AT-1", day=date(2026, 9, 3))
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_support_breakdowns")(dimension="attendant", sort_by="tmr")
    assert "Campo de ordenação inválido" in str(exc.value)


def test_breakdown_ordena_e_limita_preservando_o_universo_no_total(tool, db_session):
    """`total` é o universo INTEIRO do recorte, não a soma das linhas devolvidas - sem isso, um
    top 1 pareceria dizer que só existe um atendente."""
    _make_attendance(db_session, "AT-1", day=date(2026, 9, 3), attendant_id="A-1", attendant_name="Ana")
    _make_attendance(db_session, "AT-2", day=date(2026, 9, 3), attendant_id="A-1", attendant_name="Ana")
    _make_attendance(db_session, "AT-3", day=date(2026, 9, 3), attendant_id="A-2", attendant_name="Bruno")
    db_session.commit()

    payload = json.loads(
        tool("opr_support_breakdowns")(
            dimension="attendant", date_from="2026-09-01", date_to="2026-09-07", limit=1
        )
    )

    assert payload["total"] == 3
    assert payload["limit"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["label"] == "Ana"
    assert payload["items"][0]["total"] == 2


def test_breakdown_inverte_a_ordenacao_com_sort_dir(tool, db_session):
    _make_attendance(db_session, "AT-1", day=date(2026, 9, 3), attendant_id="A-1", attendant_name="Ana")
    _make_attendance(db_session, "AT-2", day=date(2026, 9, 3), attendant_id="A-1", attendant_name="Ana")
    _make_attendance(db_session, "AT-3", day=date(2026, 9, 3), attendant_id="A-2", attendant_name="Bruno")
    db_session.commit()

    payload = json.loads(
        tool("opr_support_breakdowns")(
            dimension="attendant", date_from="2026-09-01", date_to="2026-09-07", sort_dir="asc"
        )
    )

    assert [item["label"] for item in payload["items"]] == ["Bruno", "Ana"]


def test_breakdown_traz_comparativo_por_linha_quando_ha_periodo(tool, db_session):
    _make_attendance(db_session, "AT-ATUAL", day=date(2026, 9, 3), attendant_id="A-1")
    _make_attendance(db_session, "AT-ANTERIOR", day=date(2026, 8, 27), attendant_id="A-1")
    _make_attendance(db_session, "AT-ANTERIOR-2", day=date(2026, 8, 28), attendant_id="A-1")
    db_session.commit()

    payload = json.loads(
        tool("opr_support_breakdowns")(dimension="attendant", date_from="2026-09-01", date_to="2026-09-07")
    )

    item = payload["items"][0]
    assert item["total"] == 1
    assert item["previous_total"] == 2
    assert item["total_change"] == -1


def test_breakdown_sem_periodo_agrega_o_historico_sem_comparativo(tool, db_session):
    """Período é opcional aqui (ao contrário do overview) - sem ele não existe período anterior de
    que comparar, e as colunas de comparação ficam zeradas."""
    _make_attendance(db_session, "AT-1", day=date(2026, 9, 3))
    _make_attendance(db_session, "AT-2", day=date(2025, 1, 15))
    db_session.commit()

    payload = json.loads(tool("opr_support_breakdowns")(dimension="attendant"))

    assert payload["total"] == 2
    assert payload["items"][0]["total"] == 2
    assert payload["items"][0]["previous_total"] == 0


def test_breakdown_sem_registros_e_consulta_valida(tool, db_session):
    db_session.commit()

    payload = json.loads(
        tool("opr_support_breakdowns")(dimension="attendant", date_from="2026-09-01", date_to="2026-09-07")
    )

    assert payload["total"] == 0
    assert payload["items"] == []


def test_breakdown_rejeita_limit_fora_da_faixa(tool, db_session):
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_support_breakdowns")(dimension="attendant", limit=500)
    assert "limit" in str(exc.value)


def test_breakdown_combina_filtros(tool, db_session):
    _make_attendance(db_session, "AT-1", day=date(2026, 9, 3), attendant_id="A-1", channel="whatsapp")
    _make_attendance(db_session, "AT-2", day=date(2026, 9, 3), attendant_id="A-1", channel="telefone")
    _make_attendance(db_session, "AT-3", day=date(2026, 9, 3), attendant_id="A-2", channel="whatsapp")
    db_session.commit()

    payload = json.loads(
        tool("opr_support_breakdowns")(
            dimension="attendant",
            date_from="2026-09-01",
            date_to="2026-09-07",
            support_filters={"channel": "whatsapp", "attendant_id": "A-1"},
        )
    )

    assert payload["total"] == 1
    assert payload["items"][0]["total"] == 1


# --- opr_support_timeseries ---------------------------------------------------------------------


def test_timeseries_reproduz_a_serie_da_tela(tool, db_session):
    _make_attendance(db_session, "AT-1", day=date(2026, 9, 1))
    _make_attendance(db_session, "AT-2", day=date(2026, 9, 1))
    _make_attendance(db_session, "AT-3", day=date(2026, 9, 3))
    db_session.commit()

    payload = json.loads(tool("opr_support_timeseries")(date_from="2026-09-01", date_to="2026-09-03"))

    origin = opa_overview_service.daily_timeseries(
        db_session,
        OpaAttendanceFilters(date_from=date(2026, 9, 1), date_to=date(2026, 9, 3), date_basis="opened_at"),
    )
    assert [point["total"] for point in payload["points"]] == [point["total"] for point in origin] == [2, 0, 1]
    assert payload["date_basis"] == "opened_at"
    assert payload["date_from"] == "2026-09-01"


def test_timeseries_preenche_dia_vazio_com_zero_mas_media_nula(tool, db_session):
    """Comportamento deliberado do backend: um buraco no eixo esconderia o dia parado. Mas a MÉDIA
    do dia vazio é `null`, não zero - não havia nada de que tirar média."""
    _make_attendance(db_session, "AT-1", day=date(2026, 9, 1), tma_seconds=600)
    db_session.commit()

    payload = json.loads(tool("opr_support_timeseries")(date_from="2026-09-01", date_to="2026-09-03"))

    assert len(payload["points"]) == 3
    vazio = payload["points"][1]
    assert vazio["day"] == "2026-09-02"
    assert vazio["total"] == 0
    assert vazio["closed"] == 0
    assert vazio["average_duration_seconds"] is None
    assert vazio["average_tmr_seconds"] is None


def test_timeseries_um_ponto_por_dia_do_periodo_inteiro(tool, db_session):
    db_session.commit()

    payload = json.loads(tool("opr_support_timeseries")(date_from="2026-09-01", date_to="2026-09-07"))

    assert [point["day"] for point in payload["points"]] == [
        f"2026-09-0{dia}" for dia in range(1, 8)
    ]
    assert all(point["total"] == 0 for point in payload["points"])


def test_timeseries_usa_o_dia_local_para_bucketizar(tool, db_session):
    """23h30 local de 01/09 é 03h30 UTC de 02/09. O ponto tem que cair em 01/09 (dia local), senão
    a série da tool discordaria da série da tela."""
    item = _make_attendance(db_session, "AT-VIRADA", day=date(2026, 9, 1))
    late = datetime.combine(date(2026, 9, 1), time(23, 30), tzinfo=SUPPORT_TIMEZONE).astimezone(timezone.utc)
    item.opened_at = late
    item.closed_at = late + timedelta(seconds=600)
    db_session.commit()

    payload = json.loads(tool("opr_support_timeseries")(date_from="2026-09-01", date_to="2026-09-02"))

    por_dia = {point["day"]: point["total"] for point in payload["points"]}
    assert por_dia == {"2026-09-01": 1, "2026-09-02": 0}


def test_timeseries_respeita_o_teto_de_periodo(tool, db_session):
    db_session.commit()

    with pytest.raises(ValueError) as exc:
        tool("opr_support_timeseries")(date_from="2026-01-01", date_to="2026-03-01")
    assert "32 dias" in str(exc.value)


def test_timeseries_aplica_filtro_e_a_serie_bate_com_o_overview(tool, db_session):
    """A série é decomposição do MESMO universo dos cards - a soma dos pontos tem que fechar com o
    total do overview sob o mesmo recorte, senão a tela e a tool contariam universos diferentes."""
    _make_attendance(db_session, "AT-1", day=date(2026, 9, 1), channel="whatsapp")
    _make_attendance(db_session, "AT-2", day=date(2026, 9, 2), channel="whatsapp")
    _make_attendance(db_session, "AT-3", day=date(2026, 9, 2), channel="telefone")
    db_session.commit()

    filtros = {"channel": "whatsapp"}
    serie = json.loads(
        tool("opr_support_timeseries")(date_from="2026-09-01", date_to="2026-09-03", support_filters=filtros)
    )
    overview = json.loads(
        tool("opr_support_overview")(date_from="2026-09-01", date_to="2026-09-03", support_filters=filtros)
    )

    assert sum(point["total"] for point in serie["points"]) == overview["total_attendances"]["current"] == 2
