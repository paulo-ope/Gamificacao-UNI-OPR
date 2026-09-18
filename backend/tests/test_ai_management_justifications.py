"""Pendências de justificativa e leitura das justificativas expostas por chave de API
(POST /ai/management/pending-by-collaborator, /ai/management/justifications, /ai/management/cases)
- pedido do usuário em 2026-09-10.

Ponto sensível coberto aqui: `/ai/management/justifications` nasce DESLIGADA na governança de IA,
porque `justification_text` é texto livre escrito por um supervisor sobre uma pessoa específica.
Ligar essa capacidade é decisão de administrador, não efeito colateral do deploy.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import hash_api_key
from app.models import User
from app.modules.ai_governance.models import AiApiToken, AiEndpoint
from app.modules.ai_governance.policy import bump_policy_version
from app.modules.management import cases as cases_engine
from app.modules.management.models import ManagementCase


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


def _api_key(db_session, raw_key: str, scopes: list[str] | None = None) -> str:
    service_user = User(
        name="Servico IA Justificativas",
        email=f"ai-just-{raw_key[:8]}@pytest.local",
        role="ai_service",
        active=True,
        password_hash="x",
    )
    db_session.add(service_user)
    db_session.flush()
    db_session.add(
        AiApiToken(
            user_id=service_user.id,
            name="Leitura gestao",
            scopes=scopes if scopes is not None else ["management.read"],
            key_prefix=raw_key[:12],
            key_hash=hash_api_key(raw_key),
        )
    )
    return raw_key


def _enable_endpoint(db_session, key: str) -> None:
    """Liga a capacidade como a tela de governança liga - inclusive o `bump_policy_version`.

    Sem o bump, `resolve_effective_policy` devolve a política do CACHE (chaveado por
    `user.id ^ versão`), e como cada teste roda num banco `:memory:` novo os ids de usuário se
    repetem: a política de outro teste vazava aqui e este teste falhava com 403. É a mesma regra
    documentada em `policy.py` ("qualquer escrita nas tabelas de governança deve chamar
    bump_policy_version"), então o teste tem que respeitá-la igual ao código de produção."""
    endpoint = db_session.scalar(select(AiEndpoint).where(AiEndpoint.key == key))
    endpoint.enabled_api = True
    endpoint.enabled_mcp = True
    endpoint.enabled_ai = True
    db_session.flush()
    bump_policy_version(db_session)


# --- pending-by-collaborator --------------------------------------------------------------------


def test_pendencias_por_colaborador_recortam_por_regional_e_data(client, db_session):
    raw_key = _api_key(db_session, "raw-key-pending-by-collab-01")
    _make_case(db_session, responsible_name="Joao Jaru", regional="UNI JARU", reference_date=date(2026, 9, 3))
    _make_case(db_session, responsible_name="Maria Ariq", regional="UNI ARIQUEMES", reference_date=date(2026, 9, 3))
    _make_case(db_session, responsible_name="Joao Jaru", regional="UNI JARU", reference_date=date(2026, 12, 1))
    db_session.commit()

    response = client.post(
        "/api/ai/management/pending-by-collaborator",
        json={
            "regional": "UNI JARU",
            "reference_date_from": "2026-09-01",
            "reference_date_to": "2026-09-30",
            "pending_justification": True,
        },
        headers={"x-api-key": raw_key},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_collaborators"] == 1
    item = body["items"][0]
    assert item["responsible_name"] == "Joao Jaru"
    assert item["pending_cases"] == 1
    assert item["open_case_ids"]


def test_pendencias_por_colaborador_exigem_escopo_do_token(client, db_session):
    raw_key = _api_key(db_session, "raw-key-pending-no-scope-02", scopes=["orders.read"])
    db_session.commit()

    response = client.post(
        "/api/ai/management/pending-by-collaborator",
        json={},
        headers={"x-api-key": raw_key},
    )

    assert response.status_code == 403


def test_filtro_contraditorio_devolve_422_com_mensagem_acionavel(client, db_session):
    raw_key = _api_key(db_session, "raw-key-pending-contradicao-03")
    db_session.commit()

    response = client.post(
        "/api/ai/management/pending-by-collaborator",
        json={"pending_justification": True, "awaiting_review": True},
        headers={"x-api-key": raw_key},
    )

    assert response.status_code == 422
    assert "mutuamente" in response.json()["detail"]


def test_chave_de_filtro_desconhecida_e_rejeitada_em_vez_de_ignorada(client, db_session):
    """O schema é `extra="forbid"`: "regional" no singular quando o certo era outro nome dá 422,
    não uma resposta 200 com o filtro descartado em silêncio (mesmo racional de `AiOrderFilters`)."""
    raw_key = _api_key(db_session, "raw-key-pending-chave-errada-04")
    db_session.commit()

    response = client.post(
        "/api/ai/management/pending-by-collaborator",
        json={"colaborador": "Joao Campo"},
        headers={"x-api-key": raw_key},
    )

    assert response.status_code == 422


# --- justifications -----------------------------------------------------------------------------


def test_leitura_de_justificativas_nasce_desligada_na_governanca(client, db_session):
    """Decisão desta rodada: texto livre sobre uma pessoa não fica exposto a uma chave de máquina
    por padrão. O administrador liga na tela de governança."""
    raw_key = _api_key(db_session, "raw-key-justificativas-off-05")
    _make_case(db_session, status="justified", justification_text="Atestado médico apresentado.")
    db_session.commit()

    response = client.post(
        "/api/ai/management/justifications",
        json={},
        headers={"x-api-key": raw_key},
    )

    assert response.status_code == 403


def test_leitura_de_justificativas_entrega_texto_motivo_e_decisao_depois_de_liberada(client, db_session, admin_user):
    raw_key = _api_key(db_session, "raw-key-justificativas-on-06")
    _enable_endpoint(db_session, "ai.management_justifications")
    _make_case(
        db_session,
        responsible_name="Ana Souza",
        status="resolved",
        justification_text="Colaboradora em treinamento na matriz.",
        action_plan="Repor produção na semana seguinte.",
        justified_at=datetime.now(timezone.utc),
        reviewed_by=admin_user.id,
        reviewed_at=datetime.now(timezone.utc),
    )
    _make_case(db_session, responsible_name="Mariana Lima", status="justified", justification_text="Outro motivo.")
    db_session.commit()

    response = client.post(
        "/api/ai/management/justifications",
        json={"responsible_name": "Ana Souza", "has_justification": True},
        headers={"x-api-key": raw_key},
    )

    assert response.status_code == 200
    body = response.json()
    # Nome exato: "Mariana Lima" contém "ana" e NÃO deve entrar.
    assert body["total"] == 1
    item = body["items"][0]
    assert item["justification_text"] == "Colaboradora em treinamento na matriz."
    assert item["action_plan"] == "Repor produção na semana seguinte."
    assert item["reviewer_name"] == admin_user.name


def test_leitura_de_justificativas_pagina_e_reporta_o_total(client, db_session):
    raw_key = _api_key(db_session, "raw-key-justificativas-page-07")
    _enable_endpoint(db_session, "ai.management_justifications")
    for dia in range(1, 6):
        _make_case(db_session, reference_date=date(2026, 9, dia), status="justified", justification_text=f"Dia {dia}.")
    db_session.commit()

    response = client.post(
        "/api/ai/management/justifications",
        json={"page": 1, "page_size": 2},
        headers={"x-api-key": raw_key},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


# --- cases --------------------------------------------------------------------------------------


def test_listagem_de_casos_por_chave_de_api_traz_resumo_do_recorte_inteiro(client, db_session):
    raw_key = _api_key(db_session, "raw-key-cases-list-08")
    _make_case(db_session, status="pending")
    _make_case(db_session, status="justified", justification_text="ok")
    _make_case(db_session, status="resolved", justification_text="ok")
    db_session.commit()

    response = client.post(
        "/api/ai/management/cases",
        json={"page": 1, "page_size": 1},
        headers={"x-api-key": raw_key},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    # O resumo é do recorte COMPLETO, não da página - é o que evita ler 1 item como "só há 1 caso".
    assert body["summary"]["total_cases"] == 3
    assert body["summary"]["pending_cases"] == 1
