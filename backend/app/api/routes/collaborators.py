from datetime import datetime, timezone
from collections import Counter

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.core.security import require_permission
from app.models import CalculationRun, Collaborator, CollaboratorPointBalance, CollaboratorScore, PointBalanceEntry, ServiceOrder, User
from app.schemas import (
    CollaboratorCreate,
    CollaboratorDeleteResult,
    CollaboratorMonthlyHistoryItem,
    CollaboratorOut,
    CollaboratorPointBalanceOut,
    CollaboratorRegistryOut,
    CollaboratorServiceOrdersDetailOut,
    CollaboratorUpdate,
)
from app.services.calculation import latest_run
from app.services.point_balance import current_balance, serialize_entry as serialize_point_balance_entry
from app.services.regional import is_valid_regional, normalize_regional_grouped as normalize_regional
from app.services.scoring_detail import get_collaborator_service_orders_detail, get_point_value
from app.services.statement_pdf import build_collaborator_statement_pdf
from app.services.audit_log import record_audit_log, snapshot

router = APIRouter(prefix="/collaborators", tags=["collaborators"])


@router.get("/registry", response_model=CollaboratorRegistryOut)
def collaborators_registry(db: Session = Depends(get_db), user: User = Depends(require_permission("audit:read"))):
    collaborators = list(db.scalars(select(Collaborator).order_by(Collaborator.name.asc(), Collaborator.id.asc())))
    orders = list(db.scalars(select(ServiceOrder)))
    orders_by_collaborator: dict[int, list[ServiceOrder]] = {}
    for order in orders:
        orders_by_collaborator.setdefault(order.collaborator_id, []).append(order)
    portal_users_by_collaborator: dict[int, User] = {
        item.collaborator_id: item
        for item in db.scalars(select(User).where(User.collaborator_id.is_not(None)))
    }

    def build_item(collaborator: Collaborator):
        linked_orders = orders_by_collaborator.get(collaborator.id, [])
        portal_user = portal_users_by_collaborator.get(collaborator.id)
        regionals = [normalize_regional(order.regional) for order in linked_orders if is_valid_regional(order.regional)]
        roles = [collaborator.role] if collaborator.role and collaborator.role != "Importado UpValue" else []
        suggested_regional = Counter(regionals).most_common(1)[0][0] if regionals else normalize_regional(collaborator.regional)
        suggested_role = roles[0] if roles else ("Importado UpValue" if linked_orders else collaborator.role)
        return {
            "id": collaborator.id,
            "name": collaborator.name,
            "role": collaborator.role,
            "regional": normalize_regional(collaborator.regional),
            "active": collaborator.active,
            "is_registered": collaborator.is_registered,
            "phone": collaborator.phone,
            "email": collaborator.email,
            "service_orders_count": len(linked_orders),
            "suggested_regional": suggested_regional,
            "suggested_role": suggested_role,
            "has_linked_orders": bool(linked_orders),
            "has_photo": collaborator.photo is not None,
            "portal_user_id": portal_user.id if portal_user else None,
            "portal_user_email": portal_user.email if portal_user else None,
        }

    items = [build_item(collaborator) for collaborator in collaborators if is_valid_regional(collaborator.regional) or orders_by_collaborator.get(collaborator.id)]
    registered = [item for item in items if item["is_registered"]]
    unregistered = [item for item in items if not item["is_registered"]]
    return {"registered": registered, "unregistered": unregistered}


@router.post("", response_model=CollaboratorOut, status_code=201)
def create_collaborator(
    payload: CollaboratorCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:write")),
):
    data = payload.model_dump()
    data["regional"] = normalize_regional(data.get("regional"))
    collaborator = Collaborator(**data)
    db.add(collaborator)
    db.flush()
    record_audit_log(db, user, "create", "collaborators", collaborator.id, None, snapshot(collaborator))
    db.commit()
    db.refresh(collaborator)
    return collaborator


