from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models import (
    AppSetting,
    CalculationRun,
    Collaborator,
    CollaboratorPointBalance,
    ImportRun,
    ImportServiceOrderAudit,
    PointBalanceEntry,
    ServiceOrder,
)
from app.modules.operations.models import OperationOrder
from app.services import ixc_importer, operations_sync
from app.services.ixc_importer import IxcImportLockTimeoutError
from app.services.operations_sync import (
    OPERATIONS_SYNC_WATERMARK_KEY,
    RECONCILIATION_IMPORT_FILENAME,
    _resolve_collaborator,
    backfill_collaborator_ixc_ids,
    reconcile_missing_service_orders_from_operations,
    reconcile_recent_missing_service_orders_from_operations,
    run_operations_to_service_orders_sync,
    sync_service_orders_from_operations,
)
from app.services.scoring_detail import sla_inside


def _patch_advisory_lock(monkeypatch, session, *, acquired: bool, on_xact_acquire=None):
    """SQLite (usado nos testes) nao entende pg_try_advisory_lock/pg_advisory_unlock (funcoes
    exclusivas do Postgres) - simula a resposta dessas duas chamadas especificas e deixa
    qualquer outra query passar direto pro execute real, pra poder exercitar o lock consultivo
    (_ixc_import_lock) sem precisar de um Postgres de verdade no teste."""
    # MAX_WAIT=0 faz o loop de espera tentar exatamente uma vez; POLL_INTERVAL precisa ser > 0
    # (nao 0.0) - com os dois zerados, `waited` nunca ultrapassa 0.0 e o loop de espera do
    # _ixc_import_lock nunca termina quando o lock nao e adquirido (achado real: travou o
    # primeiro rascunho deste teste).
    monkeypatch.setattr(ixc_importer, "IXC_IMPORT_LOCK_MAX_WAIT_SECONDS", 0.0)
    monkeypatch.setattr(ixc_importer, "IXC_IMPORT_LOCK_POLL_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(operations_sync, "IXC_IMPORT_LOCK_MAX_WAIT_SECONDS", 0.0)
    monkeypatch.setattr(operations_sync, "IXC_IMPORT_LOCK_POLL_INTERVAL_SECONDS", 0.01)

    real_execute = session.execute

    class _ScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar(self):
            if on_xact_acquire is not None:
                on_xact_acquire()
            return self._value

    def fake_execute(statement, *args, **kwargs):
        sql = str(statement)
        if "pg_try_advisory_xact_lock" in sql:
            return _ScalarResult(acquired)
        if "pg_try_advisory_lock" in sql:
            return _ScalarResult(acquired)
        if "pg_advisory_unlock" in sql:
            return _ScalarResult(True)
        return real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(session, "execute", fake_execute)


def test_reactivating_a_collaborator_does_not_reset_is_registered(db_session, make_collaborator):
    """Regression (audit finding B3): a collaborator manually deactivated via the registry
    screen's "Desativar" toggle (active=False) while still is_registered=True (e.g. temporary
    leave) got their registration silently wiped to False the next time a new O.S synced under
    their ixc_employee_id/name - zeroing their pay until someone noticed and re-registered them
    by hand. Reactivating must only flip `active` back on; it must not touch `is_registered`."""
    collaborator = make_collaborator(name="Tecnico De Ferias", registered=True)
    collaborator.active = False
    collaborator.ixc_employee_id = 4242
    db_session.flush()

    resolved, created = _resolve_collaborator(
        db_session,
        name="Tecnico De Ferias",
        regional=collaborator.regional,
        ixc_employee_id=4242,
        collaborators_cache=[collaborator],
    )

    assert created is False
    assert resolved.active is True
    assert resolved.is_registered is True, "reativar nao deveria derrubar um cadastro que ja existia"


def _make_operation_order(**overrides):
    defaults = dict(
        source="ixc",
        source_order_id="9001",
        order_code="IXC-9001",
        contract_id="C-9001",
        customer_login="cliente9001",
        customer_name="Cliente Nove Mil e Um",
        regional="UNI SUL",
        sector="Suporte Externo",
        os_type="Manutenção",
        os_subject="Reparo",
        diagnosis="Falha",
        responsible="Tecnico Um",
        responsible_ixc_id=555,
        status="Finalizada",
        status_code="F",
        is_closed=True,
        sla_status="on_time",
        sla_target_hours=24.0,
        elapsed_hours=10.5,
        opened_at=datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 5, 18, 30, tzinfo=timezone.utc),
        raw_payload={},
    )
    defaults.update(overrides)
    return OperationOrder(**defaults)


