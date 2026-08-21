"""Resolução de "responsável x regional" a partir das fontes brutas do IXC (cadastro manual de
responsável + histórico de O.S.) - fonte única pra essa lógica, que antes só existia dentro de
`management/services.py` (reorganização pedida pelo usuário em 2026-08-21, plano em
generic-riding-petal.md).

Fica em `operations/`, não em `management/`, porque `management` já importa de `operations` (e
nunca o contrário) - manter aqui deixa a porta aberta pra `operations/queries.py:team_by_identity`
(hoje uma 4ª lógica ad hoc e mais simples do mesmo problema) reusar isto no futuro, sem inverter
dependência entre os módulos.

IMPORTANTE: isto NÃO resolve "a regional de uma pessoa" como um valor único - uma pessoa pode
aparecer em mais de um par (responsible_name, regional) quando tem cadastro manual numa regional e
histórico de O.S. em outra (ex.: mudança de base). Isso reflete o que `management/services.py`
já materializava manualmente antes desta extração; a função devolve a LISTA de candidatos
(um por par), não um valor único por pessoa."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import OperationOrder, OperationResponsibleAssignment

ResponsibleRegionalSource = Literal["assignment", "order_history"]


@dataclass(frozen=True)
class ResponsibleRegionalCandidate:
    responsible_name: str
    regional: str  # ainda não normalizada (normalize_regional) - mesma responsabilidade do chamador de antes
    team_model_id: int | None
    ixc_employee_id: int | None
    last_order_at: datetime | None
    source: ResponsibleRegionalSource


def resolve_responsible_regional_candidates(db: Session) -> list[ResponsibleRegionalCandidate]:
    """Réplica exata da lógica que antes vivia em `refresh_operational_members`: para um par
    (responsible_name, regional), o cadastro manual (`OperationResponsibleAssignment`) tem
    prioridade sobre o histórico agregado de O.S. fechadas/abertas - pares só vistos no histórico
    (sem cadastro manual para aquele MESMO par) entram com `source="order_history"`."""
    last_orders = {
        (row.responsible_name, row.regional): row
        for row in db.execute(
            select(
                OperationOrder.responsible.label("responsible_name"),
                OperationOrder.regional.label("regional"),
                func.max(OperationOrder.responsible_ixc_id).label("ixc_employee_id"),
                func.max(func.coalesce(OperationOrder.closed_at, OperationOrder.opened_at)).label("last_order_at"),
            )
            .where(OperationOrder.responsible.is_not(None), OperationOrder.responsible != "")
            .where(OperationOrder.regional.is_not(None), OperationOrder.regional != "")
            .group_by(OperationOrder.responsible, OperationOrder.regional)
        ).all()
    }

    candidates: dict[tuple[str, str], ResponsibleRegionalCandidate] = {}
    assignments = db.scalars(select(OperationResponsibleAssignment)).all()
    for assignment in assignments:
        key = (assignment.responsible_name, assignment.regional)
        order_info = last_orders.get(key)
        candidates[key] = ResponsibleRegionalCandidate(
            responsible_name=assignment.responsible_name,
            regional=assignment.regional,
            team_model_id=assignment.team_model_id,
            ixc_employee_id=int(order_info.ixc_employee_id) if order_info and order_info.ixc_employee_id else None,
            last_order_at=order_info.last_order_at if order_info else None,
            source="assignment",
        )

    for key, order_info in last_orders.items():
        if key in candidates:
            continue
        candidates[key] = ResponsibleRegionalCandidate(
            responsible_name=order_info.responsible_name,
            regional=order_info.regional,
            team_model_id=None,
            ixc_employee_id=int(order_info.ixc_employee_id) if order_info.ixc_employee_id else None,
            last_order_at=order_info.last_order_at,
            source="order_history",
        )

    return list(candidates.values())
