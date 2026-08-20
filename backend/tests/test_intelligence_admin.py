"""F5: testes de risco da Administração do UNI Intelligence (app/modules/intelligence/cockpit.py,
router.py - bloco admin_router).

Cobre os riscos reais introduzidos nesta rodada, não testes redundantes com F0-F4:
- widget.filters NUNCA amplia o scope do profile (só restringe) - o contrato central da F5.
- tradução os_subjects -> subjects para as funções REST legadas de operations.
- validação de widget/filtro na escrita (Administração) - nunca aceita filtro não suportado em
  silêncio.
- RBAC: intelligence:read não basta para os endpoints admin (intelligence:manage) nem para
  publicar (intelligence:publish) - três permissões distintas, nunca uma cobrindo a outra.
- publicações: Administração enxerga DISMISSED (histórico), TV não.
- monitores: PUT admin realmente muda o comportamento efetivo lido pelo scheduler.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.security import get_current_user
from app.main import app
from app.models import AccessProfile, AccessProfilePermission, User, UserAccessProfile
from app.modules.intelligence import cockpit
from app.modules.intelligence.models import IntelligenceDashboardProfile
from app.modules.operations.models import OperationOrder
from app.modules.operations.period import OPERATIONS_TIMEZONE


def _seed_order(db_session, *, regional: str, sector: str = "Suporte Externo") -> None:
    # Meio-dia local (não "agora - Xh") - `build_cockpit_payload` calcula "hoje" em
    # OPERATIONS_TIMEZONE (UTC-4); usar um horário relativo ao UTC "agora" arrisca cair do lado
    # errado da meia-noite local quando o teste roda perto da virada do dia em UTC (achado real:
    # os 2 testes de widget-scope abaixo falharam por isso na primeira rodada).
    local_noon = datetime.now(OPERATIONS_TIMEZONE).replace(hour=12, minute=0, second=0, microsecond=0)
    opened_at = local_noon.astimezone(timezone.utc)
    db_session.add(
        OperationOrder(
            source="ixc",
            source_order_id=f"ADMIN-{regional}-{sector}-{opened_at.timestamp()}",
            order_code=f"ADMIN-{regional}-{sector}-{opened_at.timestamp()}",
            regional=regional,
            os_type="Manutencao",
            os_subject="Reparo",
            sector=sector,
            sla_status="unidentified",
            is_closed=False,
            opened_at=opened_at,
        )
    )
    db_session.commit()


def _as_user_with_only(db_session, *, base_user: User, permissions: list[str]) -> User:
    """Sobrescreve as permissões efetivas de `base_user` via AccessProfile dedicado - como
    `permissions_for_user` usa profile_permissions OU role (nunca os dois juntos), isso restringe
    de verdade um admin_user a só o que a lista pede (ver core/security.py::permissions_for_user)."""
    profile = AccessProfile(name=f"Teste {'-'.join(permissions)}", active=True, is_system=False)
    db_session.add(profile)
    db_session.flush()
    for permission in permissions:
        db_session.add(AccessProfilePermission(profile_id=profile.id, permission=permission))
    db_session.add(UserAccessProfile(user_id=base_user.id, profile_id=profile.id))
    db_session.commit()
    return base_user


def _call_as(client, user, method, path, **kwargs):
    original = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        return getattr(client, method)(path, **kwargs)
    finally:
        if original is not None:
            app.dependency_overrides[get_current_user] = original


def _make_profile(db_session, key: str, *, regionals: list[str] | None = None, widgets: list) -> IntelligenceDashboardProfile:
    profile = IntelligenceDashboardProfile(
        key=key,
        name=key,
        purpose="MATRIX_TV" if not regionals else "REGIONAL_TV",
        scope_json={"regionals": regionals or []},
        widgets_json=widgets,
        refresh_seconds=60,
        active=True,
    )
    db_session.add(profile)
    db_session.commit()
    return profile


# --- _restrict_filter_values / _effective_operations_filters (unidade) -------------------------


def test_restrict_filter_values_narrows_within_base():
    values, conflict = cockpit._restrict_filter_values(["A", "B", "C"], ["B", "C", "D"])
    assert values == ["B", "C"]
    assert conflict is False


def test_restrict_filter_values_uses_widget_value_when_base_is_global():
    # Profile global (sem recorte) + widget restringe -> usa o do widget (restrição válida de
    # "tudo" para "isso"; não é ampliação porque não havia recorte nenhum antes).
    values, conflict = cockpit._restrict_filter_values([], ["B"])
    assert values == ["B"]
    assert conflict is False


def test_restrict_filter_values_conflict_keeps_base_never_widens_or_empties():
    values, conflict = cockpit._restrict_filter_values(["A"], ["Z"])
    assert values == ["A"]
    assert conflict is True


def test_effective_operations_filters_flags_unsupported_field_and_drops_it():
    warnings: list[dict] = []
    effective = cockpit._effective_operations_filters({"sectors": ["Suporte Externo"]}, {"responsibles": ["fulano"]}, "production", warnings)
    assert "responsibles" not in effective
    assert warnings[0]["code"] == "FILTER_NOT_SUPPORTED_BY_WIDGET"
    assert warnings[0]["widget"] == "production"


def test_to_operations_rest_filters_translates_os_subjects_to_legacy_subjects_key():
    translated = cockpit._to_operations_rest_filters({"os_subjects": ["Reparo"], "sectors": ["Suporte Externo"]})
    assert translated == {"subjects": ["Reparo"], "sectors": ["Suporte Externo"]}


# --- validate_widget_entries (validação de escrita) ---------------------------------------------


def test_validate_widget_entries_rejects_unknown_widget_key():
    try:
        cockpit.validate_widget_entries([{"key": "widget_que_nao_existe", "filters": {}}])
        assert False, "deveria ter levantado ProfileValidationError"
    except cockpit.ProfileValidationError as exc:
        assert "widget_que_nao_existe" in str(exc)


def test_validate_widget_entries_rejects_unsupported_filter_for_widget():
    try:
        cockpit.validate_widget_entries([{"key": "overall_status", "filters": {"regionals": ["UNI - JI PARANA"]}}])
        assert False, "deveria ter levantado ProfileValidationError"
    except cockpit.ProfileValidationError as exc:
        assert "regionals" in str(exc)


def test_validate_widget_entries_accepts_supported_filter_and_normalizes():
    validated = cockpit.validate_widget_entries(["overall_status", {"key": "backlog", "filters": {"team_models": ["SUPORTE MOTO"]}}])
    assert validated == [{"key": "overall_status", "filters": {}}, {"key": "backlog", "filters": {"team_models": ["SUPORTE MOTO"]}}]


# --- widget nunca amplia o scope na prática (integração real com OperationOrder) -----------------


def test_widget_filter_narrows_global_profile_to_single_regional(db_session):
    """Profile global (sem recorte) + widget production com regionals=['A'] -> só A aparece,
    nunca as duas (a ausência de recorte no profile não pode virar "widget escolhe à vontade sem
    limite", mas TAMBÉM não pode ampliar para incluir regionais que o widget não pediu)."""
    _seed_order(db_session, regional="UNI - JI PARANA")
    _seed_order(db_session, regional="UNI - JARU")
    profile = _make_profile(
        db_session,
        "teste-global-restrito",
        regionals=None,
        widgets=[{"key": "production", "filters": {"regionals": ["UNI - JI PARANA"]}}],
    )

    payload = cockpit.build_cockpit_payload(db_session, profile)

    assert payload["production"]["opened_today"] == 1
    assert not any(w.get("code") == "WIDGET_FILTER_CONFLICTS_WITH_SCOPE" for w in payload["meta"]["warnings"])


def test_widget_filter_conflicting_with_profile_scope_falls_back_to_scope_and_warns(db_session):
    """Profile recortado para UNI - JI PARANA + widget production pedindo UNI - JARU (fora do
    scope) -> nunca deve ampliar para JARU nem para as duas; mantém só o que o profile já permitia
    e registra o warning estruturado (nunca ignora em silêncio)."""
    _seed_order(db_session, regional="UNI - JI PARANA")
    _seed_order(db_session, regional="UNI - JARU")
    profile = _make_profile(
        db_session,
        "teste-conflito-scope",
        regionals=["UNI - JI PARANA"],
        widgets=[{"key": "production", "filters": {"regionals": ["UNI - JARU"]}}],
    )

    payload = cockpit.build_cockpit_payload(db_session, profile)

    assert payload["production"]["opened_today"] == 1  # continua só JI PARANA, nunca JARU
    assert any(w.get("code") == "WIDGET_FILTER_CONFLICTS_WITH_SCOPE" and w.get("widget") == "production" for w in payload["meta"]["warnings"])


# --- RBAC: intelligence:read / intelligence:manage / intelligence:publish são distintas ----------


def test_read_only_user_is_forbidden_from_admin_endpoints(client, db_session, admin_user):
    reader = _as_user_with_only(db_session, base_user=admin_user, permissions=["intelligence:read"])

    response = _call_as(client, reader, "get", "/api/intelligence/admin/profiles")
    assert response.status_code == 403

    response = _call_as(client, reader, "put", "/api/intelligence/admin/monitors/collective_outage", json={"enabled": False})
    assert response.status_code == 403


def test_manage_permission_alone_does_not_grant_publish(client, db_session, admin_user):
    manager = _as_user_with_only(db_session, base_user=admin_user, permissions=["intelligence:read", "intelligence:manage"])

    response = _call_as(
        client,
        manager,
        "post",
        "/api/intelligence/cockpit-content",
        json={"content_type": "MANUAL_MESSAGE", "title": "teste", "body": "teste"},
    )
    assert response.status_code == 403


def test_manage_user_can_reach_admin_endpoints(client, db_session, admin_user):
    manager = _as_user_with_only(db_session, base_user=admin_user, permissions=["intelligence:read", "intelligence:manage"])

    response = _call_as(client, manager, "get", "/api/intelligence/admin/profiles")
    assert response.status_code == 200


# --- criação/edição de profile via endpoint valida filtros (nunca 500, sempre 422) ---------------


def test_create_profile_endpoint_rejects_unsupported_widget_filter(client):
    response = client.post(
        "/api/intelligence/admin/profiles",
        json={
            "key": "teste-filtro-invalido",
            "name": "Teste",
            "scope": {"regionals": []},
            "widgets": [{"key": "active_alerts", "filters": {"os_subjects": ["Reparo"]}}],
        },
    )
    assert response.status_code == 422


def test_create_profile_endpoint_rejects_duplicate_key(client, db_session):
    _make_profile(db_session, "ja-existe", widgets=[])
    response = client.post("/api/intelligence/admin/profiles", json={"key": "ja-existe", "name": "Duplicado", "scope": {"regionals": []}, "widgets": []})
    assert response.status_code == 422


# --- publicações: Administração vê histórico (DISMISSED), TV não --------------------------------


def test_admin_content_list_includes_dismissed_but_cockpit_does_not(client, db_session, admin_user):
    cockpit.ensure_default_dashboard_profile(db_session)
    profile = cockpit.get_profile(db_session, "uni-geral")
    created = cockpit.publish_cockpit_content(
        db_session,
        content_type="MANUAL_MESSAGE",
        profile_key=None,
        scope={},
        severity="INFO",
        title="Aviso de teste",
        body="corpo",
        evidence={},
        confidence=None,
        valid_until=None,
        source_type="USER",
        source_key=None,
        author_user_id=admin_user.id,
    )
    cockpit.dismiss_cockpit_content(db_session, created)

    admin_response = client.get("/api/intelligence/admin/content")
    assert admin_response.status_code == 200
    admin_titles = {item["title"]: item["status"] for item in admin_response.json()}
    assert admin_titles.get("Aviso de teste") == "DISMISSED"

    tv_response = client.get(f"/api/intelligence/cockpit/{profile.key}")
    assert tv_response.status_code == 200
    tv_titles = {item["title"] for item in tv_response.json()["content"]}
    assert "Aviso de teste" not in tv_titles


def test_update_dismissed_content_is_rejected(client, db_session, admin_user):
    created = cockpit.publish_cockpit_content(
        db_session,
        content_type="MANUAL_MESSAGE",
        profile_key=None,
        scope={},
        severity="INFO",
        title="Outro aviso",
        body="corpo",
        evidence={},
        confidence=None,
        valid_until=None,
        source_type="USER",
        source_key=None,
        author_user_id=admin_user.id,
    )
    cockpit.dismiss_cockpit_content(db_session, created)

    response = client.put(f"/api/intelligence/admin/content/{created.id}", json={"title": "Não deveria funcionar"})
    assert response.status_code == 422


# --- monitores: PUT admin muda o que o scheduler efetivamente lê --------------------------------


def test_admin_monitor_update_changes_effective_settings_read_by_scheduler(client, db_session):
    response = client.put(
        "/api/intelligence/admin/monitors/collective_outage",
        json={"enabled": False, "interval_minutes": 45},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["interval_minutes"] == 45

    listing = client.get("/api/intelligence/monitors")
    updated = next(item for item in listing.json()["items"] if item["key"] == "collective_outage")
    assert updated["enabled"] is False
    assert updated["interval_minutes"] == 45
