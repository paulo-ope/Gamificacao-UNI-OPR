from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.models import CalculationRun, ServiceOrder, User
from app.schemas import (
    ServiceOrderDeletePeriodRequest,
    ServiceOrderDeletePeriodResult,
    ServiceOrderOut,
    ServiceOrderPeriodSummary,
    ServiceOrderSubjectSummary,
)
from app.seed import seed_database
from app.services.regional import normalize_regional, same_regional
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
    orders = real_service_orders(list(db.scalars(select(ServiceOrder))))
    grouped: dict[tuple[int, int], list[ServiceOrder]] = {}
    for order in orders:
        reference_date = _closed_reference_date(order)
        if reference_date is None:
            continue
        grouped.setdefault((reference_date.year, reference_date.month), []).append(order)

    summaries: list[ServiceOrderPeriodSummary] = []
    for (year, month), period_orders in grouped.items():
        dates = [date for date in (_closed_reference_date(order) for order in period_orders) if date is not None]
        summaries.append(
            ServiceOrderPeriodSummary(
                reference_month=month,
                reference_year=year,
                total_service_orders=len(period_orders),
                first_order_at=min(dates) if dates else None,
                last_order_at=max(dates) if dates else None,
            )
        )

    return sorted(summaries, key=lambda item: (item.reference_year, item.reference_month), reverse=True)


@router.get("/subject-summary", response_model=list[ServiceOrderSubjectSummary])
def service_order_subject_summary(
    reference_month: int,
    reference_year: int,
    regional: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("orders:read")),
):
    orders = real_service_orders(period_orders(db, reference_month, reference_year, regional))
    grouped: dict[tuple[str, str], int] = {}
    for order in orders:
        key = (
            str(order.os_type or "Nao informado").strip() or "Nao informado",
            str(order.os_subject or "Nao informado").strip() or "Nao informado",
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
        raise HTTPException(status_code=422, detail="Mes de referencia invalido.")

    expected_confirmation = _period_confirmation(payload.reference_month, payload.reference_year)
    if payload.confirmation.strip().upper() != expected_confirmation:
        raise HTTPException(
            status_code=400,
            detail=f"Confirmacao invalida. Digite exatamente: {expected_confirmation}",
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
    seed_database(db, include_demo=False)
    return {"status": "logic_seeded_without_demo_orders"}
