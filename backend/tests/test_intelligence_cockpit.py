"""F2: Cockpit API + publicação genérica de conteúdo (app/modules/intelligence/cockpit.py,
router.py). Cobre os testes obrigatórios backend do processo aprovado: profile válido/inexistente,
scope global/regional, conteúdo ativo/expirado, publicação sem permissão/válida, alertas/incidentes
filtrados pelo profile, monitor unhealthy, coverage/warnings, e o payload completo do summary."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.intelligence import cockpit
from app.modules.intelligence.models import IntelligenceAlert, IntelligenceCockpitContent, IntelligenceDashboardProfile, IntelligenceMonitorRun
from app.modules.operations.models import OperationOrder


def _seed_orders(db_session, *, regional: str, count_open: int = 3, count_closed: int = 5) -> None:
    now = datetime.now(timezone.utc)
    counter = {"n": 0}

    def _next_code() -> str:
        counter["n"] += 1
        return f"COCKPIT-{regional}-{counter['n']}"

    for _ in range(count_open):
        db_session.add(
            OperationOrder(
                source="ixc", source_order_id=_next_code(), order_code=_next_code(),
                regional=regional, os_type="Manutencao", os_subject="Reparo",
                sector="Suporte Externo", sla_status="unidentified", is_closed=False,
                opened_at=now - timedelta(hours=2),
            )
        )
    for _ in range(count_closed):
        db_session.add(
            OperationOrder(
                source="ixc", source_order_id=_next_code(), order_code=_next_code(),
                regional=regional, os_type="Manutencao", os_subject="Reparo",
                sector="Suporte Externo", sla_status="on_time", is_closed=True,
                opened_at=now - timedelta(hours=4), closed_at=now - timedelta(hours=1), elapsed_hours=3.0,
            )
        )
    db_session.commit()


def _seed_alert(db_session, **overrides) -> IntelligenceAlert:
    now = datetime.now(timezone.utc)
    defaults = dict(
        kind="ALERT", alert_type="SLA_DETERIORATION", monitor_key="sla_deterioration",
        dedupe_key=f"test:{overrides.get('regional', 'x')}:{now.timestamp()}",
        regional="UNI - JI PARANA", severity="HIGH", title="Alerta de teste", summary="resumo",
        status="CONFIRMED", first_detected_at=now, last_seen_at=now,
    )
    defaults.update(overrides)
    alert = IntelligenceAlert(**defaults)
    db_session.add(alert)
    db_session.commit()
    return alert


def _make_profile(db_session, key: str, regionals: list[str] | None = None) -> IntelligenceDashboardProfile:
    profile = IntelligenceDashboardProfile(
        key=key, name=key, purpose="MATRIX_TV" if not regionals else "REGIONAL_TV",
        scope_json={"regionals": regionals or []},
        widgets_json=list(cockpit.WIDGET_CATALOG), refresh_seconds=60, active=True,
    )
    db_session.add(profile)
    db_session.commit()
    return profile


# --- profile ---------------------------------------------------------------------------------


def test_default_profile_seed_creates_uni_geral(db_session):
    cockpit.ensure_default_dashboard_profile(db_session)
    profile = cockpit.get_profile(db_session, "uni-geral")
    assert profile is not None
    assert profile.purpose == "MATRIX_TV"
    assert profile.scope_json == {"regionals": []}
    assert "overall_status" in profile.widgets_json


def test_default_profile_seed_is_idempotent(db_session):
    cockpit.ensure_default_dashboard_profile(db_session)
    first = cockpit.get_profile(db_session, "uni-geral")
    first.name = "Renomeado pela Administração"
    db_session.commit()

    cockpit.ensure_default_dashboard_profile(db_session)  # roda de novo, não deve reverter
    second = cockpit.get_profile(db_session, "uni-geral")
    assert second.name == "Renomeado pela Administração"


def test_get_profile_returns_none_for_unknown_key(db_session):
    assert cockpit.get_profile(db_session, "nao-existe") is None


def test_cockpit_endpoint_404_for_unknown_profile(client):
    response = client.get("/api/intelligence/cockpit/nao-existe")
    assert response.status_code == 404


# --- payload completo --------------------------------------------------------------------------


def test_cockpit_payload_has_all_expected_sections(db_session):
    profile = _make_profile(db_session, "uni-geral")
    _seed_orders(db_session, regional="UNI - JI PARANA")

    payload = cockpit.build_cockpit_payload(db_session, profile)

    for key in ("profile", "generated_at", "overall_status", "display_mode", "production", "backlog", "sla", "alerts", "incidents", "content", "monitor_health", "data_freshness", "meta"):
        assert key in payload, f"chave ausente no payload do cockpit: {key}"
    assert payload["overall_status"]["status"] in ("NORMAL", "ATTENTION", "RISK", "CRITICAL")
    assert payload["production"]["opened_today"] >= 3
    assert payload["backlog"]["total"] >= 3


def test_cockpit_payload_scope_global_sees_all_regionals_alerts(db_session):
    profile = _make_profile(db_session, "uni-geral")  # regionals: []
    _seed_alert(db_session, regional="UNI - JI PARANA")
    _seed_alert(db_session, regional="UNI - MACHADINHO DOESTE")

    payload = cockpit.build_cockpit_payload(db_session, profile)

    assert len(payload["alerts"]) == 2


def test_cockpit_payload_scope_regional_filters_alerts(db_session):
    profile = _make_profile(db_session, "machadinho", regionals=["UNI - MACHADINHO DOESTE"])
    _seed_alert(db_session, regional="UNI - JI PARANA")
    _seed_alert(db_session, regional="UNI - MACHADINHO DOESTE")

    payload = cockpit.build_cockpit_payload(db_session, profile)

    assert len(payload["alerts"]) == 1
    assert payload["alerts"][0]["regional"] == "UNI - MACHADINHO DOESTE"


def test_cockpit_payload_incidents_separated_from_alerts(db_session):
    profile = _make_profile(db_session, "uni-geral")
    _seed_alert(db_session, kind="ALERT", alert_type="SLA_DETERIORATION")
    _seed_alert(db_session, kind="INCIDENT", alert_type="COLLECTIVE_OUTAGE")

    payload = cockpit.build_cockpit_payload(db_session, profile)

    assert len(payload["alerts"]) == 1
    assert len(payload["incidents"]) == 1
    assert payload["incidents"][0]["kind"] == "INCIDENT"


def test_cockpit_payload_monitor_unhealthy_reflected(db_session):
    profile = _make_profile(db_session, "uni-geral")
    _seed_alert(db_session, kind="ALERT", alert_type="MONITOR_UNHEALTHY", monitor_key="monitor_health", severity="HIGH")

    payload = cockpit.build_cockpit_payload(db_session, profile)

    assert payload["overall_status"]["status"] == "RISK"


def test_cockpit_payload_coverage_and_warnings_propagate(db_session):
    profile = _make_profile(db_session, "uni-geral")
    _seed_alert(
        db_session,
        coverage_json={"coordinate_coverage_pct": 71.4},
        warnings_json=[{"code": "PARTIAL_DIMENSION_COVERAGE"}],
    )

    payload = cockpit.build_cockpit_payload(db_session, profile)

    assert payload["alerts"][0]["coverage"]["coordinate_coverage_pct"] == 71.4
    assert payload["alerts"][0]["warnings"][0]["code"] == "PARTIAL_DIMENSION_COVERAGE"


def test_cockpit_payload_monitor_health_section_present(db_session):
    profile = _make_profile(db_session, "uni-geral")
    db_session.add(IntelligenceMonitorRun(monitor_key="collective_outage", status="COMPLETED", started_at=datetime.now(timezone.utc)))
    db_session.commit()

    payload = cockpit.build_cockpit_payload(db_session, profile)

    keys = {row["monitor_key"] for row in payload["monitor_health"]}
    assert {"collective_outage", "sla_deterioration", "operational_pressure", "monitor_health"} <= keys


# --- conteúdo: ativo vs expirado, global vs direcionado -----------------------------------------


def test_content_active_appears_in_payload(db_session):
    profile = _make_profile(db_session, "uni-geral")
    cockpit.publish_cockpit_content(
        db_session, content_type="INFO", profile_key=None, scope={}, severity="INFO",
        title="Comunicado ativo", body="corpo do comunicado", evidence=None, confidence=None,
        valid_until=None, source_type="SYSTEM", source_key="test", author_user_id=None,
    )

    payload = cockpit.build_cockpit_payload(db_session, profile)

    assert len(payload["content"]) == 1
    assert payload["content"][0]["title"] == "Comunicado ativo"


def test_content_expired_does_not_appear_in_payload(db_session):
    profile = _make_profile(db_session, "uni-geral")
    content = cockpit.publish_cockpit_content(
        db_session, content_type="INFO", profile_key=None, scope={}, severity="INFO",
        title="Comunicado expirado", body="corpo", evidence=None, confidence=None,
        valid_until=datetime.now(timezone.utc) + timedelta(seconds=2), source_type="SYSTEM",
        source_key="test", author_user_id=None,
    )
    # força expiração sem esperar o relógio de verdade
    content.valid_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    payload = cockpit.build_cockpit_payload(db_session, profile)

    assert payload["content"] == []


def test_content_targeted_profile_not_shown_on_other_profile(db_session):
    profile_a = _make_profile(db_session, "profile-a")
    profile_b = _make_profile(db_session, "profile-b")
    cockpit.publish_cockpit_content(
        db_session, content_type="MANUAL_MESSAGE", profile_key="profile-a", scope={}, severity="INFO",
        title="Só para o profile A", body="corpo", evidence=None, confidence=None, valid_until=None,
        source_type="USER", source_key=None, author_user_id=1,
    )

    payload_a = cockpit.build_cockpit_payload(db_session, profile_a)
    payload_b = cockpit.build_cockpit_payload(db_session, profile_b)

    assert len(payload_a["content"]) == 1
    assert payload_b["content"] == []


# --- validação de publicação (service) -----------------------------------------------------------


def test_publish_rejects_invalid_content_type(db_session):
    try:
        cockpit.publish_cockpit_content(
            db_session, content_type="NOT_A_TYPE", profile_key=None, scope={}, severity="INFO",
            title="t", body="b", evidence=None, confidence=None, valid_until=None,
            source_type="SYSTEM", source_key="test", author_user_id=None,
        )
        assert False, "deveria ter levantado CockpitContentValidationError"
    except cockpit.CockpitContentValidationError:
        pass


def test_publish_rejects_anonymous_content(db_session):
    try:
        cockpit.publish_cockpit_content(
            db_session, content_type="INFO", profile_key=None, scope={}, severity="INFO",
            title="t", body="b", evidence=None, confidence=None, valid_until=None,
            source_type="SYSTEM", source_key=None, author_user_id=None,
        )
        assert False, "publicacao anonima (sem source_key nem author_user_id) deveria ser rejeitada"
    except cockpit.CockpitContentValidationError:
        pass


def test_publish_rejects_unknown_profile(db_session):
    try:
        cockpit.publish_cockpit_content(
            db_session, content_type="INFO", profile_key="nao-existe", scope={}, severity="INFO",
            title="t", body="b", evidence=None, confidence=None, valid_until=None,
            source_type="SYSTEM", source_key="test", author_user_id=None,
        )
        assert False, "profile inexistente deveria ser rejeitado"
    except cockpit.CockpitContentValidationError:
        pass


# --- endpoints REST ------------------------------------------------------------------------------


def test_publish_endpoint_requires_permission(client, db_session, admin_user):
    """admin tem intelligence:publish por padrão (ROLE_PERMISSIONS) - simula um usuário sem essa
    permissão criando um perfil de acesso próprio, sem intelligence:publish."""
    from app.core.security import get_current_user
    from app.main import app
    from app.models import User

    limited_user = User(name="Sem Permissao", email="sem-permissao@pytest.local", role="viewer", active=True, password_hash="x")
    db_session.add(limited_user)
    db_session.flush()

    app.dependency_overrides[get_current_user] = lambda: limited_user
    try:
        response = client.post(
            "/api/intelligence/cockpit-content",
            json={"content_type": "INFO", "title": "t", "body": "b"},
        )
    finally:
        app.dependency_overrides[get_current_user] = lambda: admin_user

    assert response.status_code == 403


def test_publish_endpoint_valid_creates_content(client, db_session):
    cockpit.ensure_default_dashboard_profile(db_session)

    response = client.post(
        "/api/intelligence/cockpit-content",
        json={
            "content_type": "AI_INSIGHT",
            "profile_key": "uni-geral",
            "title": "Teste UNI Intelligence",
            "body": "Mensagem de validação do canal de inteligência operacional.",
            "severity": "INFO",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["content_type"] == "AI_INSIGHT"
    assert body["source_type"] == "USER"
    assert body["author_user_id"] is not None

    cockpit_response = client.get("/api/intelligence/cockpit/uni-geral")
    assert cockpit_response.status_code == 200
    titles = [item["title"] for item in cockpit_response.json()["content"]]
    assert "Teste UNI Intelligence" in titles


# --- F3: escopo de setores (achado real - backlog contava Cobranca/Comercial/Estoque/etc) -----


def _make_order_with_sector(db_session, counter, *, sector: str, regional: str = "UNI - JI PARANA", is_closed: bool = False) -> None:
    db_session.add(
        OperationOrder(
            source="ixc", source_order_id=f"SECTOR-{counter}", order_code=f"SECTOR-{counter}",
            regional=regional, os_type="Manutencao", os_subject="Reparo", sector=sector,
            sla_status="unidentified", is_closed=is_closed,
            opened_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )


def test_backlog_only_counts_primary_operational_sectors(db_session):
    """F3 - achado real: sem filtro de setor, o backlog contava Cobranca/Comercial/Estoque/
    Financeiro (não é fila de campo). Default deve ser só os 3 setores de operação real."""
    profile = _make_profile(db_session, "uni-geral")
    for i in range(5):
        _make_order_with_sector(db_session, f"billing-{i}", sector="Cobrança")
    for i in range(2):
        _make_order_with_sector(db_session, f"field-{i}", sector="Suporte Externo")
    db_session.commit()

    payload = cockpit.build_cockpit_payload(db_session, profile)

    assert payload["backlog"]["total"] == 2, "Cobranca nao pode contar como backlog operacional"
    assert set(payload["meta"]["applied_filters"]["sectors"]) == {"Suporte Externo", "Suporte Externo Rádio", "Suporte Externo Fibra"}


def test_backlog_sector_filter_is_applied_and_visible_in_meta(db_session):
    profile = _make_profile(db_session, "uni-geral")
    payload = cockpit.build_cockpit_payload(db_session, profile)
    assert set(payload["meta"]["applied_filters"]["sectors"]) == {"Suporte Externo", "Suporte Externo Rádio", "Suporte Externo Fibra"}


# --- F3: overall_status considera escopo/impacto, nao so severidade global ---------------------


def test_local_critical_incident_is_risk_not_critical_on_global_profile(db_session):
    profile = _make_profile(db_session, "uni-geral")  # regionals: [] (escopo global)
    _seed_alert(db_session, kind="INCIDENT", alert_type="COLLECTIVE_OUTAGE", severity="CRITICAL", regional="UNI - JI PARANA")

    payload = cockpit.build_cockpit_payload(db_session, profile)

    assert payload["overall_status"]["status"] == "RISK", "1 incidente critico LOCAL nao pode deixar a UNI inteira CRITICAL"


def test_critical_incident_is_critical_on_matching_regional_profile(db_session):
    profile = _make_profile(db_session, "machadinho", regionals=["UNI - JI PARANA"])
    _seed_alert(db_session, kind="INCIDENT", alert_type="COLLECTIVE_OUTAGE", severity="CRITICAL", regional="UNI - JI PARANA")

    payload = cockpit.build_cockpit_payload(db_session, profile)

    assert payload["overall_status"]["status"] == "CRITICAL", "incidente critico na propria regional do profile regional deve ser CRITICAL"


def test_multi_regional_critical_incidents_are_critical_on_global_profile(db_session):
    profile = _make_profile(db_session, "uni-geral")
    _seed_alert(db_session, dedupe_key="a", kind="INCIDENT", severity="CRITICAL", regional="UNI - JI PARANA")
    _seed_alert(db_session, dedupe_key="b", kind="INCIDENT", severity="CRITICAL", regional="UNI - MACHADINHO DOESTE")

    payload = cockpit.build_cockpit_payload(db_session, profile)

    assert payload["overall_status"]["status"] == "CRITICAL", "2+ regionais criticas ao mesmo tempo e sistemico, nao local"


def test_global_incident_without_regional_is_critical_on_global_profile(db_session):
    profile = _make_profile(db_session, "uni-geral")
    _seed_alert(db_session, kind="INCIDENT", severity="CRITICAL", regional=None)

    payload = cockpit.build_cockpit_payload(db_session, profile)

    assert payload["overall_status"]["status"] == "CRITICAL", "incidente sem regional (achado global) deve ser CRITICAL mesmo na visao UNI"


# --- F3: conteudo regional nao vaza entre profiles ----------------------------------------------


def test_regional_content_does_not_leak_to_other_regional_profile(db_session):
    uni_geral = _make_profile(db_session, "uni-geral2")
    machadinho = _make_profile(db_session, "machadinho2", regionals=["UNI - MACHADINHO DOESTE"])
    jipa = _make_profile(db_session, "jipa2", regionals=["UNI - JI PARANA"])

    cockpit.publish_cockpit_content(
        db_session, content_type="AI_INSIGHT", profile_key=None, scope={"regional": "UNI - JI PARANA"},
        severity="INFO", title="Insight de Ji-Parana", body="corpo", evidence=None, confidence=None,
        valid_until=None, source_type="AI", source_key="test", author_user_id=None,
    )

    assert len(cockpit.build_cockpit_payload(db_session, uni_geral)["content"]) == 1, "escopo global deve ver conteudo de qualquer regional"
    assert len(cockpit.build_cockpit_payload(db_session, jipa)["content"]) == 1, "profile da propria regional deve ver o conteudo"
    assert len(cockpit.build_cockpit_payload(db_session, machadinho)["content"]) == 0, "conteudo de Ji-Parana nao pode vazar para Machadinho"


# --- F3: os 3 profiles default ------------------------------------------------------------------


def test_three_default_profiles_are_seeded(db_session):
    cockpit.ensure_default_dashboard_profile(db_session)

    uni_geral = cockpit.get_profile(db_session, "uni-geral")
    machadinho = cockpit.get_profile(db_session, "machadinho-operacional")
    executivo = cockpit.get_profile(db_session, "executivo-uni")

    assert uni_geral is not None and uni_geral.purpose == "MATRIX_TV" and uni_geral.scope_json == {"regionals": []}
    assert machadinho is not None and machadinho.purpose == "REGIONAL_TV"
    assert machadinho.scope_json == {"regionals": ["UNI - MACHADINHO DOESTE"]}
    assert executivo is not None and executivo.purpose == "EXECUTIVE" and executivo.scope_json == {"regionals": []}
    # profiles realmente diferentes: executivo tem MENOS widgets que os operacionais
    assert len(executivo.widgets_json) < len(uni_geral.widgets_json)
    assert "active_alerts" not in executivo.widgets_json


def test_three_default_profiles_seed_is_idempotent_per_profile(db_session):
    cockpit.ensure_default_dashboard_profile(db_session)
    machadinho = cockpit.get_profile(db_session, "machadinho-operacional")
    machadinho.name = "Renomeado"
    db_session.commit()

    cockpit.ensure_default_dashboard_profile(db_session)  # roda de novo

    assert cockpit.get_profile(db_session, "machadinho-operacional").name == "Renomeado"
    assert cockpit.get_profile(db_session, "executivo-uni") is not None
