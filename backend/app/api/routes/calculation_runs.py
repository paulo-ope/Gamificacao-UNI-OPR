from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.core.performance import performance_step
from app.core.security import require_permission
from app.db.session import get_db
from app.models import CalculationRun, CollaboratorScore, User
from app.schemas import (
    CalculationRequest,
    CalculationRunHistoryOut,
    CalculationRunOut,
    CalculationRunSnapshotOut,
    CalculationRunStatusUpdate,
)
from app.services import point_balance
from app.services.calculation import (
    calculate_scores,
    latest_run,
    recompute_run_totals_from_scores,
    refresh_run_breakdowns,
    serialize_run,
)
from app.services.audit_log import record_audit_log
from app.services.calculation_closure import serialize_run_status, update_run_status
from app.services.leadership_bonus import calculate_and_store_leadership_bonus

router = APIRouter(prefix="/calculation-runs", tags=["calculation-runs"])


def _serialize_history_run(run: CalculationRun) -> CalculationRunHistoryOut:
    scores = list(run.scores)
    top_score = max(scores, key=lambda score: float(score.final_points), default=None)
    return CalculationRunHistoryOut(
        id=run.id,
        reference_month=run.reference_month,
        reference_year=run.reference_year,
        regional=run.regional,
        point_value=float(run.point_value),
        source_import_id=run.source_import_id,
        source_filename=run.source_filename,
        rules_version_id=run.rules_version_id,
        created_at=run.created_at,
        **serialize_run_status(run),
        collaborators_count=len(scores),
        service_orders_count=sum(int(score.service_orders_count) for score in scores),
        gross_points=round(sum(float(score.gross_points) for score in scores), 2),
        penalty_points=round(sum(float(score.penalty_points) for score in scores), 2),
        net_points=round(sum(float(score.net_points) for score in scores), 2),
        final_points=round(sum(float(score.final_points) for score in scores), 2),
        estimated_payment=round(sum(float(score.estimated_payment) for score in scores), 2),
        top_collaborator_name=top_score.collaborator.name if top_score and top_score.collaborator else None,
        top_collaborator_points=round(float(top_score.final_points), 2) if top_score else None,
    )


@router.get("", response_model=list[CalculationRunHistoryOut])
def list_calculation_runs(
    limit: int = 24,
    include_empty: bool = False,
    reference_month: int | None = None,
    reference_year: int | None = None,
    regional: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard:read")),
):
    stmt = (
        select(CalculationRun)
        .options(selectinload(CalculationRun.scores).selectinload(CollaboratorScore.collaborator))
        .order_by(desc(CalculationRun.created_at), desc(CalculationRun.id))
        .limit(100)
    )
    if reference_month is not None:
        stmt = stmt.where(CalculationRun.reference_month == reference_month)
    if reference_year is not None:
        stmt = stmt.where(CalculationRun.reference_year == reference_year)
    if regional is not None:
        if regional == "":
            stmt = stmt.where(CalculationRun.regional.is_(None))
        else:
            stmt = stmt.where(CalculationRun.regional == regional)
    if status:
        stmt = stmt.where(CalculationRun.status == status.strip().lower())
    runs = db.scalars(stmt).all()
    history = [_serialize_history_run(run) for run in runs]
    if not include_empty:
        history = [run for run in history if run.service_orders_count > 0]
    return history[: min(max(limit, 1), 100)]


@router.post("/calculate", response_model=CalculationRunOut)
def calculate(
    payload: CalculationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("calculation:run")),
):
    if payload.reference_month is None or payload.reference_year is None:
        raise HTTPException(status_code=422, detail="Informe explicitamente o mes e o ano de referencia antes de recalcular.")
    try:
        with performance_step("calculation-runs.calculate", "calculate_scores"):
            run = calculate_scores(
                db,
                reference_month=payload.reference_month,
                reference_year=payload.reference_year,
                regional=payload.regional,
                point_value=payload.point_value,
                executed_by=user.id,
                allow_paid_revision=payload.create_revision,
                execution_note=payload.execution_note,
            )
        with performance_step("calculation-runs.calculate", "leadership_bonus"):
            calculate_and_store_leadership_bonus(db, run)
        with performance_step("calculation-runs.calculate", "audit_log"):
            record_audit_log(db, user, "run", "calculation_runs", run.id, None, payload)
        with performance_step("calculation-runs.calculate", "commit"):
            db.commit()
        with performance_step("calculation-runs.calculate", "serialize"):
            return serialize_run(run, db)
    except Exception:
        db.rollback()
        raise


