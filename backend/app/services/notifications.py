"""Notificações in-app: sino no topo, sem integração externa - avisa um usuário de algo que
precisa da atenção dele, com um link pra abrir direto o que gerou o aviso."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import permissions_for_user
from app.models import Notification, User


def create_notification(
    db: Session,
    *,
    user_id: int,
    title: str,
    message: str,
    link_url: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        link_url=link_url,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(notification)
    db.flush()
    return notification


def notify_users_with_permission(
    db: Session,
    *,
    permission: str,
    title: str,
    message: str,
    link_url: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    exclude_user_id: int | None = None,
) -> list[Notification]:
    """Notifica todo usuário ativo que tem `permission` - usado para avisar a matriz
    (`management:review`) sem precisar saber de antemão quem são essas pessoas (o conjunto pode
    mudar a qualquer momento via Admin > Perfis, sem exigir código novo aqui).

    `exclude_user_id`: quem disparou a ação não precisa ser notificado de si mesmo (ex.: um
    admin com `management:review` que também justifica os próprios casos)."""
    users = db.scalars(select(User).where(User.active.is_(True))).all()
    created: list[Notification] = []
    for user in users:
        if user.id == exclude_user_id:
            continue
        if permission not in permissions_for_user(user):
            continue
        created.append(
            create_notification(
                db,
                user_id=user.id,
                title=title,
                message=message,
                link_url=link_url,
                entity_type=entity_type,
                entity_id=entity_id,
            )
        )
    return created


def unread_count(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count(Notification.id)).where(Notification.user_id == user_id, Notification.is_read.is_(False))
    ) or 0


def list_for_user(db: Session, user_id: int, *, limit: int = 30) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
    )


def mark_read(db: Session, user_id: int, notification_id: int) -> Notification | None:
    notification = db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
    )
    if notification is None:
        return None
    notification.is_read = True
    db.flush()
    return notification


def mark_all_read(db: Session, user_id: int) -> int:
    notifications = db.scalars(
        select(Notification).where(Notification.user_id == user_id, Notification.is_read.is_(False))
    ).all()
    for notification in notifications:
        notification.is_read = True
    if notifications:
        db.flush()
    return len(notifications)
