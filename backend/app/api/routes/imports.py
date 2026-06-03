from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.schemas import ImportPreview, ImportResult
from app.services.upvalue_importer import build_preview, import_upvalue_service_orders

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/upvalue-service-orders/preview", response_model=ImportPreview)
async def preview_upvalue_service_orders(file: UploadFile = File(...), user=Depends(require_permission("orders:import"))):
    contents = await file.read()
    try:
        return build_preview(file.filename or "upvalue.xlsx", contents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/upvalue-service-orders", response_model=ImportResult)
async def import_upvalue_orders(file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(require_permission("orders:import"))):
    contents = await file.read()
    try:
        return import_upvalue_service_orders(db, file.filename or "upvalue.xlsx", contents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
