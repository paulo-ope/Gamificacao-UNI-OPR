"""Visão Geral: um card por módulo, composto a partir de funções JÁ EXISTENTES de cada módulo -
mesmo espírito de `intelligence/cockpit.py` (nenhuma métrica recalculada do zero aqui, só
composição). Cada card é melhor-esforço: se a consulta de um módulo falhar (dado ainda não
sincronizado, filtro sem resultado etc.), aquele card some da lista em vez de derrubar a Visão
Geral inteira - mas nunca silenciosamente quando o módulo simplesmente não é permitido ao usuário
(esse caso nem tenta consultar)."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.security import permissions_for_user
from app.models import User
from app.modules.registry import get_module

from .schemas import WorkspaceOverviewCardOut, WorkspaceOverviewOut


def _operations_card(db: Session, user: User) -> WorkspaceOverviewCardOut | None:
    from app.modules.operations import queries as ops_queries
    from app.modules.operations.scope import PRIMARY_SECTOR_NAMES

    today = date.today()
    overview = ops_queries.overview(db, today, today, user, sectors=list(PRIMARY_SECTOR_NAMES))
    sla_rate = overview.get("sla_rate")
    module = get_module("operations")
    return WorkspaceOverviewCardOut(
        module_key="operations",
        title=module.name,
        metric_label="O.S. abertas hoje",
        metric_value=str(overview.get("opened", 0)),
        subtitle=f"SLA hoje: {sla_rate}%" if sla_rate is not None else None,
        link=module.web_path,
    )


def _scheduling_card(db: Session, user: User) -> WorkspaceOverviewCardOut | None:
    from app.modules.scheduling import metrics as scheduling_metrics

    today = date.today()
    filters = scheduling_metrics.SchedulingFilters(date_from=today, date_to=today)
    dashboard = scheduling_metrics.build_dashboard(db, filters)
    summary = dashboard["summary"]
    module = get_module("scheduling")
    sla_rate = summary.get("sla_rate")
    return WorkspaceOverviewCardOut(
        module_key="scheduling",
        title=module.name,
        metric_label="O.S. agendadas hoje",
        metric_value=str(summary.get("scheduled_orders", 0)),
        subtitle=f"SLA hoje: {sla_rate}%" if sla_rate is not None else None,
        link=module.web_path,
    )


def _support_card(db: Session, user: User) -> WorkspaceOverviewCardOut | None:
    from app.modules.support import opa_overview_service
    from app.modules.support.opa_filters import OpaAttendanceFilters

    today = date.today()
    filters = OpaAttendanceFilters(date_from=today, date_to=today)
    metrics = opa_overview_service.overview_metrics(db, filters)
    module = get_module("support")
    return WorkspaceOverviewCardOut(
        module_key="support",
        title=module.name,
        metric_label="Atendimentos hoje",
        metric_value=str(metrics.get("total_attendances", 0)),
        subtitle=f"{round(metrics.get('closure_rate', 0.0), 1)}% encerrados",
        link=module.web_path,
    )


def _management_card(db: Session, user: User) -> WorkspaceOverviewCardOut | None:
    from app.modules.management import cases as cases_engine

    conditions = cases_engine.case_scope_conditions(user)
    summary = cases_engine.summarize_cases(db, conditions)
    module = get_module("management")
    return WorkspaceOverviewCardOut(
        module_key="management",
        title=module.name,
        metric_label="Casos pendentes",
        metric_value=str(summary.get("pending_cases", 0)),
        subtitle=f"{summary.get('overdue_cases', 0)} em atraso" if summary.get("overdue_cases") else None,
        link=module.web_path,
    )


# Módulo -> (permissão necessária, função que monta o card). Só os módulos com uma métrica de
# resumo simples já pronta entram aqui - gamification/admin/intelligence ficam de fora desta
# primeira rodada (não têm um summary de "um número" equivalente pronto pra reaproveitar sem
# recalcular algo do zero); a Visão Geral pode ganhar mais cards depois, um de cada vez.
_CARD_BUILDERS: tuple[tuple[str, str, callable], ...] = (
    ("operations", "operations:read", _operations_card),
    ("scheduling", "scheduling:read", _scheduling_card),
    ("support", "support:read", _support_card),
    ("management", "management:read", _management_card),
)


def build_overview(db: Session, user: User) -> WorkspaceOverviewOut:
    permissions = permissions_for_user(user)
    cards: list[WorkspaceOverviewCardOut] = []
    for module_key, required_permission, builder in _CARD_BUILDERS:
        if required_permission not in permissions:
            continue
        try:
            card = builder(db, user)
        except Exception:  # um módulo com dado indisponível não pode derrubar a Visão Geral inteira
            continue
        if card is not None:
            cards.append(card)
    return WorkspaceOverviewOut(cards=cards)
