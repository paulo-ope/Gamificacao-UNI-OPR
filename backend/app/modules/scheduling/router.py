"""Rotas do módulo de Agendamento.

Todos os KPIs respondem instantâneo (dado local sincronizado). A única operação lenta - o sync com
o IXC - roda como job assíncrono com polling, reutilizando a tabela `scheduling_jobs` que já
existia para esse fim (job_type="sync").
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import permissions_for_user, require_permission
from app.db.session import SessionLocal, get_db
from app.models import SchedulingJob, User
from app.modules.scheduling import metrics as metrics_engine
from app.modules.scheduling.models import (
    SchedulingEvent,
    SchedulingOperator,
    SchedulingOrder,
    SchedulingSavedFilter,
    SchedulingTechnician,
)
from app.modules.scheduling.schemas import (
    SchedulingBacklogItem,
    SchedulingDashboard,
    SchedulingFilterOptions,
    SchedulingOperatorEventPage,
    SchedulingOrderDetailPage,
    SchedulingOrderTimeline,
    SchedulingSavedFilterCreate,
    SchedulingSavedFilterOut,
    SchedulingSavedFilterUpdate,
    SchedulingSettingsUpdate,
    SchedulingSyncJobOut,
    SchedulingSyncRequest,
    SchedulingSyncStatus,
    SchedulingTeamMember,
    SchedulingTeamUpdate,
)
from app.modules.scheduling.sync import WATERMARK_KEY, backfill_messages, run_sync, _get_watermark
from app.services.ixc_client import IxcApiError, fetch_funcionarios_by_ids, fetch_usuarios_by_ids, get_ixc_client

logger = logging.getLogger("scheduling_router")

router = APIRouter(prefix="/scheduling", tags=["scheduling"])


def _parse_filters(
    date_from: date,
    date_to: date,
    filial_ids: list[str],
    setor_ids: list[str],
    assunto_ids: list[str],
    operator_ids: list[int],
) -> metrics_engine.SchedulingFilters:
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="A data final não pode ser anterior à inicial.")
    if (date_to - date_from).days > 366:
        raise HTTPException(status_code=400, detail="O período máximo de consulta é de 1 ano.")
    return metrics_engine.SchedulingFilters(
        date_from=date_from,
        date_to=date_to,
        filial_ids=filial_ids,
        setor_ids=setor_ids,
        assunto_ids=assunto_ids,
        operator_ids=operator_ids,
    )


@router.get("/dashboard", response_model=SchedulingDashboard)
def get_dashboard(
    date_from: date,
    date_to: date,
    filial_ids: list[str] = Query(default_factory=list),
    setor_ids: list[str] = Query(default_factory=list),
    assunto_ids: list[str] = Query(default_factory=list),
    operator_ids: list[int] = Query(default_factory=list),
    count_mode: str = "all_events",
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:read")),
):
    if count_mode not in ("all_events", "distinct_orders"):
        raise HTTPException(status_code=400, detail=f"count_mode inválido: {count_mode!r}")
    filters = _parse_filters(date_from, date_to, filial_ids, setor_ids, assunto_ids, operator_ids)
    return metrics_engine.build_dashboard(db, filters, count_mode=count_mode)


@router.get("/backlog", response_model=list[SchedulingBacklogItem])
def get_backlog(
    date_from: date,
    date_to: date,
    filial_ids: list[str] = Query(default_factory=list),
    setor_ids: list[str] = Query(default_factory=list),
    assunto_ids: list[str] = Query(default_factory=list),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:read")),
):
    filters = _parse_filters(date_from, date_to, filial_ids, setor_ids, assunto_ids, [])
    return metrics_engine.backlog_items(db, filters, limit=limit)


@router.get("/orders", response_model=SchedulingOrderDetailPage)
def get_order_details(
    date_from: date,
    date_to: date,
    filial_ids: list[str] = Query(default_factory=list),
    setor_ids: list[str] = Query(default_factory=list),
    assunto_ids: list[str] = Query(default_factory=list),
    operator_ids: list[int] = Query(default_factory=list),
    status: str | None = Query(default=None, description='"pending" ou "scheduled"'),
    sla_status: str | None = Query(default=None, description='"late" ou "on_time" (só entre agendadas)'),
    ttfa_bucket: str | None = None,
    backlog_bucket: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, le=200),
    sort_by: str = Query(default="opened_at"),
    sort_dir: str = Query(default="desc"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:read")),
):
    """Drill-through: lista as O.S. específicas por trás de qualquer card/gráfico/linha do
    dashboard, com o colaborador completo (operador que agendou + técnico de campo designado)."""
    if status not in (None, "pending", "scheduled"):
        raise HTTPException(status_code=400, detail=f"status inválido: {status!r}")
    if sla_status not in (None, "late", "on_time"):
        raise HTTPException(status_code=400, detail=f"sla_status inválido: {sla_status!r}")
    if sort_by not in metrics_engine.ORDER_SORT_KEYS:
        raise HTTPException(status_code=400, detail=f"sort_by inválido: {sort_by!r}")
    if sort_dir not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail=f"sort_dir inválido: {sort_dir!r}")
    filters = _parse_filters(date_from, date_to, filial_ids, setor_ids, assunto_ids, operator_ids)
    return metrics_engine.order_details(
        db, filters,
        status=status, sla_status=sla_status, ttfa_bucket=ttfa_bucket, backlog_bucket=backlog_bucket,
        page=page, page_size=page_size, sort_by=sort_by, sort_dir=sort_dir,
    )


@router.get("/operators/{ixc_operator_id}/events", response_model=SchedulingOperatorEventPage)
def get_operator_events(
    ixc_operator_id: int,
    date_from: date,
    date_to: date,
    filial_ids: list[str] = Query(default_factory=list),
    setor_ids: list[str] = Query(default_factory=list),
    assunto_ids: list[str] = Query(default_factory=list),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:read")),
):
    """Drill-through do modo "cada ação conta": todo agendamento/reagendamento feito por esse
    operador no período, uma linha por evento - diferente de GET /orders (que só enxerga a O.S. que
    ele agendou primeiro)."""
    filters = _parse_filters(date_from, date_to, filial_ids, setor_ids, assunto_ids, [])
    return metrics_engine.operator_events(db, filters, operator_id=ixc_operator_id, page=page, page_size=page_size)


@router.get("/orders/{ixc_os_id}/timeline", response_model=SchedulingOrderTimeline)
def get_order_timeline(
    ixc_os_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:read")),
):
    """Log completo de uma O.S. específica: todo evento sincronizado (Abertura, Agendamento,
    Reagendar, Fechamento), em ordem, com quem fez cada um."""
    timeline = metrics_engine.order_timeline(db, ixc_os_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail="O.S. não encontrada (fora do escopo sincronizado do módulo).")
    return timeline


def _saved_filter_permissions(user: User) -> set[str]:
    return permissions_for_user(user)


def _ensure_global_saved_filter_permission(user: User) -> None:
    if "scheduling:views:manage_global" not in _saved_filter_permissions(user):
        raise HTTPException(status_code=403, detail="Seu perfil não permite gerenciar visões globais.")


def _saved_filter_or_404_scoped(db: Session, saved_filter_id: int, user: User) -> SchedulingSavedFilter:
    item = db.scalar(select(SchedulingSavedFilter).where(SchedulingSavedFilter.id == saved_filter_id))
    if item is None or (item.visibility == "personal" and item.user_id != user.id):
        raise HTTPException(status_code=404, detail="Filtro salvo não encontrado.")
    return item


def _can_manage_saved_filter(user: User, item: SchedulingSavedFilter) -> bool:
    if item.visibility == "personal":
        return item.user_id == user.id and "scheduling:manage_filters" in _saved_filter_permissions(user)
    return "scheduling:views:manage_global" in _saved_filter_permissions(user)


def _ensure_unique_filter_name_scoped(
    db: Session, user_id: int, name: str, visibility: str, exclude_id: int | None = None,
) -> None:
    stmt = select(SchedulingSavedFilter.id).where(func.lower(SchedulingSavedFilter.name) == name.casefold())
    if visibility == "personal":
        stmt = stmt.where(SchedulingSavedFilter.user_id == user_id, SchedulingSavedFilter.visibility == "personal")
    else:
        stmt = stmt.where(SchedulingSavedFilter.visibility == "global")
    if exclude_id is not None:
        stmt = stmt.where(SchedulingSavedFilter.id != exclude_id)
    if db.scalar(stmt) is not None:
        detail = "Já existe uma visão global com esse nome." if visibility == "global" else "Você já possui uma visão pessoal com esse nome."
        raise HTTPException(status_code=409, detail=detail)


@router.get("/saved-filters", response_model=list[SchedulingSavedFilterOut])
def list_saved_filters(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:read")),
):
    condition = SchedulingSavedFilter.user_id == user.id
    if "scheduling:views:read_global" in _saved_filter_permissions(user):
        condition = condition | (SchedulingSavedFilter.visibility == "global")
    return list(
        db.scalars(
            select(SchedulingSavedFilter)
            .where(condition)
            .order_by(SchedulingSavedFilter.visibility.asc(), SchedulingSavedFilter.updated_at.desc(), SchedulingSavedFilter.name.asc())
        )
    )


@router.post("/saved-filters", response_model=SchedulingSavedFilterOut, status_code=201, dependencies=[Depends(require_permission("scheduling:manage_filters"))])
def create_saved_filter(
    payload: SchedulingSavedFilterCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:manage_filters")),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Informe um nome para a visão.")
    visibility = payload.visibility if payload.visibility in ("personal", "global") else "personal"
    if visibility == "global":
        _ensure_global_saved_filter_permission(user)
    _ensure_unique_filter_name_scoped(db, user.id, name, visibility)
    item = SchedulingSavedFilter(
        user_id=user.id,
        name=name,
        filters=payload.filters.model_dump(mode="json"),
        visibility=visibility,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/saved-filters/{saved_filter_id}", response_model=SchedulingSavedFilterOut)
def update_saved_filter(
    saved_filter_id: int,
    payload: SchedulingSavedFilterUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:read")),
):
    item = _saved_filter_or_404_scoped(db, saved_filter_id, user)
    if not _can_manage_saved_filter(user, item):
        raise HTTPException(status_code=403, detail="Seu perfil não permite atualizar esta visão.")
    next_visibility = payload.visibility or item.visibility
    if next_visibility == "global" and item.visibility != "global":
        _ensure_global_saved_filter_permission(user)
    if item.visibility == "global":
        _ensure_global_saved_filter_permission(user)
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Informe um nome para a visão.")
        _ensure_unique_filter_name_scoped(db, user.id, name, next_visibility, exclude_id=item.id)
        item.name = name
    if payload.filters is not None:
        item.filters = payload.filters.model_dump(mode="json")
    if payload.visibility is not None:
        item.visibility = next_visibility
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/saved-filters/{saved_filter_id}", status_code=204)
def delete_saved_filter(
    saved_filter_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:read")),
):
    item = _saved_filter_or_404_scoped(db, saved_filter_id, user)
    if not _can_manage_saved_filter(user, item):
        raise HTTPException(status_code=403, detail="Seu perfil não permite excluir esta visão.")
    db.delete(item)
    db.commit()


@router.get("/filters", response_model=SchedulingFilterOptions)
def get_filter_options(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:read")),
):
    return metrics_engine.filter_options(db)


@router.get("/settings")
def get_settings_endpoint(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:read")),
):
    return metrics_engine.load_settings(db)


@router.put("/settings")
def update_settings_endpoint(
    payload: SchedulingSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:manage")),
):
    values = {key: value for key, value in payload.model_dump().items() if value is not None}
    return metrics_engine.save_settings(db, values)


@router.get("/team", response_model=list[SchedulingTeamMember])
def get_team(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:read")),
):
    """Operadores vistos no log local, com nome resolvido. Nomes desconhecidos são buscados no IXC
    uma única vez e ficam no cadastro local (`scheduling_operators`) - as leituras seguintes não
    tocam a API."""
    seen_ids = {
        int(op_id) for (op_id,) in db.execute(
            select(SchedulingEvent.operator_id).where(SchedulingEvent.operator_id.is_not(None)).distinct()
        )
    }
    known = {row.ixc_user_id: row for row in db.execute(select(SchedulingOperator)).scalars()}
    missing = sorted(seen_ids - set(known))
    if missing:
        try:
            for user_record in fetch_usuarios_by_ids(get_ixc_client(), missing):
                ixc_id = int(user_record.get("id") or 0)
                if ixc_id and ixc_id not in known:
                    row = SchedulingOperator(ixc_user_id=ixc_id, name=str(user_record.get("nome") or f"Operador IXC {ixc_id}"))
                    db.add(row)
                    known[ixc_id] = row
            db.commit()
        except IxcApiError:
            logger.warning("IXC indisponível ao resolver nomes de operadores - seguindo com os nomes locais.")
    rows = [known[i] for i in sorted(seen_ids) if i in known]
    rows.sort(key=lambda r: (not r.is_team_member, r.name))
    return rows


@router.put("/team", response_model=list[SchedulingTeamMember])
def update_team(
    payload: SchedulingTeamUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:manage")),
):
    wanted = set(payload.team_member_ids)
    for row in db.execute(select(SchedulingOperator)).scalars():
        row.is_team_member = row.ixc_user_id in wanted
    db.commit()
    rows = list(db.execute(select(SchedulingOperator).order_by(SchedulingOperator.name)).scalars())
    rows.sort(key=lambda r: (not r.is_team_member, r.name))
    return rows


@router.post("/technicians/resolve")
def resolve_technician_names(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:read")),
):
    """Resolve no IXC os técnicos (`id_tecnico`) vistos no log local que ainda não têm nome em
    cache (`scheduling_technicians`) - chamado uma vez ao abrir a tela, mesmo espírito do /team."""
    seen_ids = {
        int(tech_id) for (tech_id,) in db.execute(
            select(SchedulingEvent.technician_id).where(SchedulingEvent.technician_id.is_not(None)).distinct()
        )
    }
    known_ids = set(db.execute(select(SchedulingTechnician.ixc_funcionario_id)).scalars())
    missing = sorted(seen_ids - known_ids)
    resolved = 0
    if missing:
        try:
            for record in fetch_funcionarios_by_ids(get_ixc_client(), missing):
                ixc_id = int(record.get("id") or 0)
                if ixc_id and ixc_id not in known_ids:
                    db.add(SchedulingTechnician(ixc_funcionario_id=ixc_id, name=str(record.get("funcionario") or f"Técnico IXC {ixc_id}")))
                    known_ids.add(ixc_id)
                    resolved += 1
            db.commit()
        except IxcApiError:
            logger.warning("IXC indisponível ao resolver nomes de técnicos - seguindo com os nomes locais.")
    return {"resolved": resolved, "pending": len(missing) - resolved}


def _run_sync_job(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(SchedulingJob, job_id)
        if job is None:
            return
        job.status = "running"
        db.commit()
        try:
            result = run_sync(
                db,
                get_ixc_client(),
                date_from=job.params.get("date_from"),
                date_to=job.params.get("date_to"),
            )
        except (IxcApiError, RuntimeError) as exc:
            db.rollback()
            job = db.get(SchedulingJob, job_id)
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = datetime.utcnow()
            db.commit()
        except Exception:
            logger.exception("Falha inesperada no sync de agendamento (job=%s)", job_id)
            db.rollback()
            job = db.get(SchedulingJob, job_id)
            job.status = "failed"
            job.error = "Falha inesperada ao sincronizar com o IXC."
            job.finished_at = datetime.utcnow()
            db.commit()
        else:
            job = db.get(SchedulingJob, job_id)
            job.status = "completed"
            job.result = result
            job.finished_at = datetime.utcnow()
            db.commit()


@router.post("/sync", response_model=SchedulingSyncJobOut)
def start_sync(
    payload: SchedulingSyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:sync")),
):
    """Dispara sync com o IXC. Com `date_from`/`date_to` faz backfill do intervalo; sem parâmetros,
    incremental a partir da marca d'água. Acompanhe em GET /scheduling/sync/status."""
    if bool(payload.date_from) != bool(payload.date_to):
        raise HTTPException(status_code=400, detail="Informe as duas datas do backfill, ou nenhuma para sync incremental.")
    running = db.execute(
        select(SchedulingJob).where(SchedulingJob.job_type == "sync", SchedulingJob.status.in_(("pending", "running")))
    ).scalars().first()
    if running:
        raise HTTPException(status_code=409, detail=f"Já existe um sync em andamento (job {running.id}).")
    params = {
        "date_from": payload.date_from.isoformat() if payload.date_from else None,
        "date_to": payload.date_to.isoformat() if payload.date_to else None,
    }
    job = SchedulingJob(job_type="sync", status="pending", params=params, requested_by=user.id)
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_sync_job, job.id)
    return job