def _reconcile_window():
    return (
        datetime(2026, 6, 1, tzinfo=timezone.utc),
        datetime(2026, 7, 1, tzinfo=timezone.utc),
    )


def _add_existing_service_order(db_session, collaborator: Collaborator, order: OperationOrder, **overrides):
    defaults = dict(
        os_code=order.order_code,
        contract_id=order.contract_id or "NAO IDENTIFICADO",
        customer_login=order.customer_login,
        customer_name=order.customer_name or "Não informado",
        collaborator_id=collaborator.id,
        regional=collaborator.regional,
        os_type=order.os_type or "Manutenção",
        os_subject=order.os_subject or "Reparo",
        diagnosis=order.diagnosis or "Não informado",
        status="Concluída",
        sla_status=order.sla_status or "",
        sla_hours=order.sla_target_hours,
        closing_time_hours=order.elapsed_hours,
        opened_at=order.opened_at,
        closed_at=order.closed_at,
        is_warranty=False,
        is_recurrence=False,
        is_priority=False,
        has_reschedule=False,
        has_pending=False,
    )
    defaults.update(overrides)
    service_order = ServiceOrder(**defaults)
    db_session.add(service_order)
    db_session.flush()
    return service_order


def _reconcile(
    db_session,
    monkeypatch,
    *,
    dry_run=False,
    batch_size=25,
    on_xact_acquire=None,
    **filters,
):
    _patch_advisory_lock(monkeypatch, db_session, acquired=True, on_xact_acquire=on_xact_acquire)
    date_from, date_to = _reconcile_window()
    return reconcile_missing_service_orders_from_operations(
        db_session,
        date_from=date_from,
        date_to=date_to,
        dry_run=dry_run,
        batch_size=batch_size,
        **filters,
    )


