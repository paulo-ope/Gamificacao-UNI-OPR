"""Achado real da auditoria de performance 2026-08-27: `_sync_opa_dimensions` buscava
usuários/motivos/departamentos/etiquetas/CLIENTES do OPA Suite em TODA sincronização (a cada
~20 min, todo import manual, todo backfill) - o cadastro de clientes sozinho tem mais de 100 mil
registros na base real, medido em mais de 100 SEGUNDOS só pra essa dimensão, toda vez. Além
disso, `_sync_dimension_records` fazia um SELECT por registro pra decidir criar vs. atualizar -
mais de 100 mil consultas individuais numa única sincronização.

Corrigido em duas frentes: (1) throttle configurável (padrão 24h) - entre uma janela e outra, usa
só o cache já no banco, sem nenhuma chamada à API; (2) upsert em lote no
`_sync_dimension_records`, carregando os existentes de uma vez em vez de um SELECT por registro."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.support.models import SupportOpaDimension
from app.modules.support.opa_ingestion import (
    SUPPORT_OPA_DIMENSIONS_LAST_SYNCED_AT_KEY,
    SUPPORT_OPA_DIMENSIONS_REFRESH_HOURS_KEY,
    _dimensions_due_for_refresh,
    _sync_dimension_records,
    _sync_opa_dimensions,
)
from app.services.calculation import upsert_setting


class _CountingClient:
    """Fake client que conta quantas vezes cada coleção foi buscada - o throttle deve manter
    essa contagem em 1 chamada por coleção mesmo com múltiplos ciclos de sincronização."""

    def __init__(self):
        self.calls = {"user": 0, "reason": 0, "department": 0, "tag": 0, "customer": 0}

    def list_users(self):
        self.calls["user"] += 1
        return [{"id": "U1", "nome": "Ana"}]

    def list_reasons(self):
        self.calls["reason"] += 1
        return [{"id": "R1", "nome": "Suporte"}]

    def list_departments(self):
        self.calls["department"] += 1
        return [{"id": "D1", "nome": "Financeiro"}]

    def list_tags(self):
        self.calls["tag"] += 1
        return [{"id": "T1", "nome": "Urgente"}]

    def list_clients(self):
        self.calls["customer"] += 1
        return [{"id": f"C{i}", "nome": f"Cliente {i}"} for i in range(50)]


def test_sync_dimension_records_batches_the_existence_check(db_session):
    now = datetime.now(timezone.utc)
    records = [{"id": f"C{i}", "nome": f"Cliente {i}"} for i in range(500)]

    _sync_dimension_records(db_session, dimension_type="customer", records=records, now=now)
    db_session.commit()

    rows = db_session.query(SupportOpaDimension).filter_by(dimension_type="customer").all()
    assert len(rows) == 500
    assert {row.source_id for row in rows} == {f"C{i}" for i in range(500)}

    # Segunda passada com nomes atualizados - deve fazer UPDATE (mesmas 500 linhas), não
    # duplicar nem falhar por causa do lote.
    updated_records = [{"id": f"C{i}", "nome": f"Cliente Renomeado {i}"} for i in range(500)]
    _sync_dimension_records(db_session, dimension_type="customer", records=updated_records, now=now)
    db_session.commit()

    rows_after = db_session.query(SupportOpaDimension).filter_by(dimension_type="customer").all()
    assert len(rows_after) == 500
    assert all(row.name.startswith("Cliente Renomeado") for row in rows_after)


def test_dimensions_due_for_refresh_defaults_to_true_when_never_synced(db_session):
    assert _dimensions_due_for_refresh(db_session, datetime.now(timezone.utc)) is True


def test_dimensions_due_for_refresh_respects_configured_window(db_session):
    now = datetime.now(timezone.utc)
    upsert_setting(db_session, SUPPORT_OPA_DIMENSIONS_LAST_SYNCED_AT_KEY, (now - timedelta(hours=2)).isoformat())
    upsert_setting(db_session, SUPPORT_OPA_DIMENSIONS_REFRESH_HOURS_KEY, "24")
    db_session.commit()

    assert _dimensions_due_for_refresh(db_session, now) is False

    # last_synced foi há 2h (relativo a `now`) - com 24h configuradas, só fica due depois que o
    # total decorrido desde o último sync passar de 24h.
    assert _dimensions_due_for_refresh(db_session, now + timedelta(hours=20)) is False  # 22h decorridas
    assert _dimensions_due_for_refresh(db_session, now + timedelta(hours=23)) is True  # 25h decorridas


def test_sync_opa_dimensions_only_calls_the_client_once_within_the_window(db_session):
    client = _CountingClient()
    now = datetime.now(timezone.utc)

    first = _sync_opa_dimensions(db_session, client, now)
    db_session.commit()
    assert client.calls == {"user": 1, "reason": 1, "department": 1, "tag": 1, "customer": 1}
    assert first["customer"]["C0"] == "Cliente 0"

    # Segundo ciclo, poucos minutos depois - dentro da janela de 24h, não deve chamar a API de
    # novo, mas o mapa de dimensões continua correto (lido do cache local).
    second = _sync_opa_dimensions(db_session, client, now + timedelta(minutes=15))
    db_session.commit()
    assert client.calls == {"user": 1, "reason": 1, "department": 1, "tag": 1, "customer": 1}
    assert second["customer"]["C0"] == "Cliente 0"
    assert second["user"]["U1"] == "Ana"

    # Terceiro ciclo, depois da janela - deve buscar de novo.
    third = _sync_opa_dimensions(db_session, client, now + timedelta(hours=25))
    db_session.commit()
    assert client.calls == {"user": 2, "reason": 2, "department": 2, "tag": 2, "customer": 2}
    assert third["customer"]["C0"] == "Cliente 0"


def test_sync_opa_dimensions_force_bypasses_the_throttle(db_session):
    client = _CountingClient()
    now = datetime.now(timezone.utc)

    _sync_opa_dimensions(db_session, client, now)
    db_session.commit()
    assert client.calls["customer"] == 1

    _sync_opa_dimensions(db_session, client, now + timedelta(minutes=5), force=True)
    db_session.commit()
    assert client.calls["customer"] == 2


def test_sync_settings_endpoint_exposes_and_updates_dimensions_refresh_hours(client):
    response = client.get("/api/support/opa-sync-settings")
    assert response.status_code == 200
    assert response.json()["dimensions_refresh_hours"] == 24

    update = client.put("/api/support/opa-sync-settings", json={"dimensions_refresh_hours": 48})
    assert update.status_code == 200
    assert update.json()["dimensions_refresh_hours"] == 48

    reread = client.get("/api/support/opa-sync-settings")
    assert reread.json()["dimensions_refresh_hours"] == 48