@router.delete("/{collaborator_id}", response_model=CollaboratorDeleteResult)
def delete_collaborator(
    collaborator_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:write")),
):
    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")

    linked_orders = list(db.scalars(select(ServiceOrder).where(ServiceOrder.collaborator_id == collaborator_id)))
    # CollaboratorScore.collaborator_id é NOT NULL - sem checar isso aqui, apagar um colaborador com
    # pontuação já calculada (mesmo sem nenhuma O.S. vinculada no momento) derruba o delete com um
    # IntegrityError (achado real: o ORM tenta nulificar a FK ao invés de bloquear/soft-deletar).
    has_scores = db.scalar(
        select(CollaboratorScore.id).where(CollaboratorScore.collaborator_id == collaborator_id).limit(1)
    )
    if linked_orders or has_scores:
        before = snapshot(collaborator)
        collaborator.active = False
        collaborator.is_registered = False
        if not collaborator.role or collaborator.role.strip() == "":
            collaborator.role = "Importado UpValue"
        record_audit_log(db, user, "soft_delete", "collaborators", collaborator.id, before, snapshot(collaborator))
        db.commit()
        return {
            "id": collaborator.id,
            "deleted": False,
            "soft_deleted": True,
            "moved_to_unregistered": True,
        }

    before = snapshot(collaborator)
    record_audit_log(db, user, "delete", "collaborators", collaborator.id, before, None)
    db.delete(collaborator)
    db.commit()
    return {
        "id": collaborator_id,
        "deleted": True,
        "soft_deleted": False,
        "moved_to_unregistered": False,
    }


