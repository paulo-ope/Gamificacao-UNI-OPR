import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import SessionLocal, get_db
from app.models import ImportRun, ImportServiceOrderAudit, User
from app.schemas import ImportPreview, ImportResult, ImportRunOut, ImportServiceOrderAuditOut
from app.services.calculation import get_setting
from app.services.ixc_client import get_ixc_client
from app.services.ixc_importer import backfill_ixc_service_orders, ixc_import_lock_busy
from app.services.ixc_scheduler import (
    IXC_SYNC_CONSECUTIVE_FAILURES_KEY,
    IXC_SYNC_LAST_ERROR_AT_KEY,
    IXC_SYNC_LAST_ERROR_KEY,
    IXC_SYNC_LAST_SUCCESS_AT_KEY,
)
from app.services.upvalue_importer import build_preview, import_upvalue_service_orders, register_failed_import_run

logger = logging.getLogger("imports")
router = APIRouter(prefix="/imports", tags=["imports"])


class IxcBackfillRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


def _run_ixc_backfill_job(year: int, month: int, imported_by: int | None) -> None:
    """Processa o backfill retroativo do IXC em background - ver POST /ixc-backfill. Acha real da
    auditoria de performance 2026-08-27: buscar um mês inteiro da API do IXC (paginado) rodava
    inline na requisição HTTP, sem nenhum modelo de job/status, arriscando timeout na mesma
    classe de problema já corrigida em support/opa-imports."""
    with SessionLocal() as db:
        try:
            client = get_ixc_client()
            backfill_ixc_service_orders(db, client, year=year, month=month, imported_by=imported_by)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Falha no backfill retroativo do IXC %04d-%02d (background)", year, month)


@router.post("/ixc-backfill", status_code=202)
def backfill_ixc_orders(
    payload: IxcBackfillRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("orders:import")),
):
    """Importação retroativa sob demanda de um mês específico direto da API do IXC (fora do polling
    periódico) - uma vez importado, esse mês fica salvo e não é mais buscado de novo automaticamente.
    Roda em BACKGROUND (devolve 202 na hora) - acompanhe o resultado em GET /imports/runs
    (source="ixc", mais recente) em vez de esperar a resposta desta requisição."""
    if ixc_import_lock_busy(db):
        raise HTTPException(
            status_code=409,
            detail="Outra importação do IXC (sincronização automática ou retroativa) já está em andamento. Tente novamente em instantes.",
        )
    background_tasks.add_task(_run_ixc_backfill_job, payload.year, payload.month, user.id)
    return {
        "status": "queued",
        "message": "Importação retroativa do IXC iniciada em segundo plano - acompanhe em GET /imports/runs.",
        "year": payload.year,
        "month": payload.month,
    }


@router.get("/ixc-sync-status")
def ixc_sync_status(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("orders:read")),
):
    """Saúde da sincronização automática com o IXC - não existe alerta ativo (e-mail/webhook) neste
    projeto, então essa rota é o jeito de alguém checar se a sincronização periódica está funcionando."""
    failures_raw = get_setting(db, IXC_SYNC_CONSECUTIVE_FAILURES_KEY, "0")
    try:
        consecutive_failures = int(failures_raw or "0")
    except ValueError:
        consecutive_failures = 0
    return {
        "last_success_at": get_setting(db, IXC_SYNC_LAST_SUCCESS_AT_KEY, "") or None,
        "last_error_at": get_setting(db, IXC_SYNC_LAST_ERROR_AT_KEY, "") or None,
        "last_error": get_setting(db, IXC_SYNC_LAST_ERROR_KEY, "") or None,
        "consecutive_failures": consecutive_failures,
        "is_healthy": consecutive_failures == 0,
    }