@router.get("/latest", response_model=CalculationRunOut | None)
def get_latest_run(db: Session = Depends(get_db), user: User = Depends(require_permission("dashboard:read"))):
    return serialize_run(latest_run(db), db)


@router.get("/{run_id}", response_model=CalculationRunOut)
def get_calculation_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard:read")),
):
    run = db.scalar(
        select(CalculationRun)
        .where(CalculationRun.id == run_id)
        .options(selectinload(CalculationRun.scores).selectinload(CollaboratorScore.collaborator))
    )
    if not run:
        raise HTTPException(status_code=404, detail="Fechamento não encontrado.")
    payload = serialize_run(run, db)
    if payload is not None:
        payload["config_snapshot"] = run.config_snapshot
    return payload


@router.get("/{run_id}/snapshot", response_model=CalculationRunSnapshotOut)
def get_calculation_run_snapshot(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("dashboard:read")),
):
    run = db.get(CalculationRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Fechamento não encontrado.")
    return CalculationRunSnapshotOut(id=run.id, config_snapshot=run.config_snapshot)


def _apply_point_balance_after_payment(db: Session, run: CalculationRun, user: User) -> bool:
    """Consome os lancamentos de saldo pendentes de cada colaborador do run, so deve ser chamada
    apos o run efetivamente transicionar para status="paid". Retorna True se algum colaborador
    teve pontos ajustados (sinal para recalcular o bonus de lideranca)."""
    score_summaries = run.result_summary.get("score_summaries") if isinstance(run.result_summary, dict) else None
    adjusted = False

    for score in run.scores:
        cached = (score_summaries or {}).get(str(score.collaborator_id), {})
        gross_final_points = float(
            cached.get("gross_final_points", round(float(score.net_points) * float(score.health_multiplier), 2))
        )
        if "gross_estimated_payment" in cached:
            gross_estimated_payment = float(cached["gross_estimated_payment"])
        elif not float(score.balance_adjustment_points or 0):
            # Sem ajuste de saldo no rascunho, o estimated_payment gravado ja e o bruto.
            gross_estimated_payment = float(score.estimated_payment)
        else:
            # Run antigo sem cache bruto e com ajuste aplicado: reconstruir pelo valor do ponto do run.
            gross_estimated_payment = round(gross_final_points * float(run.point_value), 2)

        result = point_balance.apply_pending_entries_for_paid_run(
            db,
            collaborator=score.collaborator,
            calculation_run=run,
            reference_month=run.reference_month,
            reference_year=run.reference_year,
            available_points=gross_final_points,
            user=user,
        )

        # Sempre recompor a partir do BRUTO, mesmo quando nada foi consumido (applied_points == 0):
        # a previa do rascunho pode ter gravado um valor reduzido por um debito que foi estornado
        # depois - neste caso o pagamento precisa devolver os pontos ao colaborador.
        effective_rate = (gross_estimated_payment / gross_final_points) if gross_final_points else float(run.point_value)
        new_final_points = round(max(float(result["balance_after"]), 0.0), 2)
        new_estimated_payment = round(new_final_points * effective_rate, 2)
        # Garantia explicita (independente da aritmetica acima): colaborador nao cadastrado nunca
        # sai daqui com valor a pagar, mesmo no recomputo oficial feito ao marcar como pago.
        if not score.collaborator.is_registered:
            new_estimated_payment = 0.0

        if (
            float(score.final_points) != new_final_points
            or float(score.estimated_payment) != new_estimated_payment
            or float(score.balance_adjustment_points) != float(result["applied_points"])
        ):
            adjusted = True

        score.balance_adjustment_points = float(result["applied_points"])
        score.balance_after = float(result["balance_after"])
        score.final_points = new_final_points
        score.estimated_payment = new_estimated_payment

        if score_summaries is not None and str(score.collaborator_id) in score_summaries:
            cached_summary = score_summaries[str(score.collaborator_id)]
            cached_summary["balance_adjustment_points"] = score.balance_adjustment_points
            cached_summary["balance_after"] = score.balance_after
            cached_summary["final_points"] = score.final_points
            cached_summary["estimated_payment"] = score.estimated_payment

    # `flag_modified` FORA do `if adjusted` (achado C1): as escritas no cache acima acontecem
    # sempre, mas o SQLAlchemy nao detecta mutacao in-place de coluna JSON. Quando nada mudou nas
    # linhas (`adjusted == False`), essas escritas eram descartadas em silencio e a divergencia
    # entre cache e linha sobrevivia ao pagamento - foi assim que o #1601 ficou com R$ 80,50 de
    # diferenca entre a tela e o extrato do colaborador.
    if score_summaries is not None:
        flag_modified(run, "result_summary")
    recompute_run_totals_from_scores(run)

    return adjusted


def _refresh_stale_draft_previews(db: Session, collaborator_ids: set[int], exclude_run_id: int) -> None:
    """Depois que um debito de garantia e efetivamente consumido por um fechamento que acabou
    de virar 'paid', qualquer OUTRO rascunho/revisao (draft/review/approved) desses mesmos
    colaboradores que tenha pre-visualizado o MESMO debito antes dele ser consumido fica com um
    valor fantasma: o desconto nao existe mais, mas aquele rascunho nunca foi recalculado.

    Isso nao chega a pagar errado (o pagamento sempre recompoe do bruto ao ser marcado como
    pago - ver _apply_point_balance_after_payment), mas mostra um "Desconto de garantia" que
    nao e mais real para quem esta conferindo o rascunho antes de aprovar. Aqui so atualizamos
    os campos de exibicao (balance_adjustment_points/final_points/estimated_payment) desses
    rascunhos para refletir o estado atual do ledger - sem consumir nada."""
    if not collaborator_ids:
        return

    # Carrega SO as linhas que podem mudar (colaborador afetado + previa de saldo diferente de
    # zero), nunca os fechamentos inteiros com todos os scores. Achado A2 da auditoria
    # 2026-08-26: a versao anterior selecionava todos os rascunhos do sistema com
    # `selectinload(scores)` - com 1.100 rascunhos acumulados isso carregava ~224 mil linhas em
    # memoria DENTRO da transacao que esta marcando um pagamento (33 segundos medidos no
    # fechamento #1601). Com este recorte sao ~26 mil linhas, e a maior parte do problema so
    # desaparece de vez com a politica de retencao de rascunhos.
    stale_rows = list(
        db.execute(
            select(CollaboratorScore, CalculationRun)
            .join(CalculationRun, CalculationRun.id == CollaboratorScore.calculation_run_id)
            .where(CalculationRun.status.in_(["draft", "review", "approved"]))
            .where(CalculationRun.id != exclude_run_id)
            .where(CollaboratorScore.collaborator_id.in_(collaborator_ids))
            .where(CollaboratorScore.balance_adjustment_points != 0)
            .options(selectinload(CollaboratorScore.collaborator))
        ).all()
    )
    if not stale_rows:
        return

    scores_by_run: dict[int, tuple[CalculationRun, list[CollaboratorScore]]] = {}
    for score, stale_run in stale_rows:
        scores_by_run.setdefault(stale_run.id, (stale_run, []))[1].append(score)

    pending_entries_by_collaborator = point_balance.pending_entries_by_collaborator_batch(db, list(collaborator_ids))

    for stale_run, scores in scores_by_run.values():
        score_summaries = stale_run.result_summary.get("score_summaries") if isinstance(stale_run.result_summary, dict) else None
        changed = False
        # Totais atualizados por DELTA: recalcular somando `stale_run.scores` obrigaria a carregar
        # todas as linhas de cada rascunho - exatamente o custo que este recorte evita.
        final_points_delta = 0.0
        estimated_payment_delta = 0.0
        for score in scores:
            cached = (score_summaries or {}).get(str(score.collaborator_id), {})
            gross_final_points = float(
                cached.get("gross_final_points", round(float(score.net_points) * float(score.health_multiplier), 2))
            )
            gross_estimated_payment = (
                float(cached["gross_estimated_payment"])
                if "gross_estimated_payment" in cached
                else round(gross_final_points * float(stale_run.point_value), 2)
            )
            preview = point_balance.preview_pending_adjustment(
                db,
                score.collaborator_id,
                gross_final_points,
                pending=pending_entries_by_collaborator.get(score.collaborator_id, []),
            )
            effective_rate = (gross_estimated_payment / gross_final_points) if gross_final_points else float(stale_run.point_value)
            new_final_points = round(max(float(preview["projected_balance"]), 0.0), 2)
            new_estimated_payment = round(new_final_points * effective_rate, 2)
            if not score.collaborator.is_registered:
                new_estimated_payment = 0.0

            final_points_delta += new_final_points - float(score.final_points)
            estimated_payment_delta += new_estimated_payment - float(score.estimated_payment)

            score.balance_adjustment_points = float(preview["adjustment_points"])
            score.balance_after = float(preview["projected_balance"])
            score.final_points = new_final_points
            score.estimated_payment = new_estimated_payment
            if score_summaries is not None and str(score.collaborator_id) in score_summaries:
                cached_summary = score_summaries[str(score.collaborator_id)]
                cached_summary["balance_adjustment_points"] = score.balance_adjustment_points
                cached_summary["balance_after"] = score.balance_after
                cached_summary["final_points"] = score.final_points
                cached_summary["estimated_payment"] = score.estimated_payment
            changed = True

        if changed and isinstance(stale_run.result_summary, dict):
            updated = dict(stale_run.result_summary)
            updated["final_points"] = round(float(updated.get("final_points") or 0) + final_points_delta, 2)
            updated["estimated_payment"] = round(
                float(updated.get("estimated_payment") or 0) + estimated_payment_delta, 2
            )
            cards = updated.get("cards")
            if isinstance(cards, dict):
                updated_cards = dict(cards)
                if "final_points" in updated_cards:
                    updated_cards["final_points"] = updated["final_points"]
                if "estimated_payment" in updated_cards:
                    updated_cards["estimated_payment"] = updated["estimated_payment"]
                updated["cards"] = updated_cards
            # Achado real de 2026-08-27: este ajuste corrige final_points/estimated_payment por
            # DELTA (evita recarregar o rascunho inteiro), mas nunca tocava em cost_by_regional/
            # cost_by_group/cost_by_subject/cost_by_collaborator - esses detalhamentos ficavam
            # congelados com o valor de ANTES do debito ser consumido, enquanto cards/final_points
            # já refletiam o valor de depois. GET /dashboard/summary detectava a divergência
            # (corretamente) e recomputava tudo do zero a cada carregamento (5-7s medidos, run
            # #1936: R$ 15.073,50 em cache vs R$ 11.967,06 reconciliado). Em vez de tentar
            # redistribuir o delta por regional/grupo/assunto (arriscaria reintroduzir uma versão
            # mais sutil do mesmo bug), invalida o marcador de cache - a rota já sabe recomputar
            # os detalhamentos ao vivo quando ele está ausente.
            updated.pop("dashboard_cache_version", None)
            stale_run.result_summary = updated


@router.patch("/{run_id}/status", response_model=CalculationRunOut)
def change_calculation_run_status(
    run_id: int,
    payload: CalculationRunStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("calculation:run")),
):
    # Lock de linha antes de qualquer leitura de status: sem ele, dois cliques (ou dois
    # operadores) leem `approved` ao mesmo tempo, os dois passam pela validacao de transicao e os
    # dois consomem o ledger de saldo. A janela nao e teorica - no fechamento #1601 passaram-se
    # 33 segundos entre o inicio da transicao e o commit (achado C5 da auditoria 2026-08-26).
    # O dialeto SQLite (usado nos testes) simplesmente ignora o FOR UPDATE.
    locked_run_id = db.scalar(select(CalculationRun.id).where(CalculationRun.id == run_id).with_for_update())
    if locked_run_id is None:
        raise HTTPException(status_code=404, detail="Fechamento não encontrado.")
    run = db.scalar(
        select(CalculationRun)
        .where(CalculationRun.id == run_id)
        .options(selectinload(CalculationRun.scores).selectinload(CollaboratorScore.collaborator))
    )
    if not run:
        raise HTTPException(status_code=404, detail="Fechamento não encontrado.")
    before = serialize_run(run, db)
    previous_status = run.status
    update_run_status(db, run, payload.status, user, payload.note)
    if run.status == "paid" and previous_status != "paid":
        _apply_point_balance_after_payment(db, run, user)
        # Os detalhamentos (`cost_by_*`, distribuicao de penalidade, saude por regional) ficavam
        # congelados com a previa do rascunho mesmo depois do pagamento recompor os valores -
        # a mesma tela mostrava "Total a pagar" corrigido e "por regional" desatualizado (C1).
        # O bonus roda depois pra somar sobre a base ja atualizada; agora e idempotente (C2).
        refresh_run_breakdowns(db, run)
        calculate_and_store_leadership_bonus(db, run)
        _refresh_stale_draft_previews(db, {score.collaborator_id for score in run.scores}, exclude_run_id=run.id)
    record_audit_log(db, user, "update_status", "calculation_runs", run.id, before, {"status": run.status, "note": payload.note})
    db.commit()
    db.refresh(run)
    return serialize_run(run, db)