def _run_backfill_messages_job(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(SchedulingJob, job_id)
        if job is None:
            return
        job.status = "running"
        db.commit()
        try:
            result = backfill_messages(db, get_ixc_client())
        except IxcApiError as exc:
            db.rollback()
            job = db.get(SchedulingJob, job_id)
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = datetime.utcnow()
            db.commit()
        except Exception:
            logger.exception("Falha inesperada no backfill de mensagens (job=%s)", job_id)
            db.rollback()
            job = db.get(SchedulingJob, job_id)
            job.status = "failed"
            job.error = "Falha inesperada ao buscar mensagens no IXC."
            job.finished_at = datetime.utcnow()
            db.commit()
        else:
            job = db.get(SchedulingJob, job_id)
            job.status = "completed"
            job.result = result
            job.finished_at = datetime.utcnow()
            db.commit()


@router.post("/messages/backfill", response_model=SchedulingSyncJobOut)
def start_messages_backfill(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:manage")),
):
    """Preenche mensagem/histórico dos eventos sincronizados antes desses campos existirem
    (operação única - eventos novos já chegam com o texto pelo sync normal)."""
    running = db.execute(
        select(SchedulingJob).where(SchedulingJob.job_type == "backfill_messages", SchedulingJob.status.in_(("pending", "running")))
    ).scalars().first()
    if running:
        raise HTTPException(status_code=409, detail=f"Já existe um backfill de mensagens em andamento (job {running.id}).")
    job = SchedulingJob(job_type="backfill_messages", status="pending", params={}, requested_by=user.id)
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_backfill_messages_job, job.id)
    return job


@router.get("/messages/backfill/status", response_model=SchedulingSyncJobOut | None)
def messages_backfill_status(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:read")),
):
    return db.execute(
        select(SchedulingJob).where(SchedulingJob.job_type == "backfill_messages").order_by(SchedulingJob.id.desc())
    ).scalars().first()


@router.get("/sync/status", response_model=SchedulingSyncStatus)
def sync_status(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("scheduling:read")),
):
    last_job = db.execute(
        select(SchedulingJob).where(SchedulingJob.job_type == "sync").order_by(SchedulingJob.id.desc())
    ).scalars().first()
    return SchedulingSyncStatus(
        watermark=_get_watermark(db),
        last_job=last_job,
        orders_count=db.execute(select(func.count(SchedulingOrder.id))).scalar() or 0,
        events_count=db.execute(select(func.count(SchedulingEvent.id))).scalar() or 0,
    )
