from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.models import Collaborator, ServiceOrder
from app.modules.operations.models import OperationOrder
from app.services.operations_sync import (
    _resolve_collaborator,
    backfill_collaborator_ixc_ids,
    sync_service_orders_from_operations,
)
from app.services.scoring_detail import sla_inside


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