@router.post("/upvalue-service-orders/preview", response_model=ImportPreview)
async def preview_upvalue_service_orders(file: UploadFile = File(...), user=Depends(require_permission("orders:import"))):
    contents = await file.read()
    try:
        return build_preview(file.filename or "upvalue.xlsx", contents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Não foi possível ler a planilha informada.") from exc


@router.post("/upvalue-service-orders", response_model=ImportResult)
async def import_upvalue_orders(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(require_permission("orders:import"))):
    contents = await file.read()
    try:
        result = import_upvalue_service_orders(db, file.filename or "upvalue.xlsx", contents, imported_by=user.id)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        register_failed_import_run(
            db,
            file.filename or "upvalue.xlsx",
            contents,
            "Não foi possível importar a planilha informada.",
            imported_by=user.id,
        )
        db.commit()
        raise HTTPException(status_code=400, detail="Não foi possível importar a planilha informada.") from exc
    except Exception as exc:
        db.rollback()
        register_failed_import_run(
            db,
            file.filename or "upvalue.xlsx",
            contents,
            "Falha inesperada ao importar a planilha.",
            imported_by=user.id,
        )
        db.commit()
        raise HTTPException(status_code=500, detail="Falha inesperada ao importar a planilha.") from exc


@router.get("/runs", response_model=list[ImportRunOut])
def list_import_runs(
    status: str | None = None,
    file_name: str | None = None,
    imported_by: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("orders:read")),
):
    stmt = select(ImportRun).order_by(desc(ImportRun.created_at), desc(ImportRun.id))
    if status:
        stmt = stmt.where(ImportRun.status == status.strip().lower())
    if file_name:
        stmt = stmt.where(ImportRun.filename.ilike(f"%{file_name.strip()}%"))
    if imported_by is not None:
        stmt = stmt.where(ImportRun.imported_by == imported_by)
    if date_from is not None:
        stmt = stmt.where(ImportRun.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(ImportRun.created_at <= date_to)
    return list(db.scalars(stmt.limit(limit)))


@router.get("/runs/{import_run_id}", response_model=ImportRunOut)
def get_import_run(
    import_run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("orders:read")),
):
    import_run = db.get(ImportRun, import_run_id)
    if not import_run:
        raise HTTPException(status_code=404, detail="Importação não encontrada.")
    return import_run


@router.get("/runs/{import_run_id}/audits", response_model=list[ImportServiceOrderAuditOut])
def list_import_run_audits(
    import_run_id: int,
    action: str | None = None,
    os_code: str | None = None,
    reason: str | None = None,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("orders:read")),
):
    if not db.get(ImportRun, import_run_id):
        raise HTTPException(status_code=404, detail="Importação não encontrada.")
    stmt = (
        select(ImportServiceOrderAudit)
        .where(ImportServiceOrderAudit.import_run_id == import_run_id)
        .order_by(desc(ImportServiceOrderAudit.created_at), desc(ImportServiceOrderAudit.id))
    )
    if action:
        stmt = stmt.where(ImportServiceOrderAudit.action == action.strip().lower())
    if os_code:
        stmt = stmt.where(ImportServiceOrderAudit.os_code == os_code.strip())
    if reason:
        stmt = stmt.where(ImportServiceOrderAudit.reason.ilike(f"%{reason.strip()}%"))
    return list(db.scalars(stmt.offset(offset).limit(limit)))


@router.get("/runs/{import_run_id}/errors", response_model=list[ImportServiceOrderAuditOut])
def list_import_run_errors(
    import_run_id: int,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("orders:read")),
):
    if not db.get(ImportRun, import_run_id):
        raise HTTPException(status_code=404, detail="Importação não encontrada.")
    stmt = (
        select(ImportServiceOrderAudit)
        .where(ImportServiceOrderAudit.import_run_id == import_run_id)
        .where(ImportServiceOrderAudit.action.in_(("error", "rejected", "blocked_paid_period")))
        .order_by(desc(ImportServiceOrderAudit.created_at), desc(ImportServiceOrderAudit.id))
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(stmt))