@router.get("/{collaborator_id}/service-orders-detail", response_model=CollaboratorServiceOrdersDetailOut)
def collaborator_service_orders_detail(
    collaborator_id: int,
    calculation_run_id: int | None = None,
    reference_month: int | None = Query(default=None, ge=1, le=12),
    reference_year: int | None = Query(default=None, ge=2000),
    regional: str | None = None,
    only_scored: bool = False,
    only_unscored: bool = False,
    only_penalized: bool = False,
    only_sla_out: bool = False,
    only_warranty: bool = False,
    only_recurrence: bool = False,
    only_non_recurrent: bool = False,
    only_diagnosis_blocked: bool = False,
    os_type: str | None = None,
    os_subject: str | None = None,
    status_sla: str | None = None,
    group_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
):
    run: CalculationRun | None = None
    if calculation_run_id:
        run = db.get(CalculationRun, calculation_run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Apuração não encontrada.")
    else:
        run = latest_run(db)

    now = datetime.now(timezone.utc)
    month = reference_month or (run.reference_month if run else now.month)
    year = reference_year or (run.reference_year if run else now.year)
    selected_regional = regional if regional is not None else (run.regional if run else None)
    point_value = run.point_value if run else get_point_value(db)

    try:
        return get_collaborator_service_orders_detail(
            db,
            collaborator_id=collaborator_id,
            reference_month=month,
            reference_year=year,
            regional=selected_regional,
            only_scored=only_scored,
            only_unscored=only_unscored,
            only_penalized=only_penalized,
            only_sla_out=only_sla_out,
            only_warranty=only_warranty,
            only_recurrence=only_recurrence,
            only_non_recurrent=only_non_recurrent,
            only_diagnosis_blocked=only_diagnosis_blocked,
            os_type=os_type,
            os_subject=os_subject,
            status_sla=status_sla,
            group_id=group_id,
            point_value=point_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Detalhamento do colaborador não encontrado para o período informado.") from exc


@router.get("/{collaborator_id}/scoring-detail", response_model=CollaboratorServiceOrdersDetailOut)
def collaborator_scoring_detail(
    collaborator_id: int,
    calculation_run_id: int | None = None,
    reference_month: int | None = Query(default=None, ge=1, le=12),
    reference_year: int | None = Query(default=None, ge=2000),
    regional: str | None = None,
    only_scored: bool = False,
    only_unscored: bool = False,
    only_penalized: bool = False,
    only_sla_out: bool = False,
    only_warranty: bool = False,
    only_recurrence: bool = False,
    only_non_recurrent: bool = False,
    only_diagnosis_blocked: bool = False,
    os_type: str | None = None,
    os_subject: str | None = None,
    status_sla: str | None = None,
    group_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
):
    return collaborator_service_orders_detail(
        collaborator_id=collaborator_id,
        calculation_run_id=calculation_run_id,
        reference_month=reference_month,
        reference_year=reference_year,
        regional=regional,
        only_scored=only_scored,
        only_unscored=only_unscored,
        only_penalized=only_penalized,
        only_sla_out=only_sla_out,
        only_warranty=only_warranty,
        only_recurrence=only_recurrence,
        only_non_recurrent=only_non_recurrent,
        only_diagnosis_blocked=only_diagnosis_blocked,
        os_type=os_type,
        os_subject=os_subject,
        status_sla=status_sla,
        group_id=group_id,
        db=db,
        user=user,
    )


@router.get("/{collaborator_id}/statement.pdf")
def collaborator_statement_pdf(
    collaborator_id: int,
    calculation_run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
):
    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")

    run = db.get(CalculationRun, calculation_run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Apuração não encontrada.")

    score = db.scalar(
        select(CollaboratorScore).where(
            CollaboratorScore.calculation_run_id == run.id,
            CollaboratorScore.collaborator_id == collaborator_id,
        )
    )
    if not score:
        raise HTTPException(status_code=404, detail="Pontuação do colaborador não encontrada nesta apuração.")

    pdf_bytes = build_collaborator_statement_pdf(db, collaborator, run, score)
    safe_name = "".join(ch if ch.isalnum() else "-" for ch in collaborator.name.lower()).strip("-")
    filename = f"extrato-{safe_name}-{run.reference_month:02d}-{run.reference_year}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{collaborator_id}/point-balance", response_model=CollaboratorPointBalanceOut)
def collaborator_point_balance(
    collaborator_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
):
    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")

    entries = list(
        db.scalars(
            select(PointBalanceEntry)
            .where(PointBalanceEntry.collaborator_id == collaborator_id)
            .options(
                selectinload(PointBalanceEntry.original_service_order),
                selectinload(PointBalanceEntry.related_service_order),
                selectinload(PointBalanceEntry.origin_calculation_run),
                selectinload(PointBalanceEntry.applied_calculation_run),
            )
            .order_by(PointBalanceEntry.created_at.desc(), PointBalanceEntry.id.desc())
        )
    )
    balance = db.scalar(
        select(CollaboratorPointBalance).where(CollaboratorPointBalance.collaborator_id == collaborator_id)
    )
    return CollaboratorPointBalanceOut(
        collaborator_id=collaborator_id,
        collaborator_name=collaborator.name,
        balance_points=current_balance(db, collaborator_id),
        updated_at=balance.updated_at if balance else None,
        entries=[serialize_point_balance_entry(entry, collaborator_name=collaborator.name) for entry in entries],
    )


@router.get("/{collaborator_id}/monthly-history", response_model=list[CollaboratorMonthlyHistoryItem])
def collaborator_monthly_history(
    collaborator_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
):
    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")

    rows = list(
        db.scalars(
            select(CollaboratorScore)
            .join(CalculationRun, CalculationRun.id == CollaboratorScore.calculation_run_id)
            .where(CollaboratorScore.collaborator_id == collaborator_id)
            .where(CalculationRun.status != "cancelled")
            .options(selectinload(CollaboratorScore.calculation_run))
            .order_by(desc(CalculationRun.reference_year), desc(CalculationRun.reference_month))
        )
    )

    # Uma linha por (mes, ano, regional): prefere o fechamento pago; senao o mais recente.
    def rank(score: CollaboratorScore) -> tuple:
        run = score.calculation_run
        return (1 if run.status == "paid" else 0, run.created_at)

    best_by_period: dict[tuple, CollaboratorScore] = {}
    for score in rows:
        run = score.calculation_run
        key = (run.reference_year, run.reference_month, run.regional)
        current = best_by_period.get(key)
        if current is None or rank(score) > rank(current):
            best_by_period[key] = score

    ordered = sorted(
        best_by_period.values(),
        key=lambda s: (s.calculation_run.reference_year, s.calculation_run.reference_month),
        reverse=True,
    )
    return [
        CollaboratorMonthlyHistoryItem(
            reference_month=score.calculation_run.reference_month,
            reference_year=score.calculation_run.reference_year,
            regional=score.calculation_run.regional,
            calculation_run_id=score.calculation_run_id,
            status=score.calculation_run.status,
            service_orders_count=int(score.service_orders_count),
            gross_points=float(score.gross_points),
            net_points=float(score.net_points),
            final_points=float(score.final_points),
            estimated_payment=float(score.estimated_payment),
            balance_adjustment_points=float(score.balance_adjustment_points or 0),
            health_multiplier=float(score.health_multiplier or 1),
        )
        for score in ordered
    ]


@router.put("/{collaborator_id}", response_model=CollaboratorOut)
def update_collaborator(
    collaborator_id: int,
    payload: CollaboratorUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:write")),
):
    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")

    before = snapshot(collaborator)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(collaborator, field, normalize_regional(value) if field == "regional" else value)
    record_audit_log(db, user, "update", "collaborators", collaborator.id, before, snapshot(collaborator))
    db.commit()
    db.refresh(collaborator)
    return collaborator


# Foto de perfil guardada como bytes no banco (ver migration 20260717_0008) - sem infraestrutura de
# arquivo neste projeto, e o volume de colaboradores (algumas centenas) cabe perfeitamente bem nisso.
MAX_COLLABORATOR_PHOTO_BYTES = 2 * 1024 * 1024  # 2MB
ALLOWED_COLLABORATOR_PHOTO_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post("/{collaborator_id}/photo", response_model=CollaboratorOut)
async def upload_collaborator_photo(
    collaborator_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:write")),
):
    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")

    if file.content_type not in ALLOWED_COLLABORATOR_PHOTO_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="Formato de imagem não suportado. Use JPEG, PNG ou WEBP.")

    contents = await file.read()
    if len(contents) > MAX_COLLABORATOR_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Imagem maior que 2MB. Envie uma foto menor.")

    # Snapshot manual e leve (não usa `snapshot()`/`before/after` genérico) - esse helper serializa
    # TODAS as colunas do modelo pro log de auditoria, incluindo os bytes crus da foto, o que
    # quebraria (bytes não são JSON-serializável de forma segura) ou incharia o log de auditoria
    # com o conteúdo binário da imagem.
    had_photo_before = collaborator.photo is not None
    collaborator.photo = contents
    collaborator.photo_content_type = file.content_type
    record_audit_log(
        db, user, "update", "collaborators", collaborator.id,
        {"has_photo": had_photo_before}, {"has_photo": True, "photo_content_type": file.content_type},
    )
    db.commit()
    db.refresh(collaborator)
    return collaborator


@router.get("/{collaborator_id}/photo")
def get_collaborator_photo(
    collaborator_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("audit:read")),
):
    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator or not collaborator.photo:
        raise HTTPException(status_code=404, detail="Colaborador sem foto de perfil.")
    return Response(content=collaborator.photo, media_type=collaborator.photo_content_type or "application/octet-stream")


@router.delete("/{collaborator_id}/photo", response_model=CollaboratorOut)
def delete_collaborator_photo(
    collaborator_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scoring:write")),
):
    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")

    had_photo_before = collaborator.photo is not None
    collaborator.photo = None
    collaborator.photo_content_type = None
    record_audit_log(
        db, user, "update", "collaborators", collaborator.id,
        {"has_photo": had_photo_before}, {"has_photo": False},
    )
    db.commit()
    db.refresh(collaborator)
    return collaborator
