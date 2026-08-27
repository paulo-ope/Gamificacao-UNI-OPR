"""Achado da auditoria de performance 2026-08-27: POST /imports/ixc-backfill buscava um mes
inteiro da API do IXC (paginado) rodando inline na requisicao HTTP, arriscando timeout - mesma
classe de problema ja corrigida em support/opa-imports. Virou job em background (202 na hora,
resultado consultavel em GET /imports/runs)."""
from __future__ import annotations

import app.api.routes.imports as imports_module


class _SessionLocalStub:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


def test_ixc_backfill_queues_and_runs_in_background(client, db_session, monkeypatch):
    monkeypatch.setattr(imports_module, "SessionLocal", _SessionLocalStub(db_session))
    monkeypatch.setattr(imports_module, "ixc_import_lock_busy", lambda db: False)
    monkeypatch.setattr(imports_module, "get_ixc_client", lambda: "fake-client")

    calls = []

    def fake_backfill(db, client, *, year, month, imported_by):
        calls.append((year, month, imported_by))
        return {"backfill_period": f"{year:04d}-{month:02d}"}

    monkeypatch.setattr(imports_module, "backfill_ixc_service_orders", fake_backfill)

    response = client.post("/api/imports/ixc-backfill", json={"year": 2026, "month": 7})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["year"] == 2026
    assert body["month"] == 7
    # BackgroundTasks no TestClient roda antes da resposta terminar de ser processada - o job ja
    # deve ter sido executado quando chegamos aqui.
    assert calls == [(2026, 7, calls[0][2])]


def test_ixc_backfill_rejects_when_busy(client, monkeypatch):
    monkeypatch.setattr(imports_module, "ixc_import_lock_busy", lambda db: True)

    response = client.post("/api/imports/ixc-backfill", json={"year": 2026, "month": 7})

    assert response.status_code == 409
