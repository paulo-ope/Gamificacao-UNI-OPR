"""Regras da aba Especialista/Analista: projetos e tarefas lançados pela equipe do Suporte.

Tudo o que é lançado é visível para quem acessa o Suporte Interno (`support:read`); quem grava
precisa de `support:plan_write` (checado na rota). Aqui ficam as regras: tipo e pai, transição de
status, conclusão com resultado, atraso, progresso do projeto e conflito de edição por versão.
Nada é excluído: item sai de cena por arquivamento."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.security import permissions_for_user
from app.models import User

from .models import SupportPlanItem, SupportPlanUpdate
from .opa_filters import SUPPORT_TIMEZONE

OPEN_STATUSES = ("planned", "in_progress", "blocked")
CLOSED_STATUSES = ("done", "canceled")
# Ordem do quadro: o que pede atenção primeiro.
STATUS_ORDER = {"blocked": 0, "in_progress": 1, "planned": 2, "done": 3, "canceled": 4}
CREATE_STATUSES = ("planned", "in_progress", "blocked")
SUMMARY_PERIOD_DAYS = 30
# Gravar texto de andamento ao bloquear ou cancelar: sem motivo, o quadro vira um muro mudo.
STATUSES_REQUIRING_TEXT = ("blocked", "canceled")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return datetime.now(SUPPORT_TIMEZONE).date()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _conflict() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail="Este item foi alterado por outra pessoa. Atualize a tela e tente de novo.",
    )


def _is_overdue(item: SupportPlanItem, today: date) -> bool:
    return item.due_date is not None and item.due_date < today and item.status in OPEN_STATUSES


def _get_item(db: Session, item_id: int) -> SupportPlanItem:
    item = db.get(SupportPlanItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    return item


def _check_version(item: SupportPlanItem, version: int) -> None:
    if item.version != version:
        raise _conflict()


def _users_by_id(db: Session, ids: set[int]) -> dict[int, User]:
    if not ids:
        return {}
    return {user.id: user for user in db.scalars(select(User).where(User.id.in_(ids)))}


def _validated_assignees(db: Session, assignee_ids: list[int]) -> list[int]:
    unique = list(dict.fromkeys(assignee_ids))
    users = _users_by_id(db, set(unique))
    for user_id in unique:
        user = users.get(user_id)
        if user is None or not user.active:
            raise _bad_request("Responsável inválido ou inativo.")
    return unique


def _validated_parent(db: Session, kind: str, parent_id: int | None, item_id: int | None = None) -> int | None:
    if parent_id is None:
        return None
    if kind != "task":
        raise _bad_request("Só tarefa pode pertencer a um projeto.")
    if item_id is not None and parent_id == item_id:
        raise _bad_request("Um item não pode pertencer a si mesmo.")
    parent = db.get(SupportPlanItem, parent_id)
    if parent is None or parent.kind != "project":
        raise _bad_request("O projeto informado não existe.")
    if parent.archived:
        raise _bad_request("O projeto informado está arquivado.")
    return parent_id


def _audit_snapshot(item: SupportPlanItem) -> dict[str, Any]:
    return {
        "kind": item.kind,
        "title": item.title,
        "status": item.status,
        "priority": item.priority,
        "due_date": item.due_date.isoformat() if item.due_date else None,
        "assignee_ids": list(item.assignee_ids or []),
        "parent_id": item.parent_id,
        "archived": item.archived,
        "version": item.version,
    }


def audit_snapshot(item: SupportPlanItem) -> dict[str, Any]:
    return _audit_snapshot(item)


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------
def create_item(db: Session, user: User, payload) -> SupportPlanItem:
    title = _clean(payload.title)
    if not title:
        raise _bad_request("Informe o título.")
    if payload.status not in CREATE_STATUSES:
        raise _bad_request("Um item novo não pode nascer concluído ou cancelado.")
    parent_id = _validated_parent(db, payload.kind, payload.parent_id)
    now = _now()
    item = SupportPlanItem(
        kind=payload.kind,
        parent_id=parent_id,
        title=title,
        description=_clean(payload.description),
        status=payload.status,
        priority=payload.priority,
        due_date=payload.due_date,
        assignee_ids=_validated_assignees(db, payload.assignee_ids),
        archived=False,
        version=1,
        created_by_id=user.id,
        created_by_name=user.name,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    db.flush()
    return item


def update_item(db: Session, item_id: int, payload) -> tuple[SupportPlanItem, dict[str, Any]]:
    item = _get_item(db, item_id)
    _check_version(item, payload.version)
    before = _audit_snapshot(item)
    if payload.title is not None:
        title = _clean(payload.title)
        if not title:
            raise _bad_request("Informe o título.")
        item.title = title
    if payload.description is not None:
        item.description = _clean(payload.description)
    if payload.priority is not None:
        item.priority = payload.priority
    if payload.clear_due_date:
        item.due_date = None
    elif payload.due_date is not None:
        item.due_date = payload.due_date
    if payload.assignee_ids is not None:
        item.assignee_ids = _validated_assignees(db, payload.assignee_ids)
    if payload.clear_parent:
        item.parent_id = None
    elif payload.parent_id is not None:
        item.parent_id = _validated_parent(db, item.kind, payload.parent_id, item.id)
    if payload.result is not None:
        item.result = _clean(payload.result)
    item.version += 1
    item.updated_at = _now()
    db.flush()
    return item, before


def add_update(db: Session, user: User, item_id: int, payload) -> tuple[SupportPlanItem, dict[str, Any]]:
    item = _get_item(db, item_id)
    _check_version(item, payload.version)
    if item.archived:
        raise _bad_request("Item arquivado: desarquive para registrar andamento.")
    before = _audit_snapshot(item)
    text = _clean(payload.text) or ""
    new_status = payload.status if payload.status and payload.status != item.status else None
    if not text and new_status is None:
        raise _bad_request("Escreva o andamento ou escolha um novo status.")
    if new_status in STATUSES_REQUIRING_TEXT and not text:
        raise _bad_request("Explique o motivo ao bloquear ou cancelar.")
    status_from = item.status
    if new_status == "done":
        result = _clean(payload.result) or item.result
        if not result:
            raise _bad_request("Para concluir, descreva o resultado: o que foi feito e o que mudou.")
        item.result = result
        item.completed_at = _now()
    elif new_status is not None and item.status == "done":
        # Reabrir: o resultado e a data de conclusão antigos deixam de valer.
        item.completed_at = None
    elif payload.result is not None:
        item.result = _clean(payload.result)
    if new_status is not None:
        item.status = new_status
    item.version += 1
    item.updated_at = _now()
    db.add(
        SupportPlanUpdate(
            item_id=item.id,
            author_id=user.id,
            author_name=user.name,
            text=text,
            status_from=status_from if new_status is not None else None,
            status_to=new_status,
            created_at=item.updated_at,
        )
    )
    db.flush()
    return item, before


def set_archived(db: Session, item_id: int, payload) -> tuple[SupportPlanItem, dict[str, Any]]:
    item = _get_item(db, item_id)
    _check_version(item, payload.version)
    before = _audit_snapshot(item)
    item.archived = payload.archived
    item.version += 1
    item.updated_at = _now()
    db.flush()
    return item, before


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def _person(users: dict[int, User], user_id: int) -> dict[str, Any]:
    user = users.get(user_id)
    return {"id": user_id, "name": user.name if user else "Usuário removido"}


def _serialize(
    item: SupportPlanItem,
    *,
    users: dict[int, User],
    parent_titles: dict[int, str],
    task_counts: dict[int, tuple[int, int]],
    update_counts: dict[int, int],
    today: date,
) -> dict[str, Any]:
    total, done = task_counts.get(item.id, (0, 0))
    return {
        "id": item.id,
        "kind": item.kind,
        "parent_id": item.parent_id,
        "parent_title": parent_titles.get(item.parent_id) if item.parent_id else None,
        "title": item.title,
        "description": item.description,
        "status": item.status,
        "priority": item.priority,
        "due_date": item.due_date,
        "overdue": _is_overdue(item, today),
        "assignees": [_person(users, user_id) for user_id in (item.assignee_ids or [])],
        "result": item.result,
        "completed_at": item.completed_at,
        "archived": item.archived,
        "version": item.version,
        "created_by_name": item.created_by_name,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "tasks_total": total,
        "tasks_done": done,
        "updates_count": update_counts.get(item.id, 0),
    }


def _serialize_many(db: Session, items: list[SupportPlanItem]) -> list[dict[str, Any]]:
    today = _today()
    user_ids = {user_id for item in items for user_id in (item.assignee_ids or [])}
    users = _users_by_id(db, user_ids)
    item_ids = [item.id for item in items]
    parent_ids = {item.parent_id for item in items if item.parent_id}
    parent_titles = (
        dict(db.execute(select(SupportPlanItem.id, SupportPlanItem.title).where(SupportPlanItem.id.in_(parent_ids))).all())
        if parent_ids
        else {}
    )
    task_counts: dict[int, tuple[int, int]] = {}
    update_counts: dict[int, int] = {}
    if item_ids:
        totals: dict[int, list[int]] = defaultdict(lambda: [0, 0])
        for parent_id, status, count in db.execute(
            select(SupportPlanItem.parent_id, SupportPlanItem.status, func.count())
            .where(
                SupportPlanItem.parent_id.in_(item_ids),
                SupportPlanItem.archived.is_(False),
                SupportPlanItem.status != "canceled",
            )
            .group_by(SupportPlanItem.parent_id, SupportPlanItem.status)
        ):
            totals[parent_id][0] += count
            if status == "done":
                totals[parent_id][1] += count
        task_counts = {key: (value[0], value[1]) for key, value in totals.items()}
        update_counts = dict(
            db.execute(
                select(SupportPlanUpdate.item_id, func.count())
                .where(SupportPlanUpdate.item_id.in_(item_ids))
                .group_by(SupportPlanUpdate.item_id)
            ).all()
        )
    return [
        _serialize(item, users=users, parent_titles=parent_titles, task_counts=task_counts, update_counts=update_counts, today=today)
        for item in items
    ]


def _sort_key(item: SupportPlanItem):
    return (
        item.archived,
        STATUS_ORDER.get(item.status, 9),
        item.due_date is None,
        item.due_date or date.max,
        -item.id,
    )


def list_items(
    db: Session,
    *,
    statuses: list[str] | None = None,
    kind: str | None = None,
    assignee_id: int | None = None,
    search: str | None = None,
    include_archived: bool = False,
    only_overdue: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    statement = select(SupportPlanItem)
    if not include_archived:
        statement = statement.where(SupportPlanItem.archived.is_(False))
    if statuses:
        statement = statement.where(SupportPlanItem.status.in_(statuses))
    if kind:
        statement = statement.where(SupportPlanItem.kind == kind)
    term = _clean(search)
    if term:
        like = f"%{term}%"
        statement = statement.where(or_(SupportPlanItem.title.ilike(like), SupportPlanItem.description.ilike(like)))
    items = list(db.scalars(statement))
    # Responsável fica em JSON: o volume é pequeno (dezenas de itens), então filtra em Python.
    if assignee_id is not None:
        items = [item for item in items if assignee_id in (item.assignee_ids or [])]
    if only_overdue:
        today = _today()
        items = [item for item in items if _is_overdue(item, today)]
    items.sort(key=_sort_key)
    page = items[offset : offset + limit]
    return {"items": _serialize_many(db, page), "total": len(items)}


def item_detail(db: Session, item_id: int) -> dict[str, Any]:
    item = _get_item(db, item_id)
    base = _serialize_many(db, [item])[0]
    updates = list(
        db.scalars(
            select(SupportPlanUpdate)
            .where(SupportPlanUpdate.item_id == item.id)
            .order_by(SupportPlanUpdate.created_at.desc(), SupportPlanUpdate.id.desc())
        )
    )
    children = list(
        db.scalars(
            select(SupportPlanItem).where(SupportPlanItem.parent_id == item.id, SupportPlanItem.archived.is_(False))
        )
    )
    children.sort(key=_sort_key)
    today = _today()
    users = _users_by_id(db, {user_id for child in children for user_id in (child.assignee_ids or [])})
    return {
        **base,
        "updates": [
            {
                "id": update.id,
                "author_name": update.author_name,
                "text": update.text,
                "status_from": update.status_from,
                "status_to": update.status_to,
                "created_at": update.created_at,
            }
            for update in updates
        ],
        "children": [
            {
                "id": child.id,
                "title": child.title,
                "status": child.status,
                "due_date": child.due_date,
                "overdue": _is_overdue(child, today),
                "assignees": [_person(users, user_id) for user_id in (child.assignee_ids or [])],
            }
            for child in children
        ],
    }


def summary(db: Session) -> dict[str, Any]:
    today = _today()
    active = list(db.scalars(select(SupportPlanItem).where(SupportPlanItem.archived.is_(False))))
    since = _now() - timedelta(days=SUMMARY_PERIOD_DAYS)
    return {
        "open": sum(1 for item in active if item.status in OPEN_STATUSES),
        "in_progress": sum(1 for item in active if item.status == "in_progress"),
        "blocked": sum(1 for item in active if item.status == "blocked"),
        "overdue": sum(1 for item in active if _is_overdue(item, today)),
        "done_in_period": sum(
            1 for item in active if item.status == "done" and item.completed_at is not None and _aware(item.completed_at) >= since
        ),
        "period_days": SUMMARY_PERIOD_DAYS,
    }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def people(db: Session) -> list[dict[str, Any]]:
    """Quem pode ser responsável: usuários ativos que têm permissão de lançar projetos e tarefas."""
    users = db.scalars(select(User).where(User.active.is_(True)).order_by(User.name))
    return [{"id": user.id, "name": user.name} for user in users if "support:plan_write" in permissions_for_user(user)]
