"""Regression tests for backend/app/services/cpk_health.py and its wiring into calculation.py."""
from sqlalchemy import select

from app.models import AppSetting, CpkRegionalSnapshot
from app.services import calculation, cpk_health
from app.services.cpk_client import CpkApiError


class _FakeCpkClient:
    def __init__(self, payload):
        self._payload = payload

    def get_relatorio_estruturado(self, ano, mes):
        return self._payload


def _payload(mes_fechado=True, regionais=None):
    return {"ano": 2026, "mes": 7, "mes_fechado": mes_fechado, "regionais": regionais or []}


def test_sync_ignores_matriz_and_unmapped_regionals(db_session, monkeypatch):
    """Regression: "Matriz" nao tem regional de gamificacao correspondente (so filiais de campo
    existem la) - decisao confirmada com o usuario. Qualquer outro nome nao mapeado tambem deve
    ser ignorado, nao travar a sincronizacao inteira."""
    payload = _payload(regionais=[
        {"regional": "Matriz", "agregado": {"status": "bateu", "cpk_realizado": 0.9, "cpk_meta": 1.0}},
        {"regional": "Ji-Paraná", "agregado": {"status": "nao_bateu", "cpk_realizado": 1.2, "cpk_meta": 0.9}},
        {"regional": "Planeta Desconhecido", "agregado": {"status": "bateu"}},
    ])
    monkeypatch.setattr(cpk_health, "get_cpk_client", lambda: _FakeCpkClient(payload))

    result = cpk_health.sync_cpk_snapshot(db_session, 2026, 7)
    db_session.commit()

    assert result["synced"] == 1
    assert result["skipped_unmapped"] == 2

    rows = list(db_session.scalars(select(CpkRegionalSnapshot)))
    assert len(rows) == 1
    assert rows[0].regional == "UNI - JI PARANA"
    assert rows[0].status == "fora_meta"
    assert rows[0].cpk_realizado == 1.2


def test_sync_applies_partial_status_even_when_month_is_still_open(db_session, monkeypatch):
    """Decisao do usuario (2026-07-31): o bonus/penalidade de CPK deve refletir o momento atual
    da apuracao, mesmo com o mes ainda em andamento (numeros parciais) - nao espera mais o mes
    fechar oficialmente pra aplicar o ajuste real de pagamento. 'mes_fechado=false' continua
    sendo gravado no snapshot, mas so como metadado de exibicao (ex.: tag "provisorio" na tela),
    nao trava mais o status em 'sem_base'."""
    payload = _payload(mes_fechado=False, regionais=[
        {"regional": "Alvorada D'oeste", "agregado": {"status": "bateu", "cpk_realizado": 0.8, "cpk_meta": 0.9}},
    ])
    monkeypatch.setattr(cpk_health, "get_cpk_client", lambda: _FakeCpkClient(payload))

    cpk_health.sync_cpk_snapshot(db_session, 2026, 7)
    db_session.commit()

    row = db_session.scalar(select(CpkRegionalSnapshot))
    assert row.status == "na_meta"
    assert row.mes_fechado is False, "metadado de exibicao continua registrando que e um numero parcial"


def test_sync_upserts_instead_of_duplicating(db_session, monkeypatch):
    """Rodar a sincronizacao duas vezes pro mesmo (ano, mes, regional) deve atualizar a linha
    existente, nao criar uma segunda."""
    payload = _payload(regionais=[
        {"regional": "Jaru", "agregado": {"status": "bateu", "cpk_realizado": 0.8, "cpk_meta": 0.9}},
    ])
    monkeypatch.setattr(cpk_health, "get_cpk_client", lambda: _FakeCpkClient(payload))
    cpk_health.sync_cpk_snapshot(db_session, 2026, 7)
    db_session.commit()

    payload["regionais"][0]["agregado"]["status"] = "nao_bateu"
    cpk_health.sync_cpk_snapshot(db_session, 2026, 7)
    db_session.commit()

    rows = list(db_session.scalars(select(CpkRegionalSnapshot).where(CpkRegionalSnapshot.regional == "UNI - JARU")))
    assert len(rows) == 1
    assert rows[0].status == "fora_meta"


