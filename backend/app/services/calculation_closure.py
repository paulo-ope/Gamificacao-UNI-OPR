from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import delete, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.security import is_admin_user
from app.models import (
    CALCULATION_RUN_STATUSES,
    CalculationRun,
    CalculationRunLock,
    CollaboratorScore,
    LeadershipProfile,
    LeadershipRoleProfile,
    User,
)
from app.services.audit_log import snapshot
from app.services.leadership_bonus import serialize_profile, serialize_role_profile
from app.services.regional import normalize_regional_grouped as normalize_regional

# Fuso da operação (Rondônia - sem horário de verão) - usado para decidir "qual é o mês corrente"
# de forma consistente com o horário local que o próprio IXC grava nas datas de O.S (ver
# ixc_importer.parse_ixc_datetime e docs/plano-integracao-ixc.md). Usar o relógio UTC do container
# para essa decisão erraria a virada do mês por até 4h (achado real).
PORTO_VELHO_TZ = ZoneInfo("America/Porto_Velho")


def now_porto_velho() -> datetime:
    return datetime.now(PORTO_VELHO_TZ)


def current_reference_period() -> tuple[int, int]:
    """(mes, ano) corrente no fuso de Porto Velho - a referência usada em todo o sistema para decidir
    se um período de apuração "já virou mês" e deve ser tratado como encerrado para fins de
    pontuação, independente de já ter sido marcado como pago."""
    now = now_porto_velho()
    return now.month, now.year


def is_period_in_the_past(reference_month: int, reference_year: int) -> bool:
    current_month, current_year = current_reference_period()
    return (reference_year, reference_month) < (current_year, current_month)


ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"review", "cancelled"},
    "review": {"approved", "cancelled"},
    "approved": {"paid", "cancelled"},
    "paid": set(),
    "cancelled": set(),
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# --- Trava de exclusão mútua contra cálculo concorrente do mesmo ciclo (P0-4 da auditoria de -----
# 2026-09-15): `/calculation-runs/calculate` e o recálculo automático (`recalculate_current_period`,
# disparado pelo sincronizador do IXC e por correções de Tipo Geral) chamam `calculate_scores` sem
# NENHUMA proteção contra duas execuções do MESMO ciclo (mesmo mês/ano/regional) em paralelo. O app
# roda como um único processo `uvicorn` (sem `--workers`), mas os handlers síncronos das rotas
# rodam no threadpool do FastAPI e o sincronizador do IXC roda em paralelo a eles (`asyncio` +
# `run_in_threadpool`) - um clique manual em "recalcular" pode literalmente sobrepor o ciclo
# automático de 20 em 20 minutos, cada um com sua própria `Session`/conexão. Sem trava, os dois
# criam um `CalculationRun` e um lote de `CollaboratorScore` cada um, e os dois podem aplicar
# `point_balance.detect_post_payment_warranty_debits` em duplicidade (suas guardas são `SELECT`
# puro - só enxergam o que já foi COMMITADO, não o que a outra transação ainda não commitou).
#
# O `SELECT ... FOR UPDATE` que já existe em
# `calculation_runs.py::change_calculation_run_status` (achado C5 da auditoria 2026-08-26) protege
# a TRANSIÇÃO de status de um run que já existe - não cobre a CRIAÇÃO do rascunho, que é o caminho
# do P0-4.

CALCULATION_LOCK_STALE_AFTER = timedelta(minutes=30)
CALCULATION_LOCK_GLOBAL_REGIONAL_KEY = "__ALL__"


def _calculation_lock_key(reference_month: int, reference_year: int, normalized_regional: str | None) -> str:
    return f"{reference_year:04d}-{reference_month:02d}:{normalized_regional or CALCULATION_LOCK_GLOBAL_REGIONAL_KEY}"


