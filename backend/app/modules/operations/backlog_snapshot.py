from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal

from .models import OperationBacklogSnapshot, OperationOrder, OperationResponsibleAssignment, OperationTeamModel
from .period import OPERATIONS_TIMEZONE

logger = logging.getLogger(__name__)


def _team_model_label():
    # Mesma lógica de `ai/queries.py:_group_label` (caso "team_model") - não importada de lá de
    # propósito (operations não deve depender do módulo ai, é o contrário) - se aquela mudar,
    # esta precisa mudar também. Casa só pelo nome do responsável (case-insensitive), igual ao
    # filtro `team_models` (`_dimension_conditions`) - NUNCA pela regional da atribuição (achado
    # real: exigir regional igual fazia esta função e o filtro discordarem sobre a mesma O.S.).
    # Quando o nome tem mais de uma atribuição, prevalece a mais recentemente atualizada (mesmo
    # critério de `team_configuration`).
    team_model_name = (
        select(OperationTeamModel.name)
        .join(OperationResponsibleAssignment, OperationResponsibleAssignment.team_model_id == OperationTeamModel.id)
        .where(func.lower(OperationResponsibleAssignment.responsible_name) == func.lower(OperationOrder.responsible))
        .order_by(OperationResponsibleAssignment.updated_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    return func.coalesce(team_model_name, "Não identificado")


def capture_backlog_snapshot(db: Session) -> int:
    """Grava a fotografia de hoje do backlog (regional x modelo de equipe x setor), se ainda não
    existir. Idempotente: se já existe qualquer linha para a data de hoje, não faz nada - nunca
    duplica nem sobrescreve (se o backlog mudar depois no mesmo dia, a fotografia reflete o
    momento em que o job rodou primeiro, por desenho, já que o objetivo é "como estava hoje", não
    uma amostragem contínua). Retorna quantas linhas foram gravadas (0 se já existia)."""
    today = datetime.now(OPERATIONS_TIMEZONE).date()
    already_captured = db.scalar(
        select(func.count(OperationBacklogSnapshot.id)).where(OperationBacklogSnapshot.snapshot_date == today)
    )
    if already_captured:
        return 0

    regional_label = func.coalesce(OperationOrder.regional, "Não identificado")
    team_model_label = _team_model_label()
    sector_label = func.coalesce(OperationOrder.sector, "Não identificado")
    city_label = func.coalesce(OperationOrder.city, "Não identificado")
    rows = db.execute(
        select(
            regional_label,
            team_model_label,
            sector_label,
            city_label,
            func.count(OperationOrder.id),
            func.sum(case((OperationOrder.sla_status == "out_of_time", 1), else_=0)),
        )
        .where(OperationOrder.is_closed.is_(False))
        .group_by(regional_label, team_model_label, sector_label, city_label)
    ).all()

    for regional, team_model, sector, city, backlog_count, backlog_atrasado_count in rows:
        db.add(
            OperationBacklogSnapshot(
                snapshot_date=today,
                regional=regional,
                team_model=team_model,
                sector=sector,
                city=city,
                backlog_count=int(backlog_count),
                backlog_atrasado_count=int(backlog_atrasado_count or 0),
            )
        )
    db.commit()
    return len(rows)


async def run_backlog_snapshot_loop() -> None:
    """Confere de hora em hora se a fotografia de hoje já foi capturada; se não, captura.
    Checar por hora (em vez de num horário fixo 1x/dia) tolera reinícios do processo - a captura
    sempre acontece na primeira checagem depois da virada do dia, sem depender de um agendador
    externo (mesmo padrão assíncrono de `ixc_scheduler.run_ixc_sync_loop`)."""
    POLL_SECONDS = 3600.0
    while True:
        try:
            with SessionLocal() as db:
                captured = await asyncio.to_thread(capture_backlog_snapshot, db)
            if captured:
                logger.info("Backlog snapshot capturado: %d linhas.", captured)
        except Exception:
            logger.exception("Falha ao capturar snapshot diário de backlog.")
        await asyncio.sleep(POLL_SECONDS)