def test_get_cpk_adjustment_by_regional_maps_status_to_points(db_session):
    db_session.add_all([
        CpkRegionalSnapshot(reference_year=2026, reference_month=7, regional="UNI - JARU", status="na_meta"),
        CpkRegionalSnapshot(reference_year=2026, reference_month=7, regional="UNI - JI PARANA", status="fora_meta"),
        CpkRegionalSnapshot(reference_year=2026, reference_month=7, regional="UNI - MACHADINHO DOESTE", status="sem_base"),
    ])
    db_session.flush()

    adjustments = cpk_health.get_cpk_adjustment_by_regional(db_session, 2026, 7)

    assert adjustments["UNI - JARU"] == 0.2
    assert adjustments["UNI - JI PARANA"] == -0.2
    assert adjustments["UNI - MACHADINHO DOESTE"] == 0.0


def test_get_cpk_adjustment_respects_configured_bonus_points(db_session):
    db_session.add(AppSetting(key="cpk_bonus_points", value="0.3"))
    db_session.add(CpkRegionalSnapshot(reference_year=2026, reference_month=7, regional="UNI - JARU", status="na_meta"))
    db_session.flush()

    adjustments = cpk_health.get_cpk_adjustment_by_regional(db_session, 2026, 7)

    assert adjustments["UNI - JARU"] == 0.3


def test_apply_cpk_adjustment_sums_into_multiplier_and_floors_at_zero(db_session):
    db_session.add_all([
        CpkRegionalSnapshot(reference_year=2026, reference_month=7, regional="UNI - JARU", status="na_meta"),
        CpkRegionalSnapshot(reference_year=2026, reference_month=7, regional="UNI - JI PARANA", status="fora_meta"),
    ])
    db_session.flush()

    health_by_regional = {
        "UNI - JARU": {"multiplier": 1.5},
        "UNI - JI PARANA": {"multiplier": 0.1},
        "UNI - MACHADINHO DOESTE": {"multiplier": 1.0},  # sem snapshot pra esse periodo
    }

    result = calculation._apply_cpk_adjustment(db_session, health_by_regional, 7, 2026)

    assert result["UNI - JARU"]["multiplier"] == 1.7
    assert result["UNI - JI PARANA"]["multiplier"] == 0.0, "nunca deve ficar negativo"
    assert result["UNI - MACHADINHO DOESTE"]["multiplier"] == 1.0, "sem snapshot -> sem ajuste"


def test_apply_cpk_adjustment_does_not_sync_when_disabled(db_session, monkeypatch):
    """Por padrao (cpk_sync_enabled ausente/false), _apply_cpk_adjustment nunca chama a API ao
    vivo - so le o que ja estiver no snapshot local."""
    called = []
    monkeypatch.setattr(cpk_health, "sync_cpk_snapshot", lambda *a, **k: called.append(a))

    calculation._apply_cpk_adjustment(db_session, {}, 7, 2026)

    assert called == []


def test_apply_cpk_adjustment_auto_syncs_when_enabled(db_session, monkeypatch):
    """Com cpk_sync_enabled=true, todo recalculo busca o snapshot mais recente na API antes de
    aplicar o ajuste - nao depende mais de alguem clicar em 'Sincronizar agora'."""
    db_session.add(AppSetting(key=cpk_health.CPK_SYNC_ENABLED_SETTING, value="true"))
    db_session.flush()
    called = []
    monkeypatch.setattr(cpk_health, "sync_cpk_snapshot", lambda db, ano, mes: called.append((ano, mes)))

    calculation._apply_cpk_adjustment(db_session, {}, 7, 2026)

    assert called == [(2026, 7)]


def test_apply_cpk_adjustment_falls_back_to_cache_when_sync_fails(db_session, monkeypatch):
    """Se a API da frota estiver fora do ar no momento do calculo de folha, o erro nao pode
    travar o calculo - o ajuste continua vindo do ultimo snapshot valido ja salvo."""
    db_session.add(AppSetting(key=cpk_health.CPK_SYNC_ENABLED_SETTING, value="true"))
    db_session.add(CpkRegionalSnapshot(reference_year=2026, reference_month=7, regional="UNI - JARU", status="na_meta"))
    db_session.flush()

    def _boom(db, ano, mes):
        raise CpkApiError("timeout")

    monkeypatch.setattr(cpk_health, "sync_cpk_snapshot", _boom)

    result = calculation._apply_cpk_adjustment(db_session, {"UNI - JARU": {"multiplier": 1.0}}, 7, 2026)

    assert result["UNI - JARU"]["multiplier"] == 1.2