def acquire_calculation_lock(
    db: Session,
    reference_month: int,
    reference_year: int,
    regional: str | None,
    user: User | None = None,
) -> str:
    """Adquire a trava exclusiva do ciclo (mês/ano/regional) - ver `CalculationRunLock`.

    A garantia é o `UniqueConstraint(lock_key)` do banco, não este código Python: insere e
    COMMITA imediatamente, numa transação própria e curta, para que a trava fique visível a
    QUALQUER outra conexão (outro processo, outra thread) assim que adquirida - não espera o
    commit final do cálculo inteiro, que só acontece bem depois (`leadership_bonus`/auditoria
    inclusos). Se outra transação já tem a mesma chave commitada, o `INSERT` estoura
    `IntegrityError` e aqui vira um 409 controlado - nunca deixa duas computações do mesmo ciclo
    rodarem ao mesmo tempo.

    Antes de tentar, rouba (apaga) uma trava mais velha que `CALCULATION_LOCK_STALE_AFTER`: sem
    isso, um processo derrubado no meio do cálculo (kill -9, OOM, deploy) travaria o ciclo pra
    sempre, já que ninguém mais chamaria `release_calculation_lock`.
    """
    normalized_regional = normalize_regional(regional) if regional else None
    lock_key = _calculation_lock_key(reference_month, reference_year, normalized_regional)

    db.execute(
        delete(CalculationRunLock)
        .where(CalculationRunLock.lock_key == lock_key)
        .where(CalculationRunLock.locked_at < now_utc() - CALCULATION_LOCK_STALE_AFTER)
    )
    db.commit()

    db.add(
        CalculationRunLock(
            lock_key=lock_key,
            reference_month=reference_month,
            reference_year=reference_year,
            regional=normalized_regional,
            locked_at=now_utc(),
            locked_by=user.id if user else None,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        scope_label = f" (regional {normalized_regional})" if normalized_regional else ""
        raise HTTPException(
            status_code=409,
            detail=(
                f"Já existe um cálculo em andamento para {reference_month:02d}/{reference_year}"
                f"{scope_label}. Aguarde a conclusão e tente novamente."
            ),
        )
    return lock_key


def release_calculation_lock(db: Session, lock_key: str) -> None:
    """Libera a trava adquirida por `acquire_calculation_lock`, numa transação própria.

    Roda mesmo quando quem chamou já deu `db.rollback()` no cálculo que falhou: a trava foi
    commitada numa transação SEPARADA em `acquire_calculation_lock`, então continua existindo no
    banco até ser apagada aqui explicitamente - um rollback do cálculo em si nunca a desfaz
    sozinho. É esta chamada (sempre em `finally`, ver `calculation_cycle_lock`) que garante que
    uma falha no meio do cálculo não deixa a trava presa indefinidamente.
    """
    db.execute(delete(CalculationRunLock).where(CalculationRunLock.lock_key == lock_key))
    db.commit()


@contextmanager
def calculation_cycle_lock(
    db: Session,
    reference_month: int,
    reference_year: int,
    regional: str | None,
    user: User | None = None,
) -> Iterator[None]:
    """`with calculation_cycle_lock(db, month, year, regional, user=user):` em volta de TODO o
    trecho que calcula e commita um ciclo (`calculate_scores` + bônus de liderança + auditoria +
    commit final) - em ambos os pontos de entrada (`/calculation-runs/calculate` e
    `recalculate_current_period`). Levanta 409 (via `acquire_calculation_lock`) antes de fazer
    qualquer trabalho se o mesmo ciclo já está sendo calculado em outro lugar; sempre libera a
    trava ao sair do bloco, com sucesso ou com exceção.
    """
    lock_key = acquire_calculation_lock(db, reference_month, reference_year, regional, user=user)
    try:
        yield
    finally:
        release_calculation_lock(db, lock_key)


def normalize_run_status(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in CALCULATION_RUN_STATUSES:
        raise HTTPException(status_code=422, detail="Status de fechamento inválido.")
    return normalized


def serialize_run_status(run: CalculationRun) -> dict[str, Any]:
    return {
        "status": run.status,
        "status_changed_at": run.status_changed_at,
        "status_changed_by": run.status_changed_by,
        "status_note": run.status_note,
        "approved_at": run.approved_at,
        "approved_by": run.approved_by,
        "paid_at": run.paid_at,
        "paid_by": run.paid_by,
        "executed_at": run.executed_at,
        "executed_by": run.executed_by,
    }


def ensure_status_transition_allowed(current_status: str, next_status: str) -> None:
    current = normalize_run_status(current_status)
    target = normalize_run_status(next_status)
    if current == target:
        # Estados terminais nao aceitam nem o reenvio do proprio status: re-marcar como "pago"
        # re-executaria o consumo de saldo de pontos contra um fechamento ja encerrado.
        if current in {"paid", "cancelled"}:
            raise HTTPException(
                status_code=409,
                detail=f"Fechamento já está em '{current}' e não pode ser alterado.",
            )
        return
    if target not in ALLOWED_STATUS_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Transição de status inválida: {current} -> {target}.",
        )


def ensure_status_change_permission(user: User, next_status: str) -> None:
    target = normalize_run_status(next_status)
    if target in {"approved", "paid"} and not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Somente administrador pode aprovar ou marcar como pago.")


def ensure_no_overlapping_paid_period(db: Session, run: CalculationRun) -> None:
    """Impede marcar como PAGO um fechamento cujos colaboradores ja foram pagos para o
    mesmo periodo (mes/ano) por OUTRO CalculationRun - cobre tanto a sobreposicao entre
    um fechamento agregado (regional=None) e um fechamento regional especifico quanto uma
    revisao (allow_paid_revision) que seria marcada como paga depois do fechamento original.
    Sem esta trava, o mesmo colaborador pode ser pago duas vezes no mesmo mes via dois
    CalculationRun distintos, porque nao existe unique constraint em (mes, ano, regional)."""
    db.flush()
    collaborator_ids = {score.collaborator_id for score in run.scores}
    if not collaborator_ids:
        return

    rows = db.execute(
        select(CollaboratorScore.collaborator_id, CalculationRun.id)
        .join(CalculationRun, CalculationRun.id == CollaboratorScore.calculation_run_id)
        .where(CalculationRun.reference_month == run.reference_month)
        .where(CalculationRun.reference_year == run.reference_year)
        .where(CalculationRun.status == "paid")
        .where(CalculationRun.id != run.id)
        .where(CollaboratorScore.collaborator_id.in_(collaborator_ids))
    ).all()

    if rows:
        overlapping_collaborators = {row[0] for row in rows}
        conflicting_run_ids = sorted({row[1] for row in rows})
        run_list = ", ".join(f"#{rid}" for rid in conflicting_run_ids)
        raise HTTPException(
            status_code=409,
            detail=(
                f"{len(overlapping_collaborators)} colaborador(es) deste fechamento ja foram pagos para "
                f"{run.reference_month:02d}/{run.reference_year} pelo(s) fechamento(s) {run_list}. "
                "Não é possível marcar como pago para evitar pagamento em duplicidade. "
                "Cancele este fechamento ou reconcilie com o outro antes de continuar."
            ),
        )


def ensure_no_unregistered_payable_collaborators(run: CalculationRun) -> None:
    """Trava de segurança final antes de marcar como PAGO: mesmo com o cálculo já zerando o
    estimated_payment de colaboradores não cadastrados (ver calculation.py), esta checagem
    independe dessa lógica e barra o pagamento se, por qualquer motivo (dado antigo, edição
    manual, regressão futura), sobrar um valor a pagar para alguém sem cadastro formal. Cadastrar
    o colaborador (ou reduzir o valor a zero) é o único jeito de destravar."""
    offenders = [
        score
        for score in run.scores
        if score.collaborator and not score.collaborator.is_registered and float(score.estimated_payment) > 0
    ]
    if offenders:
        names = ", ".join(sorted({score.collaborator.name for score in offenders}))
        raise HTTPException(
            status_code=409,
            detail=(
                f"{len(offenders)} colaborador(es) não cadastrado(s) ainda têm valor a pagar neste fechamento "
                f"({names}). Cadastre-os na aba Configuração antes de marcar como pago - eles não podem ser "
                "pagos sem cadastro formal."
            ),
        )


def update_run_status(db: Session, run: CalculationRun, next_status: str, user: User, note: str | None = None) -> CalculationRun:
    current_status = normalize_run_status(run.status)
    target_status = normalize_run_status(next_status)
    ensure_status_transition_allowed(current_status, target_status)
    ensure_status_change_permission(user, target_status)
    if target_status == "paid":
        ensure_no_overlapping_paid_period(db, run)
        ensure_no_unregistered_payable_collaborators(run)

    changed_at = now_utc()
    run.status = target_status
    run.status_changed_at = changed_at
    run.status_changed_by = user.id
    run.status_note = note.strip() if note else None

    if target_status == "approved":
        run.approved_at = changed_at
        run.approved_by = user.id
    if target_status == "paid":
        run.paid_at = changed_at
        run.paid_by = user.id

    return run


def build_rule_snapshot(db: Session) -> dict[str, Any]:
    from app.services.gamification_config import serialize_current_config

    config = serialize_current_config(db)
    role_profiles = list(
        db.scalars(
            select(LeadershipRoleProfile)
            .options(selectinload(LeadershipRoleProfile.leaders))
            .order_by(LeadershipRoleProfile.name.asc())
        )
    )
    leadership_profiles = list(
        db.scalars(
            select(LeadershipProfile)
            .options(selectinload(LeadershipProfile.role_profile), selectinload(LeadershipProfile.regionals))
            .order_by(LeadershipProfile.role_type.asc(), LeadershipProfile.name.asc())
        )
    )

    return snapshot(
        {
            "captured_at": now_utc(),
            "config": config,
            "leadership_role_profiles": [serialize_role_profile(profile) for profile in role_profiles],
            "leadership_profiles": [serialize_profile(profile) for profile in leadership_profiles],
        }
    )


def find_paid_run_for_period(
    db: Session,
    reference_month: int,
    reference_year: int,
    regional: str | None,
) -> CalculationRun | None:
    stmt = (
        select(CalculationRun)
        .where(CalculationRun.reference_month == reference_month)
        .where(CalculationRun.reference_year == reference_year)
        .where(CalculationRun.status == "paid")
    )
    if regional is None:
        stmt = stmt.where(CalculationRun.regional.is_(None))
    else:
        stmt = stmt.where(CalculationRun.regional == regional)
    return db.scalar(stmt.order_by(desc(CalculationRun.created_at), desc(CalculationRun.id)).limit(1))


def find_paid_run_for_service_order_context(
    db: Session,
    reference_date: datetime | None,
    regional: str | None,
) -> CalculationRun | None:
    if reference_date is None:
        return None
    normalized_regional = normalize_regional(regional) if regional else None
    direct = find_paid_run_for_period(db, reference_date.month, reference_date.year, normalized_regional)
    if direct:
        return direct
    if normalized_regional is not None:
        return find_paid_run_for_period(db, reference_date.month, reference_date.year, None)
    return None


def find_run_for_period(
    db: Session,
    reference_month: int,
    reference_year: int,
    regional: str | None,
) -> CalculationRun | None:
    """Igual a `find_paid_run_for_period`, mas sem filtrar por status - usado quando o período já
    está encerrado por ter virado o mês (ver `is_period_in_the_past`) mas ainda não foi pago, e
    precisamos de alguma apuração (rascunho, em conferência, aprovada) para referenciar no motivo
    do lançamento de saldo e, se existir, herdar a régua congelada (`config_snapshot`)."""
    stmt = (
        select(CalculationRun)
        .where(CalculationRun.reference_month == reference_month)
        .where(CalculationRun.reference_year == reference_year)
    )
    if regional is None:
        stmt = stmt.where(CalculationRun.regional.is_(None))
    else:
        stmt = stmt.where(CalculationRun.regional == regional)
    return db.scalar(stmt.order_by(desc(CalculationRun.created_at), desc(CalculationRun.id)).limit(1))


def find_run_for_service_order_context(
    db: Session,
    reference_date: datetime | None,
    regional: str | None,
) -> CalculationRun | None:
    if reference_date is None:
        return None
    normalized_regional = normalize_regional(regional) if regional else None
    direct = find_run_for_period(db, reference_date.month, reference_date.year, normalized_regional)
    if direct:
        return direct
    if normalized_regional is not None:
        return find_run_for_period(db, reference_date.month, reference_date.year, None)
    return None


def pick_run_by_status_priority(db: Session, base_stmt) -> CalculationRun | None:
    """Escolhe entre os runs que casam com `base_stmt` priorizando (1) pago, (2) qualquer um nao
    cancelado, (3) qualquer um - sempre o mais recente dentro de cada nivel. Sem essa prioridade,
    quem busca "o fechamento deste periodo" so por `order_by(created_at desc)` acha o registro
    mais recente independente do status - criar (e depois cancelar) uma revisao explicita DEPOIS
    de um fechamento pago fazia essa revisao cancelada "vencer" so por ser mais nova, escondendo
    o pagamento real ja fechado (achado real, ver reconciliacao de julho/2026)."""
    for status_filter in (CalculationRun.status == "paid", CalculationRun.status != "cancelled", None):
        stmt = base_stmt.where(status_filter) if status_filter is not None else base_stmt
        run = db.scalar(stmt.order_by(desc(CalculationRun.created_at), desc(CalculationRun.id)).limit(1))
        if run:
            return run
    return None


def ensure_period_not_closed(
    db: Session,
    reference_month: int,
    reference_year: int,
    regional: str | None,
    allow_revision: bool = False,
) -> CalculationRun | None:
    """Bloqueia recalcular um período que já "encerrou" para fins de pontuação - seja porque foi
    marcado como pago, seja porque o mês corrente (fuso de Porto Velho, ver `is_period_in_the_past`)
    já virou para o período seguinte. Sem o segundo caso, um rascunho de um mês que já passou (mas
    que ninguém marcou como pago ainda) continuava mutável indefinidamente: uma reincidência
    descoberta dias depois do fechamento do mês mudava um total que o dono do produto já considerava
    decidido (achado real - ver docs/plano-integracao-ixc.md). Uma revisão explícita
    (`allow_revision=True`) sempre pode passar por cima disso, igual já acontecia para período pago -
    é o mesmo `create_revision` que a tela já expõe."""
    db.flush()
    paid_run = find_paid_run_for_period(db, reference_month, reference_year, regional)
    if paid_run:
        if not allow_revision:
            raise HTTPException(
                status_code=409,
                detail="Este período já está marcado como pago. Para revisar, crie uma nova revisão em rascunho sem alterar o fechamento pago original.",
            )
        return paid_run

    if is_period_in_the_past(reference_month, reference_year) and not allow_revision:
        raise HTTPException(
            status_code=409,
            detail=(
                f"O período {reference_month:02d}/{reference_year} não é mais o mês corrente "
                "(horário de Porto Velho) e é tratado como encerrado para fins de pontuação, mesmo sem "
                "ter sido marcado como pago. Reincidências encontradas contra ele agora entram no saldo "
                "de pontos do próximo fechamento em vez de mudar este total. Para recalcular mesmo assim, "
                "refaça como uma revisão explícita."
            ),
        )
    return None
