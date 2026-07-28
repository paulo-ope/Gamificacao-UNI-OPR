from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, extract, func, select
from sqlalchemy.orm import Session

from app.core.performance import performance_step
from app.core.config import get_settings
from app.core.security import require_permission
from app.db.session import get_db
from app.models import CalculationRun, LeadershipBonusResult, PointBalanceEntry, ServiceOrder, User
from app.schemas import (
    ServiceOrderDeletePeriodRequest,
    ServiceOrderDeletePeriodResult,
    ServiceOrderOut,
    ServiceOrderPeriodSummary,
    ServiceOrderSubjectSummary,
)
from app.seed import seed_database
from app.services.regional import normalize_regional_grouped as normalize_regional, same_regional_grouped as same_regional
from app.services.scoring_matrix import DEMO_SERVICE_ORDER_CODES, is_demo_service_order, real_service_orders
from app.services.audit_log import record_audit_log
from app.services.scoring_detail import period_orders

router = APIRouter(prefix="/service-orders", tags=["service-orders"])


def _order_reference_date(order: ServiceOrder):
    return order.closed_at or order.opened_at


def _closed_reference_date(order: ServiceOrder):
    return order.closed_at


def _period_confirmation(reference_month: int, reference_year: int) -> str:
    return f"APAGAR {reference_month:02d}/{reference_year}"


@router.get("", response_model=list[ServiceOrderOut])
def list_service_orders(limit: int = 200, db: Session = Depends(get_db), user: User = Depends(require_permission("orders:read"))):
    stmt = (
        select(ServiceOrder)
        .where(ServiceOrder.os_code.notin_(DEMO_SERVICE_ORDER_CODES))
        .order_by(desc(ServiceOrder.closed_at))
        .limit(limit)
    )
    return list(db.scalars(stmt))


@router.get("/period-summary", response_model=list[ServiceOrderPeriodSummary])
def service_order_period_summary(db: Session = Depends(get_db), user: User = Depends(require_permission("orders:read"))):
    with performance_step("service-orders.period-summary", "aggregate_periods"):
        year_expr = extract("year", ServiceOrder.closed_at)
        month_expr = extract("month", ServiceOrder.closed_at)
        rows = db.execute(
            select(
                year_expr.label("reference_year"),
                month_expr.label("reference_month"),
                func.count(ServiceOrder.id).label("total_service_orders"),
                func.min(ServiceOrder.closed_at).label("first_order_at"),
                func.max(ServiceOrder.closed_at).label("last_order_at"),
            )
            .where(ServiceOrder.closed_at.is_not(None))
            .where(ServiceOrder.os_code.notin_(DEMO_SERVICE_ORDER_CODES))
            .group_by(year_expr, month_expr)
            .order_by(year_expr.desc(), month_expr.desc())
        )
        return [
            ServiceOrderPeriodSummary(
                reference_month=int(row.reference_month),
                reference_year=int(row.reference_year),
                total_service_orders=int(row.total_service_orders),
                first_order_at=row.first_order_at,
                last_order_at=row.last_order_at,
            )
            for row in rows
        ]


@router.get("/subject-summary", response_model=list[ServiceOrderSubjectSummary])
def service_order_subject_summary(
    reference_month: int,
    reference_year: int,
    regional: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("orders:read")),
):
    with performance_step("service-orders.subject-summary", "load_period_orders"):
        orders = real_service_orders(period_orders(db, reference_month, reference_year, regional))
    grouped: dict[tuple[str, str], int] = {}
    with performance_step("service-orders.subject-summary", "group_subjects"):
        for order in orders:
            key = (
                str(order.os_type or "Não informado").strip() or "Não informado",
                str(order.os_subject or "Não informado").strip() or "Não informado",
            )
            grouped[key] = grouped.get(key, 0) + 1

    return [
        ServiceOrderSubjectSummary(
            os_type=os_type,
            os_subject=os_subject,
            service_orders_count=count,
        )
        for os_type, os_subject, count in sorted(
            ((os_type, os_subject, count) for (os_type, os_subject), count in grouped.items()),
            key=lambda item: (-item[2], item[0], item[1]),
        )
    ]


