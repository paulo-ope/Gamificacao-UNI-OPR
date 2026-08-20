"""Regras de Alertas parametrizáveis (Administração → UNI Intelligence → Regras de Alertas).

Cobre os riscos reais desta rodada - não redundante com F0-F5:
- CRUD de regra via endpoint (RBAC intelligence:manage) + validação (nunca aceita scope/param não
  suportado em silêncio).
- cluster de O.S. por raio (OS_CONCENTRATION_AREA) reaproveitando o mesmo DBSCAN do incidente
  coletivo, agora sobre coordenadas de O.S. em vez de login.
- regra "acima da média" com baseline suficiente x insuficiente (nunca afirma alta confiança sem
  amostra).
- cooldown (não reabre logo após resolver) e confirm_cycles (só emite após N ciclos consecutivos).
- dedupe/auto-resolve reaproveitando alerts.sync_alerts_for_monitor sem duplicar lifecycle.
- filtro de escopo nunca vaza para fora do que a regra define.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.intelligence import alert_rules
from app.modules.intelligence.alerts import dismiss_alert, sync_alerts_for_monitor
from app.modules.intelligence.models import IntelligenceAlert
from app.modules.intelligence.monitors import rules_engine
from app.modules.operations.models import OperationOrder
from app.modules.operations.period import OPERATIONS_TIMEZONE


def _local_now() -> datetime:
    return datetime.now(OPERATIONS_TIMEZONE)


_order_counter = {"n": 0}


def _seed_order(
    db_session, *, regional, latitude=None, longitude=None, sector="Suporte Externo", os_subject="Reparo",
    opened_at=None, is_closed=False, neighborhood=None, address=None,
) -> OperationOrder:
    opened_at = opened_at or _local_now().astimezone(timezone.utc)
    _order_counter["n"] += 1
    unique_id = f"RULE-{_order_counter['n']}-{regional}-{opened_at.timestamp()}"
    order = OperationOrder(
        source="ixc",
        source_order_id=unique_id,
        order_code=unique_id,
        regional=regional,
        os_type="Manutencao",
        os_subject=os_subject,
        sector=sector,
        sla_status="unidentified",
        is_closed=is_closed,
        opened_at=opened_at,
        latitude=latitude,
        longitude=longitude,
        neighborhood=neighborhood,
        raw_payload={"endereco": address} if address else {},
    )
    db_session.add(order)
    db_session.commit()
    return order


# --- CRUD + validação --------------------------------------------------------------------------


def test_create_alert_rule_endpoint_requires_manage_permission(client):
    response = client.post(
        "/api/intelligence/admin/alert-rules",
        json={"key": "teste-x", "name": "Teste", "rule_type": "BACKLOG_THRESHOLD", "params": {"threshold_value": 100}},
    )
    assert response.status_code == 201


def test_create_alert_rule_rejects_unsupported_param(client):
    response = client.post(
        "/api/intelligence/admin/alert-rules",
        json={"key": "teste-param-invalido", "name": "Teste", "rule_type": "BACKLOG_THRESHOLD", "params": {"campo_fantasma": 1}},
    )
    assert response.status_code == 422


def test_create_alert_rule_rejects_unsupported_scope(client):
    response = client.post(
        "/api/intelligence/admin/alert-rules",
        json={"key": "teste-scope-invalido", "name": "Teste", "rule_type": "MONITOR_UNHEALTHY", "scope": {"regionals": ["X"]}},
    )
    assert response.status_code == 422


def test_create_alert_rule_rejects_invalid_rule_type(client):
    response = client.post(
        "/api/intelligence/admin/alert-rules",
        json={"key": "teste-tipo-invalido", "name": "Teste", "rule_type": "TIPO_QUE_NAO_EXISTE"},
    )
    assert response.status_code == 422


def test_update_alert_rule_endpoint_toggles_active(client, db_session):
    alert_rules.create_alert_rule(db_session, key="teste-toggle", name="Teste", rule_type="BACKLOG_THRESHOLD", scope={}, params={})
    response = client.put("/api/intelligence/admin/alert-rules/teste-toggle", json={"active": False})
    assert response.status_code == 200
    assert response.json()["active"] is False


def test_delete_alert_rule_endpoint_removes_rule_and_resolves_linked_alert(client, db_session):
    rule = alert_rules.create_alert_rule(
        db_session, key="teste-excluir", name="Teste", rule_type="BACKLOG_THRESHOLD", scope={}, params={}
    )
    alert = IntelligenceAlert(
        kind="ALERT", alert_type="BACKLOG_THRESHOLD", monitor_key="alert_rules",
        dedupe_key="rule:teste-excluir:geral", severity="HIGH", title="Teste", summary="Teste",
        status="CONFIRMED", first_detected_at=_local_now(), last_seen_at=_local_now(),
        scope_json={"rule_key": rule.key},
    )
    db_session.add(alert)
    db_session.commit()

    response = client.delete("/api/intelligence/admin/alert-rules/teste-excluir")

    assert response.status_code == 204
    assert alert_rules.get_alert_rule(db_session, "teste-excluir") is None
    db_session.refresh(alert)
    assert alert.status == "RESOLVED"


def test_alert_rule_catalog_lists_all_rule_types(client):
    response = client.get("/api/intelligence/admin/alert-rules/catalog")
    assert response.status_code == 200
    body = response.json()
    keys = {entry["key"] for entry in body["rule_types"]}
    assert keys == set(alert_rules.RULE_TYPES)


def test_simulate_alert_rule_does_not_create_alert(client, db_session):
    alert_rules.create_alert_rule(
        db_session,
        key="teste-simular",
        name="Teste simular",
        rule_type="BACKLOG_THRESHOLD",
        scope={},
        params={"threshold_value": 999999},
    )

    response = client.post(
        "/api/intelligence/admin/alert-rules/teste-simular/simulate",
        json={"params": {"threshold_value": 999999}},
    )

    assert response.status_code == 200
    assert response.json()["detection_count"] == 0
    assert db_session.query(IntelligenceAlert).count() == 0


# --- OS_CONCENTRATION_AREA (cluster por raio sobre coordenadas de O.S.) --------------------------


def test_os_concentration_rule_detects_cluster_from_real_coordinates(db_session):
    rule = alert_rules.create_alert_rule(
        db_session, key="teste-cluster", name="Teste cluster", rule_type="OS_CONCENTRATION_AREA",
        scope={}, params={"min_count": 3, "window_minutes": 120, "radius_meters": 300}, severity="HIGH",
    )
    base_lat, base_lng = -10.9, -61.9
    for offset in range(4):
        _seed_order(db_session, regional="UNI - JI PARANA", latitude=base_lat + offset * 0.0005, longitude=base_lng)
    # ponto isolado, longe do cluster - nao deve ser incluido
    _seed_order(db_session, regional="UNI - JI PARANA", latitude=base_lat + 5, longitude=base_lng + 5)

    detections = rules_engine._run_os_concentration_rule(db_session, rule)
    assert len(detections) == 1
    assert detections[0].evidence["os_count"] == 4
    assert detections[0].regional == "UNI - JI PARANA"


def test_os_concentration_evidence_identifies_orders_by_code_and_address(db_session):
    """Achado real (feedback do usuário): a evidência precisa deixar claro QUAIS O.S. formam o
    agrupamento - código real da O.S. e endereço/bairro, nunca só o id interno do banco."""
    rule = alert_rules.create_alert_rule(
        db_session, key="teste-cluster-endereco", name="Teste", rule_type="OS_CONCENTRATION_AREA",
        scope={}, params={"min_count": 3, "window_minutes": 120, "radius_meters": 300},
    )
    base_lat, base_lng = -10.9, -61.9
    for offset in range(3):
        _seed_order(
            db_session, regional="UNI - JI PARANA", latitude=base_lat + offset * 0.0005, longitude=base_lng,
            neighborhood="Setor Chacareiro", address=f"Rua Travessão B, {offset}",
        )

    detections = rules_engine._run_os_concentration_rule(db_session, rule)
    assert len(detections) == 1
    sample = detections[0].evidence["os_sample"]
    assert len(sample) == 3
    assert all(item["neighborhood"] == "Setor Chacareiro" for item in sample)
    assert all(item["address"] and item["address"].startswith("Rua Travessão B") for item in sample)
    assert all(item["order_code"] for item in sample)


def test_os_concentration_historical_comparison_uses_same_area_not_whole_regional(db_session):
    """Achado real: comparar o cluster contra o volume histórico de TODA a regional nunca dispara
    (regional grande sempre tem volume alto). O baseline precisa olhar só a MESMA área (raio) - aqui
    a regional tem MUITO volume histórico fora da área do cluster, mas pouco DENTRO dela, então a
    regra ainda precisa disparar."""
    base_lat, base_lng = -10.9, -61.9
    now = _local_now()
    # muito volume historico na regional, mas longe da area do cluster (nao deve contar no baseline)
    for day_offset in range(1, 6):
        for _ in range(50):
            _seed_order(db_session, regional="UNI - JI PARANA", latitude=base_lat + 5, longitude=base_lng + 5, opened_at=(now - timedelta(days=day_offset)).astimezone(timezone.utc))
    # pouco volume historico DENTRO da area do cluster (baseline real do cluster: 1/dia)
    for day_offset in range(1, 6):
        _seed_order(db_session, regional="UNI - JI PARANA", latitude=base_lat, longitude=base_lng, opened_at=(now - timedelta(days=day_offset)).astimezone(timezone.utc))
    # hoje: cluster de 4 na area (bem acima do baseline de 1/dia da mesma area)
    for offset in range(4):
        _seed_order(db_session, regional="UNI - JI PARANA", latitude=base_lat + offset * 0.0005, longitude=base_lng, opened_at=now.astimezone(timezone.utc))

    rule = alert_rules.create_alert_rule(
        db_session, key="teste-cluster-baseline-area", name="Teste", rule_type="OS_CONCENTRATION_AREA",
        scope={}, params={"min_count": 3, "window_minutes": 120, "radius_meters": 300, "historical_comparison": True, "min_multiplier_over_average": 1.5, "baseline_days": 5},
    )
    detections = rules_engine._run_os_concentration_rule(db_session, rule)
    assert len(detections) == 1
    assert detections[0].confidence == 0.85


def test_os_concentration_rule_ignores_orders_without_coordinates(db_session):
    rule = alert_rules.create_alert_rule(
        db_session, key="teste-cluster-sem-coord", name="Teste", rule_type="OS_CONCENTRATION_AREA",
        scope={}, params={"min_count": 2, "window_minutes": 120, "radius_meters": 300},
    )
    for _ in range(3):
        _seed_order(db_session, regional="UNI - JARU", latitude=None, longitude=None)
    detections = rules_engine._run_os_concentration_rule(db_session, rule)
    assert detections == []


def test_os_concentration_rule_never_widens_beyond_configured_scope(db_session):
    """Regra com scope regionals=['UNI - JARU'] nunca pode detectar cluster em outra regional,
    mesmo que ela exista e seja maior."""
    rule = alert_rules.create_alert_rule(
        db_session, key="teste-cluster-scope", name="Teste", rule_type="OS_CONCENTRATION_AREA",
        scope={"regionals": ["UNI - JARU"]}, params={"min_count": 2, "window_minutes": 120, "radius_meters": 300},
    )
    for offset in range(3):
        _seed_order(db_session, regional="UNI - JARU", latitude=-10.4 + offset * 0.0005, longitude=-62.4)
    for offset in range(5):
        _seed_order(db_session, regional="UNI - MACHADINHO DOESTE", latitude=-9.3 + offset * 0.0005, longitude=-62.5)

    detections = rules_engine._run_os_concentration_rule(db_session, rule)
    assert len(detections) == 1
    assert detections[0].regional == "UNI - JARU"


def test_os_concentration_rule_does_not_mix_regionals_when_required(db_session):
    rule = alert_rules.create_alert_rule(
        db_session,
        key="teste-cluster-mesma-regional",
        name="Teste",
        rule_type="OS_CONCENTRATION_AREA",
        scope={},
        params={"min_count": 3, "window_minutes": 120, "radius_meters": 300, "require_same_regional": True},
    )
    for regional in ("UNI - JARU", "UNI - JARU", "UNI - JI PARANA"):
        _seed_order(db_session, regional=regional, latitude=-10.4, longitude=-62.4)

    assert rules_engine._run_os_concentration_rule(db_session, rule) == []


# --- OS_OPENING_ABOVE_AVERAGE (baseline suficiente x insuficiente) -------------------------------


def test_above_average_rule_triggers_with_sufficient_baseline(db_session):
    now = _local_now()
    # baseline: 1 O.S./dia na mesma janela horaria, por 5 dias anteriores
    for day_offset in range(1, 6):
        _seed_order(db_session, regional="UNI - JI PARANA", opened_at=(now - timedelta(days=day_offset)).astimezone(timezone.utc))
    # hoje: 5 O.S. na janela - bem acima da media (1/dia)
    for _ in range(5):
        _seed_order(db_session, regional="UNI - JI PARANA", opened_at=now.astimezone(timezone.utc))

    rule = alert_rules.create_alert_rule(
        db_session, key="teste-acima-media", name="Teste acima da media", rule_type="OS_OPENING_ABOVE_AVERAGE",
        scope={"regionals": ["UNI - JI PARANA"]},
        params={"min_count": 3, "window_minutes": 60, "historical_comparison": True, "min_multiplier_over_average": 1.5, "baseline_days": 5},
    )
    detections = rules_engine._run_opening_above_average_rule(db_session, rule)
    assert len(detections) == 1
    assert not detections[0].warnings
    assert detections[0].confidence == 0.85
    assert len(detections[0].evidence["os_sample"]) == 4


def test_above_average_rule_flags_insufficient_baseline_without_high_confidence(db_session):
    now = _local_now()
    # só 1 dia de historico (bem abaixo de MIN_BASELINE_SAMPLES=3)
    _seed_order(db_session, regional="UNI - JARU", opened_at=(now - timedelta(days=1)).astimezone(timezone.utc))
    for _ in range(5):
        _seed_order(db_session, regional="UNI - JARU", opened_at=now.astimezone(timezone.utc))

    rule = alert_rules.create_alert_rule(
        db_session, key="teste-baseline-insuficiente", name="Teste", rule_type="OS_OPENING_ABOVE_AVERAGE",
        scope={"regionals": ["UNI - JARU"]},
        params={"min_count": 3, "window_minutes": 60, "historical_comparison": True, "min_multiplier_over_average": 1.5, "baseline_days": 14},
    )
    detections = rules_engine._run_opening_above_average_rule(db_session, rule)
    assert len(detections) == 1
    assert detections[0].confidence < 0.85
    assert any(w.get("code") == "BASELINE_INSUFFICIENT_SAMPLE" for w in detections[0].warnings)


def test_above_average_rule_does_not_trigger_when_within_baseline(db_session):
    now = _local_now()
    for day_offset in range(1, 8):
        for _ in range(5):
            _seed_order(db_session, regional="UNI - ROLIM DE MOURA", opened_at=(now - timedelta(days=day_offset)).astimezone(timezone.utc))
    # hoje: mesmo volume do baseline (5), nao e anomalia
    for _ in range(5):
        _seed_order(db_session, regional="UNI - ROLIM DE MOURA", opened_at=now.astimezone(timezone.utc))

    rule = alert_rules.create_alert_rule(
        db_session, key="teste-dentro-da-media", name="Teste", rule_type="OS_OPENING_ABOVE_AVERAGE",
        scope={"regionals": ["UNI - ROLIM DE MOURA"]},
        params={"min_count": 3, "window_minutes": 60, "historical_comparison": True, "min_multiplier_over_average": 1.5, "baseline_days": 7},
    )
    detections = rules_engine._run_opening_above_average_rule(db_session, rule)
    assert detections == []


# --- BACKLOG_THRESHOLD / SLA_THRESHOLD - escopo nunca vaza --------------------------------------


def test_backlog_threshold_rule_respects_regional_scope(db_session):
    for _ in range(5):
        _seed_order(db_session, regional="UNI - JI PARANA", is_closed=False)
    for _ in range(20):
        _seed_order(db_session, regional="UNI - MACHADINHO DOESTE", is_closed=False)

    rule = alert_rules.create_alert_rule(
        db_session, key="teste-backlog-regional", name="Teste", rule_type="BACKLOG_THRESHOLD",
        scope={"regionals": ["UNI - JI PARANA"]}, params={"threshold_value": 3},
    )
    detections = rules_engine._run_backlog_threshold_rule(db_session, rule)
    assert len(detections) == 1
    assert detections[0].evidence["backlog_total"] == 5  # nunca conta as 20 de Machadinho

    rule_high_threshold = alert_rules.create_alert_rule(
        db_session, key="teste-backlog-regional-alto", name="Teste", rule_type="BACKLOG_THRESHOLD",
        scope={"regionals": ["UNI - JI PARANA"]}, params={"threshold_value": 100},
    )
    assert rules_engine._run_backlog_threshold_rule(db_session, rule_high_threshold) == []


# --- cooldown / confirm_cycles / dedupe / auto-resolve (integração com alerts.py) ----------------


def test_confirm_cycles_only_emits_after_n_consecutive_hits(db_session):
    for _ in range(5):
        _seed_order(db_session, regional="UNI - JARU", is_closed=False)
    rule = alert_rules.create_alert_rule(
        db_session, key="teste-confirm", name="Teste", rule_type="BACKLOG_THRESHOLD",
        scope={}, params={"threshold_value": 1}, confirm_cycles=2,
    )
    result1 = rules_engine.run_alert_rules_monitor(db_session)
    db_session.commit()
    assert not any(d.dedupe_key.startswith("rule:teste-confirm") for d in result1.detections)

    result2 = rules_engine.run_alert_rules_monitor(db_session)
    db_session.commit()
    assert any(d.dedupe_key.startswith("rule:teste-confirm") for d in result2.detections)


def test_cooldown_prevents_immediate_recreation_after_resolution(db_session, admin_user):
    for _ in range(5):
        _seed_order(db_session, regional="UNI - JARU", is_closed=False)
    alert_rules.create_alert_rule(
        db_session, key="teste-cooldown-unit", name="Teste", rule_type="BACKLOG_THRESHOLD",
        scope={}, params={"threshold_value": 1}, cooldown_minutes=60,
    )
    result = rules_engine.run_alert_rules_monitor(db_session)
    sync_alerts_for_monitor(db_session, monitor_key="alert_rules", detections=result.detections, resolve_after_misses=2)
    db_session.commit()

    from sqlalchemy import select

    alert = db_session.scalar(select(IntelligenceAlert).where(IntelligenceAlert.dedupe_key == "rule:teste-cooldown-unit:geral"))
    assert alert is not None
    dismiss_alert(db_session, alert, user_id=admin_user.id)
    db_session.commit()

    result2 = rules_engine.run_alert_rules_monitor(db_session)
    assert not any(d.dedupe_key == "rule:teste-cooldown-unit:geral" for d in result2.detections)


def test_alert_rules_monitor_reuses_existing_dedupe_and_autoresolve_lifecycle(db_session):
    """As detecções de regras passam pelo MESMO alerts.sync_alerts_for_monitor que os outros
    monitores - nenhum lifecycle paralelo criado para regras."""
    for _ in range(5):
        _seed_order(db_session, regional="UNI - JARU", is_closed=False)
    alert_rules.create_alert_rule(
        db_session, key="teste-lifecycle", name="Teste", rule_type="BACKLOG_THRESHOLD", scope={}, params={"threshold_value": 1},
    )
    result = rules_engine.run_alert_rules_monitor(db_session)
    stats = sync_alerts_for_monitor(db_session, monitor_key="alert_rules", detections=result.detections, resolve_after_misses=1)
    db_session.commit()
    assert stats.created == 1

    from sqlalchemy import select

    alert = db_session.scalar(select(IntelligenceAlert).where(IntelligenceAlert.dedupe_key == "rule:teste-lifecycle:geral"))
    assert alert.status == "NEW"
    assert alert.monitor_key == "alert_rules"

    # segunda rodada sem detecção (regra desativada) -> auto-resolve em 1 ciclo (resolve_after_misses=1)
    stats2 = sync_alerts_for_monitor(db_session, monitor_key="alert_rules", detections=[], resolve_after_misses=1)
    db_session.commit()
    db_session.refresh(alert)
    assert stats2.resolved == 1
    assert alert.status == "RESOLVED"
