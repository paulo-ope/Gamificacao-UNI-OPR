from __future__ import annotations

import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import ScoringSubjectRule, ServiceOrder


DEMO_SERVICE_ORDER_CODES = {f"OS-{code}" for code in range(1001, 1021)}

DEMO_SUBJECT_PAIRS = {
    ("manutencao", "queda de sinal"),
    ("manutencao", "lentidao"),
    ("ativacao", "nova instalacao"),
    ("mudanca de endereco", "mudanca residencial"),
    ("retorno", "retorno tecnico"),
    ("mudanca de tecnologia", "upgrade fibra"),
    ("recolhimento", "recolhimento de equipamento"),
}


def normalize(value: str | None) -> str:
    if not value:
        return ""
    cleaned = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in cleaned if not unicodedata.combining(ch)).strip().lower()


def subject_key(os_type: str | None, os_subject: str | None) -> tuple[str, str]:
    return normalize(os_type), normalize(os_subject)


def is_demo_service_order(order: ServiceOrder) -> bool:
    return str(order.os_code or "").strip().upper() in DEMO_SERVICE_ORDER_CODES


def is_demo_subject(os_type: str | None, os_subject: str | None) -> bool:
    return subject_key(os_type, os_subject) in DEMO_SUBJECT_PAIRS


def real_subject_keys(db: Session) -> set[tuple[str, str]]:
    orders = db.execute(select(ServiceOrder.os_code, ServiceOrder.os_type, ServiceOrder.os_subject)).all()
    return {
        subject_key(os_type, os_subject)
        for os_code, os_type, os_subject in orders
        if str(os_code or "").strip().upper() not in DEMO_SERVICE_ORDER_CODES and os_type and os_subject
    }


def real_service_orders(orders: list[ServiceOrder]) -> list[ServiceOrder]:
    return [order for order in orders if not is_demo_service_order(order)]


def matrix_subject_rules(db: Session) -> list[ScoringSubjectRule]:
    imported_subjects = real_subject_keys(db)
    rules = list(
        db.scalars(
            select(ScoringSubjectRule)
            .options(selectinload(ScoringSubjectRule.group))
            .order_by(ScoringSubjectRule.os_type.asc(), ScoringSubjectRule.os_subject.asc())
        )
    )
    return [
        rule
        for rule in rules
        if subject_key(rule.os_type, rule.os_subject) in imported_subjects
        or not is_demo_subject(rule.os_type, rule.os_subject)
    ]