@router.post("/delete-period", response_model=ServiceOrderDeletePeriodResult)
def delete_service_orders_by_period(
    payload: ServiceOrderDeletePeriodRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("orders:import")),
):
    if payload.reference_month < 1 or payload.reference_month > 12:
        raise HTTPException(status_code=422, detail="Mês de referência inválido.")

    expected_confirmation = _period_confirmation(payload.reference_month, payload.reference_year)
    if payload.confirmation.strip().upper() != expected_confirmation:
        raise HTTPException(
            status_code=400,
            detail=f"Confirmação inválida. Digite exatamente: {expected_confirmation}",
        )

    regional = normalize_regional(payload.regional) if payload.regional else None
    orders = real_service_orders(list(db.scalars(select(ServiceOrder))))
    orders_to_delete = []
    for order in orders:
        reference_date = _order_reference_date(order)
        if reference_date is None:
            continue
        if reference_date.month != payload.reference_month or reference_date.year != payload.reference_year:
            continue
        if regional and not same_regional(order.regional, regional):
            continue
        orders_to_delete.append(order)

    calculation_stmt = select(CalculationRun).where(
        CalculationRun.reference_month == payload.reference_month,
        CalculationRun.reference_year == payload.reference_year,
    )
    if regional:
        calculation_stmt = calculation_stmt.where(CalculationRun.regional == regional)
    calculation_runs = list(db.scalars(calculation_stmt))
    calculation_run_ids = [run.id for run in calculation_runs]
    order_ids_to_delete = [order.id for order in orders_to_delete]

    # Um fechamento (CalculationRun) e o registro real de um pagamento: apagar um que ja foi usado
    # como origem/aplicacao de um debito de garantia destruiria historico financeiro de verdade, e
    # isso continua bloqueado abaixo. Ja uma O.S bruta importada e apenas dado de origem re-importavel
    # - o lancamento no ledger guarda o os_code (ver original_os_code/related_os_code), entao o debito
    # sobrevive a O.S ser apagada e reimportada; so precisamos desfazer o vinculo com a linha antiga.
    if calculation_run_ids:
        blocking_entries = list(
            db.scalars(
                select(PointBalanceEntry).where(
                    PointBalanceEntry.origin_calculation_run_id.in_(calculation_run_ids)
                    | PointBalanceEntry.applied_calculation_run_id.in_(calculation_run_ids)
                )
            )
        )
        if blocking_entries:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Este período tem {len(blocking_entries)} lançamento(s) no ledger de saldo de garantia "
                    "vinculado(s) ao próprio fechamento (débito detectado ou aplicado neste fechamento pago). "
                    "Apagar o período destruiria esse histórico financeiro. Resolva ou estorne esses lançamentos "
                    "antes de apagar."
                ),
            )

    if order_ids_to_delete:
        linked_entries = list(
            db.scalars(
                select(PointBalanceEntry).where(
                    PointBalanceEntry.original_service_order_id.in_(order_ids_to_delete)
                    | PointBalanceEntry.related_service_order_id.in_(order_ids_to_delete)
                )
            )
        )
        undocumented_entries = [
            entry
            for entry in linked_entries
            if not (
                (entry.original_service_order_id not in order_ids_to_delete or entry.original_os_code)
                and (entry.related_service_order_id not in order_ids_to_delete or entry.related_os_code)
            )
        ]
        if undocumented_entries:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Este período tem {len(undocumented_entries)} lançamento(s) antigo(s) no ledger de saldo de "
                    "garantia sem o código da O.S salvo, então apagar as O.S perderia a referência. Resolva ou "
                    "estorne esses lançamentos antes de apagar."
                ),
            )
        for entry in linked_entries:
            if entry.original_service_order_id in order_ids_to_delete:
                entry.original_service_order_id = None
            if entry.related_service_order_id in order_ids_to_delete:
                entry.related_service_order_id = None

    if calculation_run_ids:
        db.execute(
            LeadershipBonusResult.__table__.delete().where(
                LeadershipBonusResult.calculation_run_id.in_(calculation_run_ids)
            )
        )

    for run in calculation_runs:
        db.delete(run)
    for order in orders_to_delete:
        db.delete(order)
    record_audit_log(
        db,
        user,
        "delete_period",
        "service_orders",
        f"{payload.reference_month:02d}/{payload.reference_year}",
        None,
        {"regional": regional, "deleted_service_orders": len(orders_to_delete), "deleted_calculation_runs": len(calculation_runs)},
    )

    db.commit()
    return ServiceOrderDeletePeriodResult(
        reference_month=payload.reference_month,
        reference_year=payload.reference_year,
        regional=regional,
        deleted_service_orders=len(orders_to_delete),
        deleted_calculation_runs=len(calculation_runs),
    )


@router.post("/seed")
def seed_service_orders(db: Session = Depends(get_db), user: User = Depends(require_permission("settings:write"))) -> dict[str, str]:
    if get_settings().app_env.lower() != "development":
        raise HTTPException(status_code=403, detail="Seed manual disponível apenas em ambiente de desenvolvimento.")
    seed_database(db, include_demo=False)
    db.commit()
    return {"status": "logic_seeded_without_demo_orders"}