def test_sync_copies_sla_fields_and_matches_collaborator_by_ixc_id(db_session, make_collaborator):
    """A sincronizacao deve copiar o SLA calculado em operations_orders (nao recalcular), e casar o
    colaborador pelo id do IXC mesmo quando o nome cadastrado diverge do nome vindo do IXC."""
    collaborator = make_collaborator(name="Tecnico Grafia Diferente", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    db_session.flush()

    order = _make_operation_order()
    db_session.add(order)
    db_session.flush()

    result = sync_service_orders_from_operations(db_session)
    db_session.commit()

    assert result["summary"]["created_count"] == 1
    service_order = db_session.scalars(select(ServiceOrder).where(ServiceOrder.os_code == "IXC-9001")).one()

    assert service_order.collaborator_id == collaborator.id
    assert service_order.sla_status == order.sla_status
    assert service_order.sla_hours == order.sla_target_hours
    assert service_order.closing_time_hours == order.elapsed_hours
    assert sla_inside(service_order) is True


def test_sync_marks_out_of_time_orders_consistently_with_operations(db_session, make_collaborator):
    """Quando a operacao analitica classifica a O.S. como out_of_time, a mesma leitura deve valer
    para o calculo de pontuacao - nao pode haver um SLA na tela analitica e outro na gamificacao."""
    make_collaborator(name="Tecnico Dois", regional="UNI SUL")
    order = _make_operation_order(
        source_order_id="9002",
        order_code="IXC-9002",
        responsible="Tecnico Dois",
        responsible_ixc_id=556,
        sla_status="out_of_time",
        sla_target_hours=6.0,
        elapsed_hours=30.25,
    )
    db_session.add(order)
    db_session.flush()

    sync_service_orders_from_operations(db_session)
    db_session.commit()

    service_order = db_session.scalars(select(ServiceOrder).where(ServiceOrder.os_code == "IXC-9002")).one()
    assert sla_inside(service_order) is False


def test_sync_ignores_orders_outside_the_three_technical_sectors(db_session, make_collaborator):
    """operations_orders cobre setores alem dos tecnicos (o modulo de operacoes analiticas serve a
    analytics organizacional mais amplo). A gamificacao so pode pontuar Suporte Externo/Radio/Fibra -
    uma O.S. de outro setor (ex. Comercial) nao pode virar ServiceOrder nem criar um colaborador
    fantasma para o atendente daquele setor."""
    order = _make_operation_order(
        source_order_id="9004",
        order_code="IXC-9004",
        sector="Comercial",
        responsible="Atendente Comercial",
        responsible_ixc_id=888,
    )
    db_session.add(order)
    db_session.flush()

    result = sync_service_orders_from_operations(db_session)
    db_session.commit()

    assert result["summary"]["created_count"] == 0
    assert db_session.scalars(select(ServiceOrder).where(ServiceOrder.os_code == "IXC-9004")).first() is None
    assert (
        db_session.scalars(select(Collaborator).where(Collaborator.name == "Atendente Comercial")).first()
        is None
    )


def test_reconciliation_creates_missing_eligible_service_order(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    db_session.add(_make_operation_order())
    db_session.flush()

    result = _reconcile(db_session, monkeypatch)

    service_order = db_session.scalars(select(ServiceOrder).where(ServiceOrder.os_code == "IXC-9001")).one()
    assert service_order.collaborator_id == collaborator.id
    assert result["created_count"] == 1
    assert result["ready_to_create"] == 1
    assert result["created_os_codes"] == ["IXC-9001"]
    import_run = db_session.scalars(select(ImportRun).where(ImportRun.filename == RECONCILIATION_IMPORT_FILENAME)).one()
    audit = db_session.scalars(select(ImportServiceOrderAudit).where(ImportServiceOrderAudit.import_run_id == import_run.id)).one()
    assert audit.action == "created"
    assert audit.reason == "Created by operations_orders reconciliation"


def test_reconciliation_existing_by_os_code_does_not_duplicate(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    order = _make_operation_order()
    db_session.add(order)
    db_session.flush()
    _add_existing_service_order(db_session, collaborator, order)

    result = _reconcile(db_session, monkeypatch)

    assert result["existing_by_os_code"] == 1
    assert result["created_count"] == 0
    assert db_session.scalar(select(func.count(ServiceOrder.id))) == 1


def test_reconciliation_existing_by_fallback_does_not_duplicate(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    order = _make_operation_order()
    db_session.add(order)
    db_session.flush()
    _add_existing_service_order(db_session, collaborator, order, os_code="LEGACY-9001")

    result = _reconcile(db_session, monkeypatch)

    assert result["existing_by_fallback"] == 1
    assert result["created_count"] == 0
    assert db_session.scalar(select(func.count(ServiceOrder.id))) == 1


def test_reconciliation_is_idempotent_on_second_run(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    db_session.add(_make_operation_order())
    db_session.flush()

    first = _reconcile(db_session, monkeypatch)
    second = _reconcile(db_session, monkeypatch)

    assert first["created_count"] == 1
    assert second["created_count"] == 0
    assert second["existing_by_os_code"] == 1
    assert db_session.scalar(select(func.count(ServiceOrder.id))) == 1


def test_reconciliation_blocks_paid_period(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    db_session.add(_make_operation_order())
    db_session.add(CalculationRun(reference_month=6, reference_year=2026, regional=None, point_value=2.5, status="paid"))
    db_session.flush()

    result = _reconcile(db_session, monkeypatch)

    assert result["blocked_paid_period"] == 1
    assert result["created_count"] == 0
    assert db_session.scalar(select(func.count(ServiceOrder.id))) == 0


def test_reconciliation_blocks_paid_period_using_porto_velho_month_boundary(
    db_session, make_collaborator, monkeypatch
):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    db_session.add(
        _make_operation_order(
            source_order_id="9009",
            order_code="IXC-9009",
            opened_at=datetime(2026, 8, 31, 22, 0, tzinfo=timezone.utc),
            closed_at=datetime(2026, 9, 1, 3, 30, tzinfo=timezone.utc),
        )
    )
    db_session.add(CalculationRun(reference_month=8, reference_year=2026, regional=None, point_value=2.5, status="paid"))
    db_session.flush()
    _patch_advisory_lock(monkeypatch, db_session, acquired=True)

    result = reconcile_missing_service_orders_from_operations(
        db_session,
        date_from=datetime(2026, 8, 1, 4, 0, tzinfo=timezone.utc),
        date_to=datetime(2026, 9, 1, 4, 0, tzinfo=timezone.utc),
        dry_run=False,
    )

    assert result["blocked_paid_period"] == 1
    assert result["created_count"] == 0
    assert db_session.scalar(select(func.count(ServiceOrder.id))) == 0


def test_reconciliation_missing_collaborator_is_invalid_and_not_created(db_session, monkeypatch):
    db_session.add(_make_operation_order(responsible="Tecnico Desconhecido", responsible_ixc_id=9999))
    db_session.flush()

    result = _reconcile(db_session, monkeypatch)

    assert result["invalid_collaborator"] == 1
    assert result["created_count"] == 0
    assert db_session.scalar(select(func.count(Collaborator.id))) == 0
    assert db_session.scalar(select(func.count(ServiceOrder.id))) == 0


def test_reconciliation_ignores_ineligible_sector_open_and_out_of_period_orders(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    db_session.add_all(
        [
            _make_operation_order(source_order_id="9004", order_code="IXC-9004", sector="Comercial"),
            _make_operation_order(source_order_id="9005", order_code="IXC-9005", is_closed=False),
            _make_operation_order(
                source_order_id="9006",
                order_code="IXC-9006",
                opened_at=datetime(2026, 7, 2, 8, 0, tzinfo=timezone.utc),
                closed_at=datetime(2026, 7, 2, 18, 0, tzinfo=timezone.utc),
            ),
        ]
    )
    db_session.flush()

    result = _reconcile(db_session, monkeypatch)

    assert result["analyzed_count"] == 0
    assert result["created_count"] == 0
    assert db_session.scalar(select(func.count(ServiceOrder.id))) == 0


def test_reconciliation_preserves_watermark_in_dry_run_and_real_run(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    db_session.add(AppSetting(key=OPERATIONS_SYNC_WATERMARK_KEY, value="2026-07-01T00:00:00+00:00"))
    db_session.add(_make_operation_order())
    db_session.flush()

    dry_run = _reconcile(db_session, monkeypatch, dry_run=True)
    watermark_after_dry_run = db_session.scalar(
        select(AppSetting.value).where(AppSetting.key == OPERATIONS_SYNC_WATERMARK_KEY)
    )
    real_run = _reconcile(db_session, monkeypatch)
    watermark_after_real_run = db_session.scalar(
        select(AppSetting.value).where(AppSetting.key == OPERATIONS_SYNC_WATERMARK_KEY)
    )

    assert dry_run["ready_to_create"] == 1
    assert real_run["created_count"] == 1
    assert watermark_after_dry_run == "2026-07-01T00:00:00+00:00"
    assert watermark_after_real_run == "2026-07-01T00:00:00+00:00"


def test_reconciliation_dry_run_has_no_side_effects(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    db_session.add(AppSetting(key=OPERATIONS_SYNC_WATERMARK_KEY, value="2026-07-01T00:00:00+00:00"))
    db_session.add(_make_operation_order())
    db_session.flush()
    before = {
        "service_orders": db_session.scalar(select(func.count(ServiceOrder.id))),
        "collaborators": db_session.scalar(select(func.count(Collaborator.id))),
        "imports": db_session.scalar(select(func.count(ImportRun.id))),
        "audits": db_session.scalar(select(func.count(ImportServiceOrderAudit.id))),
        "watermark": db_session.scalar(select(AppSetting.value).where(AppSetting.key == OPERATIONS_SYNC_WATERMARK_KEY)),
    }

    result = _reconcile(db_session, monkeypatch, dry_run=True)

    after = {
        "service_orders": db_session.scalar(select(func.count(ServiceOrder.id))),
        "collaborators": db_session.scalar(select(func.count(Collaborator.id))),
        "imports": db_session.scalar(select(func.count(ImportRun.id))),
        "audits": db_session.scalar(select(func.count(ImportServiceOrderAudit.id))),
        "watermark": db_session.scalar(select(AppSetting.value).where(AppSetting.key == OPERATIONS_SYNC_WATERMARK_KEY)),
    }
    assert result["ready_to_create"] == 1
    assert before == after


def test_reconciliation_dry_run_does_not_create_missing_collaborator_or_audit_rows(db_session, monkeypatch):
    db_session.add(_make_operation_order(responsible="Tecnico Novo", responsible_ixc_id=321))
    db_session.flush()

    result = _reconcile(db_session, monkeypatch, dry_run=True)

    assert result["invalid_collaborator"] == 1
    assert db_session.scalar(select(func.count(Collaborator.id))) == 0
    assert db_session.scalar(select(func.count(ImportRun.id))) == 0
    assert db_session.scalar(select(func.count(ImportServiceOrderAudit.id))) == 0


def test_reconciliation_rolls_back_only_the_failed_batch(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    db_session.add_all(
        [
            _make_operation_order(source_order_id="9001", order_code="IXC-9001"),
            _make_operation_order(
                source_order_id="9002",
                order_code="IXC-9002",
                contract_id="C-9002",
                customer_login="cliente9002",
                opened_at=datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc),
                closed_at=datetime(2026, 6, 6, 18, 0, tzinfo=timezone.utc),
            ),
        ]
    )
    db_session.flush()

    original_service_order = operations_sync.ServiceOrder

    def exploding_service_order(**kwargs):
        if kwargs.get("os_code") == "IXC-9002":
            raise RuntimeError("falha simulada")
        return original_service_order(**kwargs)

    monkeypatch.setattr(operations_sync, "ServiceOrder", exploding_service_order)

    result = _reconcile(db_session, monkeypatch, batch_size=1)

    assert result["created_count"] == 1
    assert result["error_count"] == 1
    assert db_session.scalars(select(ServiceOrder).where(ServiceOrder.os_code == "IXC-9001")).one()
    assert db_session.scalars(select(ServiceOrder).where(ServiceOrder.os_code == "IXC-9002")).first() is None
    assert len(result["batches"]) == 2
    assert result["batches"][0]["created_count"] == 1
    assert result["batches"][1]["error_count"] == 1


def test_reconciliation_transaction_lock_is_released_after_commit(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    db_session.add(_make_operation_order())
    db_session.flush()

    state = {"held": False, "commit_releases": 0}

    def on_xact_acquire():
        assert state["held"] is False
        state["held"] = True

    real_commit = db_session.commit

    def tracking_commit():
        real_commit()
        if state["held"]:
            state["commit_releases"] += 1
        state["held"] = False

    monkeypatch.setattr(db_session, "commit", tracking_commit)

    result = _reconcile(db_session, monkeypatch, on_xact_acquire=on_xact_acquire)

    assert result["created_count"] == 1
    assert state == {"held": False, "commit_releases": 1}


def test_reconciliation_transaction_lock_is_released_after_rollback(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    order = _make_operation_order()
    db_session.add(order)
    db_session.flush()
    _add_existing_service_order(db_session, collaborator, order)

    original_find = operations_sync.find_existing_service_order

    def stale_find_existing(db, payload):
        if payload.get("os_code") == "IXC-9001":
            return None
        return original_find(db, payload)

    monkeypatch.setattr(operations_sync, "find_existing_service_order", stale_find_existing)

    state = {"held": False, "rollback_releases": 0}

    def on_xact_acquire():
        assert state["held"] is False
        state["held"] = True

    real_rollback = db_session.rollback

    def tracking_rollback():
        real_rollback()
        if state["held"]:
            state["rollback_releases"] += 1
        state["held"] = False

    monkeypatch.setattr(db_session, "rollback", tracking_rollback)

    result = _reconcile(db_session, monkeypatch, on_xact_acquire=on_xact_acquire)

    assert result["created_count"] == 0
    assert result["error_count"] == 1
    assert state == {"held": False, "rollback_releases": 1}


def test_reconciliation_integrity_error_rolls_back_failed_batch_and_keeps_previous_commit(
    db_session, make_collaborator, monkeypatch
):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    first = _make_operation_order(source_order_id="9001", order_code="IXC-9001")
    second = _make_operation_order(
        source_order_id="9002",
        order_code="IXC-9002",
        contract_id="C-9002",
        customer_login="cliente9002",
        opened_at=datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 6, 6, 18, 0, tzinfo=timezone.utc),
    )
    db_session.add_all([first, second])
    db_session.flush()
    _add_existing_service_order(db_session, collaborator, second)

    original_find = operations_sync.find_existing_service_order

    def stale_find_existing(db, payload):
        if payload.get("os_code") == "IXC-9002":
            return None
        return original_find(db, payload)

    monkeypatch.setattr(operations_sync, "find_existing_service_order", stale_find_existing)

    result = _reconcile(db_session, monkeypatch, batch_size=1)

    assert result["created_count"] == 1
    assert result["error_count"] == 1
    assert isinstance(result["errors"][0]["reason"], str)
    assert "IXC-9002" in result["errors"][0]["os_codes"]
    assert db_session.scalars(select(ServiceOrder).where(ServiceOrder.os_code == "IXC-9001")).one()
    assert db_session.scalar(select(func.count(ServiceOrder.id)).where(ServiceOrder.os_code == "IXC-9002")) == 1
    assert db_session.scalar(select(func.count(ImportRun.id))) == 1
    assert len(result["batches"]) == 2
    assert result["batches"][0]["created_count"] == 1
    assert result["batches"][1]["error_count"] == 1


def test_reconciliation_revalidates_os_code_inside_transaction(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    order = _make_operation_order()
    db_session.add(order)
    db_session.flush()

    inserted = {"done": False}

    def insert_existing_after_candidate_selection():
        if inserted["done"]:
            return
        _add_existing_service_order(db_session, collaborator, order)
        inserted["done"] = True

    result = _reconcile(db_session, monkeypatch, on_xact_acquire=insert_existing_after_candidate_selection)

    assert result["existing_by_os_code"] == 1
    assert result["created_count"] == 0
    assert db_session.scalar(select(func.count(ServiceOrder.id))) == 1


def test_reconciliation_revalidates_fallback_inside_transaction(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    order = _make_operation_order()
    db_session.add(order)
    db_session.flush()

    inserted = {"done": False}

    def insert_fallback_existing_after_candidate_selection():
        if inserted["done"]:
            return
        _add_existing_service_order(db_session, collaborator, order, os_code="LEGACY-9001")
        inserted["done"] = True

    result = _reconcile(db_session, monkeypatch, on_xact_acquire=insert_fallback_existing_after_candidate_selection)

    assert result["existing_by_fallback"] == 1
    assert result["created_count"] == 0
    assert db_session.scalar(select(func.count(ServiceOrder.id))) == 1


def test_reconciliation_dry_run_does_not_acquire_transaction_lock(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    db_session.add(_make_operation_order())
    db_session.flush()

    def fail_if_locked(_db):
        raise AssertionError("dry-run nao deve adquirir lock transacional")

    monkeypatch.setattr(operations_sync, "_acquire_ixc_import_transaction_lock", fail_if_locked)

    result = _reconcile(db_session, monkeypatch, dry_run=True)

    assert result["ready_to_create"] == 1
    assert db_session.scalar(select(func.count(ServiceOrder.id))) == 0


def test_reconciliation_real_run_does_not_touch_point_balance(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    db_session.add(_make_operation_order())
    db_session.flush()

    def fail_if_detecting_warranty_debits(*args, **kwargs):
        raise AssertionError("reconciliador nao deve alterar garantia/pontuacao")

    monkeypatch.setattr(operations_sync, "detect_post_payment_warranty_debits", fail_if_detecting_warranty_debits)

    result = _reconcile(db_session, monkeypatch)

    assert result["created_count"] == 1
    assert db_session.scalar(select(func.count(PointBalanceEntry.id))) == 0
    assert db_session.scalar(select(func.count(CollaboratorPointBalance.id))) == 0


def test_reconciliation_import_run_rolls_back_with_failed_batch(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    order = _make_operation_order()
    db_session.add(order)
    db_session.flush()
    _add_existing_service_order(db_session, collaborator, order)

    monkeypatch.setattr(operations_sync, "find_existing_service_order", lambda db, payload: None)

    result = _reconcile(db_session, monkeypatch)

    assert result["error_count"] == 1
    assert db_session.scalar(select(func.count(ImportRun.id))) == 0
    assert db_session.scalar(select(func.count(ImportServiceOrderAudit.id))) == 0


def test_reconciliation_rejects_naive_datetime(db_session):
    aware = datetime(2026, 7, 1, tzinfo=timezone.utc)
    naive = datetime(2026, 6, 1)

    with pytest.raises(ValueError, match="date_from deve ser timezone-aware"):
        reconcile_missing_service_orders_from_operations(db_session, date_from=naive, date_to=aware)

    with pytest.raises(ValueError, match="date_to deve ser timezone-aware"):
        reconcile_missing_service_orders_from_operations(db_session, date_from=aware, date_to=naive)


def test_reconciliation_resolves_collaborator_by_responsible_ixc_id(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Nome Cadastrado Diferente", regional="UNI SUL")
    collaborator.ixc_employee_id = 32
    db_session.add(
        _make_operation_order(
            source_order_id="1332589",
            order_code="IXC-1332589",
            responsible="CAUA SOUZA ARAUJO",
            responsible_ixc_id=32,
        )
    )
    db_session.flush()

    result = _reconcile(db_session, monkeypatch, responsible_ixc_id=32)

    service_order = db_session.scalars(select(ServiceOrder).where(ServiceOrder.os_code == "IXC-1332589")).one()
    assert result["created_count"] == 1
    assert service_order.collaborator_id == collaborator.id


def test_reconciliation_filters_by_os_codes(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    db_session.add_all(
        [
            _make_operation_order(source_order_id="9001", order_code="IXC-9001"),
            _make_operation_order(source_order_id="9002", order_code="IXC-9002"),
        ]
    )
    db_session.flush()

    result = _reconcile(db_session, monkeypatch, os_codes=["IXC-9002"])

    assert result["analyzed_count"] == 1
    assert result["created_os_codes"] == ["IXC-9002"]
    assert db_session.scalars(select(ServiceOrder).where(ServiceOrder.os_code == "IXC-9001")).first() is None


def test_reconciliation_filters_by_operation_order_ids(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    order_one = _make_operation_order(source_order_id="9001", order_code="IXC-9001")
    order_two = _make_operation_order(source_order_id="9002", order_code="IXC-9002")
    db_session.add_all([order_one, order_two])
    db_session.flush()

    result = _reconcile(db_session, monkeypatch, operation_order_ids=[order_two.id])

    assert result["analyzed_count"] == 1
    assert result["created_os_codes"] == ["IXC-9002"]
    assert db_session.scalars(select(ServiceOrder).where(ServiceOrder.os_code == "IXC-9001")).first() is None


def test_recent_reconciliation_uses_bounded_window(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    inside = _make_operation_order(
        source_order_id="9007",
        order_code="IXC-9007",
        opened_at=datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc),
    )
    outside = _make_operation_order(
        source_order_id="9008",
        order_code="IXC-9008",
        opened_at=datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc),
        closed_at=datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc),
    )
    db_session.add_all([inside, outside])
    db_session.flush()

    result = reconcile_recent_missing_service_orders_from_operations(
        db_session,
        days=7,
        dry_run=True,
        now=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )

    assert result["analyzed_count"] == 1
    assert result["ready_os_codes"] == ["IXC-9007"]


def test_backfill_collaborator_ixc_ids_matches_by_normalized_name(db_session, make_collaborator):
    """Colaboradores cadastrados antes do vinculo por id devem ser casados retroativamente por nome
    normalizado contra o que ja foi importado em operations_orders, sem nova chamada ao IXC."""
    collaborator = make_collaborator(name="joao da silva", regional="UNI SUL")
    order = _make_operation_order(
        source_order_id="9003",
        order_code="IXC-9003",
        responsible="João Da Silva",
        responsible_ixc_id=777,
    )
    db_session.add(order)
    db_session.flush()

    result = backfill_collaborator_ixc_ids(db_session)

    db_session.refresh(collaborator)
    assert collaborator.ixc_employee_id == 777
    assert result["changed"] == 1


def test_run_operations_to_service_orders_sync_raises_when_advisory_lock_is_already_held(db_session, make_collaborator, monkeypatch):
    """Regression: run_operations_to_service_orders_sync (caminho periodico, chamado pelo
    scheduler) nao adquiria o mesmo lock consultivo do Postgres (_ixc_import_lock) que o
    backfill manual (import_ixc_service_orders) ja usa - o comentario dizia que os dois nunca
    rodam ao mesmo tempo, mas nada no codigo garantia isso. Com o lock ja preso por outro
    processo (simulado aqui), a sincronizacao periodica deve falhar com
    IxcImportLockTimeoutError em vez de rodar por cima - sem isso, os dois caminhos concorrentes
    podiam criar Collaborator duplicado ou colidir na chave unica de os_code."""
    make_collaborator(name="Tecnico Um", regional="UNI SUL").ixc_employee_id = 555
    order = _make_operation_order()
    db_session.add(order)
    db_session.flush()

    _patch_advisory_lock(monkeypatch, db_session, acquired=False)

    with pytest.raises(IxcImportLockTimeoutError):
        run_operations_to_service_orders_sync(db_session)

    assert db_session.scalars(select(ServiceOrder).where(ServiceOrder.os_code == "IXC-9001")).first() is None, (
        "nada deveria ter sido sincronizado com o lock preso"
    )


def test_run_operations_to_service_orders_sync_proceeds_when_advisory_lock_is_free(db_session, make_collaborator, monkeypatch):
    """Contraprova do teste acima: com o lock livre (simulado), a sincronizacao periodica passa
    pelo _ixc_import_lock normalmente e sincroniza como sempre fez."""
    collaborator = make_collaborator(name="Tecnico Um", regional="UNI SUL")
    collaborator.ixc_employee_id = 555
    order = _make_operation_order()
    db_session.add(order)
    db_session.flush()

    _patch_advisory_lock(monkeypatch, db_session, acquired=True)

    result = run_operations_to_service_orders_sync(db_session)

    assert result["summary"]["created_count"] == 1
    assert db_session.scalars(select(ServiceOrder).where(ServiceOrder.os_code == "IXC-9001")).one()
