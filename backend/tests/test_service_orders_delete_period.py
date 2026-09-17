"""Regressão (auditoria 2026-09-15): `POST /service-orders/delete-period` apagava um fechamento
com `status="paid"` sem checar isso - a rota exige só `orders:import` (perfil `operator`), que nem
tem `calculation:run` (a permissão pra MARCAR um fechamento como pago). Ou seja, o perfil mais fraco
do módulo conseguia apagar um pagamento que ele mesmo não é capaz de criar."""
from datetime import datetime, timezone

from app.models import CalculationRun, Collaborator, ServiceOrder


def _service_order(collaborator: Collaborator, code: str, closed: datetime) -> ServiceOrder:
    return ServiceOrder(
        os_code=code, contract_id="C-1", customer_login="cliente.x", customer_name="Cliente X",
        collaborator_id=collaborator.id, regional=collaborator.regional, os_type="Manutencao",
        os_subject="Reparo", diagnosis="Falha", status="Concluida",
        opened_at=closed, closed_at=closed,
    )


def test_delete_period_refuses_when_the_period_has_a_paid_closure(db_session, client, make_collaborator):
    collaborator = make_collaborator()
    order = _service_order(collaborator, "OS-DELETE-PAID-TEST", datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc))
    paid_run = CalculationRun(reference_month=7, reference_year=2026, regional=None, point_value=2.5, status="paid")
    db_session.add_all([order, paid_run])
    db_session.commit()

    response = client.post(
        "/api/service-orders/delete-period",
        json={"reference_month": 7, "reference_year": 2026, "confirmation": "APAGAR 07/2026"},
    )

    assert response.status_code == 409
    assert "PAGO" in response.json()["detail"]

    # Nada foi apagado: nem a O.S, nem o fechamento.
    db_session.expire_all()
    assert db_session.get(ServiceOrder, order.id) is not None
    assert db_session.get(CalculationRun, paid_run.id) is not None


def test_delete_period_still_works_for_a_draft_period_without_paid_closures(db_session, client, make_collaborator):
    collaborator = make_collaborator()
    order = _service_order(collaborator, "OS-DELETE-DRAFT-TEST", datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc))
    draft_run = CalculationRun(reference_month=8, reference_year=2026, regional=None, point_value=2.5, status="draft")
    db_session.add_all([order, draft_run])
    db_session.commit()
    order_id, run_id = order.id, draft_run.id

    response = client.post(
        "/api/service-orders/delete-period",
        json={"reference_month": 8, "reference_year": 2026, "confirmation": "APAGAR 08/2026"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["deleted_service_orders"] == 1
    assert body["deleted_calculation_runs"] == 1

    db_session.expire_all()
    assert db_session.get(ServiceOrder, order_id) is None
    assert db_session.get(CalculationRun, run_id) is None
