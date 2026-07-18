from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import (
    CalculationRun,
    Collaborator,
    CollaboratorPointBalance,
    PointBalanceEntry,
    ServiceOrder,
    User,
)
from app.services import scoring_detail
from app.services.audit_log import record_audit_log, snapshot
from app.services.calculation_closure import (
    find_paid_run_for_service_order_context,
    find_run_for_service_order_context,
    is_period_in_the_past,
    now_utc,
)
from app.services.scoring_matrix import real_service_orders


def _order_date(order: ServiceOrder):
    return order.closed_at or order.opened_at


def _order_points_from_snapshot(order: ServiceOrder, config_snapshot: dict[str, Any] | None) -> float | None:
    """Recalcula os pontos de `order` usando a regua congelada num config_snapshot de CalculationRun.

    Retorna None se o snapshot nao existir (runs antigos, antes deste campo), para o chamador decidir o fallback.
    """
    if not config_snapshot:
        return None
    config = config_snapshot.get("config") or {}
    subject_rules = config.get("scoring_subject_rules") or []
    groups_by_id = {group["id"]: group for group in config.get("scoring_groups") or []}

    os_type = scoring_detail.normalize(order.os_type)
    os_subject = scoring_detail.normalize(order.os_subject)

    active_rules = [
        rule
        for rule in subject_rules
        if rule.get("active") and groups_by_id.get(rule.get("group_id"), {}).get("active")
    ]

    matched_rule = next(
        (
            rule
            for rule in active_rules
            if scoring_detail.normalize(rule.get("os_type")) == os_type
            and scoring_detail.normalize(rule.get("os_subject")) == os_subject
        ),
        None,
    )
    if matched_rule is None:
        subject_matches = [rule for rule in active_rules if scoring_detail.normalize(rule.get("os_subject")) == os_subject]
        if len(subject_matches) == 1:
            matched_rule = subject_matches[0]

    if matched_rule is None:
        return 0.0

    group = groups_by_id.get(matched_rule.get("group_id"))
    if not group:
        return 0.0
    if not matched_rule.get("use_group_default") and matched_rule.get("custom_points") is not None:
        return float(matched_rule["custom_points"])
    return float(group.get("default_points") or 0)


def serialize_entry(entry: PointBalanceEntry, collaborator_name: str | None = None) -> dict[str, Any]:
    resolved_name = collaborator_name if collaborator_name is not None else (entry.collaborator.name if entry.collaborator else None)
    origin_run = entry.origin_calculation_run
    applied_run = entry.applied_calculation_run
    return {
        "id": entry.id,
        "collaborator_id": entry.collaborator_id,
        "collaborator_name": resolved_name,
        "entry_type": entry.entry_type,
        "points": entry.points,
        "original_service_order_id": entry.original_service_order_id,
        "original_os_code": entry.original_service_order.os_code if entry.original_service_order else None,
        "related_service_order_id": entry.related_service_order_id,
        "related_os_code": entry.related_service_order.os_code if entry.related_service_order else None,
        "origin_calculation_run_id": entry.origin_calculation_run_id,
        "origin_run_month": origin_run.reference_month if origin_run else None,
        "origin_run_year": origin_run.reference_year if origin_run else None,
        "origin_run_status": origin_run.status if origin_run else None,
        "applied_calculation_run_id": entry.applied_calculation_run_id,
        "applied_run_status": applied_run.status if applied_run else None,
        "applied_reference_month": entry.applied_reference_month,
        "applied_reference_year": entry.applied_reference_year,
        "status": entry.status,
        "requires_review": entry.requires_review,
        "recurrence_classification": entry.recurrence_classification,
        "recurrence_action": entry.recurrence_action,
        "reason": entry.reason,
        "created_by": entry.created_by,
        "created_at": entry.created_at,
    }


def _existing_entry(db: Session, original: ServiceOrder, later: ServiceOrder) -> PointBalanceEntry | None:
    # Casa pelo par de ids (caminho normal) OU pelo par de os_code (sobrevive a um periodo ter sido
    # apagado e reimportado, quando a O.S ganha um id novo mas o os_code continua o mesmo) - sem isso,
    # reimportar um periodo apagado duplicaria o debito de garantia do mesmo evento real.
    return db.scalar(
        select(PointBalanceEntry).where(
            or_(
                and_(
                    PointBalanceEntry.original_service_order_id == original.id,
                    PointBalanceEntry.related_service_order_id == later.id,
                ),
                and_(
                    PointBalanceEntry.original_os_code == original.os_code,
                    PointBalanceEntry.related_os_code == later.os_code,
                ),
            )
        )
    )


def detect_post_payment_warranty_debits(
    db: Session,
    candidate_orders: list[ServiceOrder],
    triggered_by: int | None = None,
) -> list[PointBalanceEntry]:
    """Detecta garantias/reincidencias tecnicas cuja O.S original ja pertence a um periodo encerrado.

    `candidate_orders` sao as O.S "posteriores" a considerar (recem importadas, ou o periodo sendo
    calculado). Um periodo e considerado "encerrado" quando esta pago OU quando o mes corrente (fuso
    de Porto Velho, ver `is_period_in_the_past`) ja virou para o periodo seguinte - mesmo sem ninguem
    ter marcado como pago ainda. Sem o segundo caso, o rascunho de um mes que ja passou continuava
    mutavel indefinidamente ate alguem lembrar de pagar, e uma reincidencia descoberta nesse meio tempo
    mudava um total que o dono do produto ja considerava decidido (achado real - ver
    docs/plano-integracao-ixc.md). Caso contrario (periodo original ainda e o mes corrente e nao esta
    pago), o mecanismo existente (scoring_detail.recurrence_penalties) resolve normalmente quando aquele
    periodo for calculado, pois a O.S posterior ja vai existir no banco.
    """
    later_orders = [order for order in candidate_orders if scoring_detail.completed(order)]
    if not later_orders:
        return []

    action = scoring_detail.get_setting(db, "recurrence_action", "annul_original")
    normalized_action = scoring_detail.normalize(action)
    window_days = int(scoring_detail._safe_float(scoring_detail.get_setting(db, "recurrence_window_days", "30"), 30))
    configured_points = scoring_detail._safe_float(scoring_detail.get_setting(db, "recurrence_penalty_points", "0"), 0)
    identity_fields = scoring_detail._configured_recurrence_identity_fields(db)
    rules = scoring_detail.active_recurrence_classification_rules(db)
    search_window_days = max([window_days, *[int(rule.max_days) for rule in rules if rule.max_days is not None]])
    active_rules_lookup = scoring_detail.build_scoring_rule_lookup(scoring_detail.active_scoring_rules(db))

    later_dates = [(later, _order_date(later)) for later in later_orders]
    later_dates = [(later, date) for later, date in later_dates if date is not None]
    if not later_dates:
        return []

    # Uma unica consulta para o lote inteiro (nao uma por O.S) - closed_at/opened_at nao sao indexados,
    # entao repetir essa consulta por O.S vira uma varredura completa da tabela a cada item do lote.
    batch_search_start = min(date for _, date in later_dates) - timedelta(days=search_window_days)
    batch_search_end = max(date for _, date in later_dates)
    candidates_stmt = select(ServiceOrder).where(
        or_(
            ServiceOrder.closed_at.between(batch_search_start, batch_search_end),
            ServiceOrder.opened_at.between(batch_search_start, batch_search_end),
        )
    )
    candidates_by_identity: dict[str, list[ServiceOrder]] = defaultdict(list)
    for candidate in real_service_orders(list(db.scalars(candidates_stmt))):
        if not scoring_detail.completed(candidate):
            continue
        candidate_identity = scoring_detail._recurrence_identity_for_fields(candidate, identity_fields)
        if candidate_identity:
            candidates_by_identity[candidate_identity].append(candidate)

    created: list[PointBalanceEntry] = []

    for later, later_date in later_dates:
        identity = scoring_detail._recurrence_identity_for_fields(later, identity_fields)
        if not identity:
            continue

        originals = []
        for candidate in candidates_by_identity.get(identity, []):
            if candidate.id == later.id:
                continue
            candidate_date = _order_date(candidate)
            if candidate_date is None or candidate_date > later_date:
                continue
            if (later_date - candidate_date).days > search_window_days:
                continue
            originals.append(candidate)

        if not originals:
            continue

        classifications = []
        for original in originals:
            original_date = _order_date(original)
            days_between = int((later_date - original_date).days)
            classification = scoring_detail.classify_recurrence_pair(
                original,
                later,
                days_between,
                window_days,
                rules,
                identity_label=scoring_detail._recurrence_identity_label_for_fields(original, identity_fields),
            )
            classification["original_order"] = original
            classifications.append(classification)

        discount_candidates = [
            item
            for item in classifications
            if item["classification"] in scoring_detail.RECURRENCE_DISCOUNT_CLASSIFICATIONS and bool(item["discount_points"])
        ]
        if not discount_candidates:
            continue

        selected = sorted(discount_candidates, key=lambda item: int(item["days_between"]))[0]
        original = selected["original_order"]
        original_date = _order_date(original)

        paid_run = find_paid_run_for_service_order_context(db, original_date, original.regional)
        period_is_closed = bool(paid_run) or is_period_in_the_past(original_date.month, original_date.year)
        if not period_is_closed:
            # Periodo original ainda e o mes corrente (fuso de Porto Velho) e nao esta pago: o
            # mecanismo normal de recurrence_penalties vai encontrar este par quando aquele periodo
            # for calculado (a O.S posterior ja vai existir).
            continue

        if _existing_entry(db, original, later):
            continue

        if normalized_action in {scoring_detail.normalize("no_penalty"), scoring_detail.normalize("nao_penaliza")}:
            continue

        # Sem fechamento pago (periodo so fechou por ter virado o mes), usa a apuracao mais recente
        # daquele periodo - se existir - so para herdar a regua congelada e compor o motivo do
        # lancamento. Pode nao existir nenhuma (mes nunca calculado) - nesse caso cai no fallback da
        # regua atual, igual ja acontecia para fechamentos pagos sem config_snapshot.
        reference_run = paid_run or find_run_for_service_order_context(db, original_date, original.regional)

        requires_review = False
        points = 0.0
        reason_note = ""
        if normalized_action == scoring_detail.normalize("requires_review"):
            requires_review = True
            reason_note = "exige revisão manual antes de aplicar qualquer desconto"
        elif normalized_action == scoring_detail.normalize("subtract_original"):
            points = -abs(float(configured_points))
            reason_note = f"desconto configurado de {abs(float(configured_points)):g} pontos"
        else:
            snapshot_points = _order_points_from_snapshot(original, reference_run.config_snapshot if reference_run else None)
            if snapshot_points is None:
                snapshot_points = scoring_detail.order_points(original, active_rules_lookup)
                run_descriptor = f"fechamento #{reference_run.id}" if reference_run else "nenhum fechamento calculado"
                reason_note = f"anulação de {snapshot_points:g} pontos (régua atual, {run_descriptor} sem config_snapshot)"
            else:
                reason_note = f"anulação de {snapshot_points:g} pontos (régua vigente no fechamento #{reference_run.id})"
            points = -abs(float(snapshot_points))

        period_label = f"{original_date.month:02d}/{original_date.year}"
        closure_descriptor = (
            f"fechamento pago #{paid_run.id}, {period_label}"
            if paid_run
            else f"período {period_label} já encerrado (mês corrente já virou, horário de Porto Velho)"
        )

        entry = PointBalanceEntry(
            # O debito e sempre do colaborador da O.S ORIGINAL: foi ele quem ganhou os pontos no
            # periodo encerrado que estao sendo estornados. O tecnico da visita de garantia (later)
            # pode ser outra pessoa e nao deve ser penalizado - mesmo criterio de recurrence_penalties,
            # que penaliza a O.S original.
            collaborator_id=original.collaborator_id,
            entry_type="post_payment_warranty_debit",
            points=points,
            original_service_order_id=original.id,
            related_service_order_id=later.id,
            original_os_code=original.os_code,
            related_os_code=later.os_code,
            origin_calculation_run_id=reference_run.id if reference_run else None,
            status="pending",
            requires_review=requires_review,
            recurrence_classification=selected["classification"],
            recurrence_action=normalized_action,
            reason=(
                f"Garantia detectada pela O.S {later.os_code} referente a O.S original {original.os_code} "
                f"({closure_descriptor}): {reason_note}."
            ),
        )
        db.add(entry)
        created.append(entry)

    if not created:
        return created

    db.flush()
    triggering_user = db.get(User, triggered_by) if triggered_by else None
    for entry in created:
        record_audit_log(
            db,
            triggering_user,
            "point_balance_debit_created",
            "point_balance_entry",
            entry.id,
            None,
            snapshot(entry),
        )

    return created


def pending_entries_for_collaborator(db: Session, collaborator_id: int) -> list[PointBalanceEntry]:
    return list(
        db.scalars(
            select(PointBalanceEntry)
            .where(PointBalanceEntry.collaborator_id == collaborator_id, PointBalanceEntry.status == "pending")
            .order_by(PointBalanceEntry.created_at.asc(), PointBalanceEntry.id.asc())
        )
    )


def current_balance(db: Session, collaborator_id: int) -> float:
    """Saldo devedor atual, calculado em tempo real a partir dos lancamentos PENDENTES.

    Nao confia na coluna `CollaboratorPointBalance.balance_points`: ela e escrita apenas
    em `apply_pending_entries_for_paid_run` e fica desatualizada (drift) se um lancamento
    pendente for depois estornado (`revert_entry`) ou se um ajuste manual for criado - nenhum
    desses caminhos atualiza a coluna. Somar os pendentes ao vivo e sempre a fonte da verdade,
    e e exatamente o que `preview_pending_adjustment`/`apply_pending_entries_for_paid_run`
    ja usam para decidir quanto descontar."""
    pending = [entry for entry in pending_entries_for_collaborator(db, collaborator_id) if not entry.requires_review]
    return round(sum(float(entry.points) for entry in pending), 2)


def preview_pending_adjustment(db: Session, collaborator_id: int, available_points: float) -> dict[str, float]:
    """Prévia (não muta nada) do efeito dos lançamentos pendentes - usada para exibir em rascunhos."""
    pending = [entry for entry in pending_entries_for_collaborator(db, collaborator_id) if not entry.requires_review]
    total_debit = round(sum(float(entry.points) for entry in pending), 2)
    projected_balance = round(float(available_points) + total_debit, 2)
    return {"adjustment_points": total_debit, "projected_balance": projected_balance}


def apply_pending_entries_for_paid_run(
    db: Session,
    collaborator: Collaborator,
    calculation_run: CalculationRun,
    reference_month: int,
    reference_year: int,
    available_points: float,
    user: User | None = None,
) -> dict[str, Any]:
    """Consome os lancamentos pendentes do colaborador. So deve ser chamada quando `calculation_run`
    efetivamente transiciona para status="paid" - nunca durante um calculo em rascunho, para nao
    consumir o lancamento num draft descartavel que nunca chega a ser aprovado."""
    pending = [entry for entry in pending_entries_for_collaborator(db, collaborator.id) if not entry.requires_review]
    if not pending:
        return {"applied_points": 0.0, "balance_after": round(float(available_points), 2), "entry_ids": []}

    total_debit = round(sum(float(entry.points) for entry in pending), 2)
    new_total = round(float(available_points) + total_debit, 2)

    for entry in pending:
        entry.status = "applied"
        entry.applied_calculation_run_id = calculation_run.id
        entry.applied_reference_month = reference_month
        entry.applied_reference_year = reference_year

    balance_row = db.scalar(
        select(CollaboratorPointBalance).where(CollaboratorPointBalance.collaborator_id == collaborator.id)
    )
    if balance_row is None:
        balance_row = CollaboratorPointBalance(collaborator_id=collaborator.id, balance_points=0)
        db.add(balance_row)

    carry_over_entry: PointBalanceEntry | None = None
    if new_total < 0:
        carry_over_entry = PointBalanceEntry(
            collaborator_id=collaborator.id,
            entry_type="period_settlement",
            points=new_total,
            status="pending",
            reason=(
                f"Saldo remanescente após aplicar débitos no fechamento #{calculation_run.id} "
                f"({reference_month:02d}/{reference_year}): {new_total:g} pontos a compensar no próximo período."
            ),
        )
        db.add(carry_over_entry)
        balance_row.balance_points = new_total
    else:
        balance_row.balance_points = 0.0
    balance_row.updated_at = now_utc()

    db.flush()

    record_audit_log(
        db,
        user,
        "point_balance_debit_applied",
        "collaborator_scores",
        collaborator.id,
        {"balance_before": round(float(available_points), 2)},
        {"balance_after": new_total, "applied_points": total_debit, "entry_ids": [entry.id for entry in pending]},
    )
    if carry_over_entry is not None:
        record_audit_log(
            db,
            user,
            "point_balance_carry_over",
            "collaborator_scores",
            collaborator.id,
            None,
            {"carry_over_points": new_total, "entry_id": carry_over_entry.id},
        )

    return {"applied_points": total_debit, "balance_after": new_total, "entry_ids": [entry.id for entry in pending]}


def create_manual_adjustment(
    db: Session,
    collaborator_id: int,
    points: float,
    reason: str,
    user: User | None = None,
) -> PointBalanceEntry:
    """Cria um ajuste manual no saldo do colaborador (crédito positivo ou débito negativo).
    Fica pendente e é consumido no próximo fechamento pago, como qualquer lançamento."""
    collaborator = db.get(Collaborator, collaborator_id)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")
    if not reason or not reason.strip():
        raise HTTPException(status_code=422, detail="Informe o motivo do ajuste manual.")
    if points == 0:
        raise HTTPException(status_code=422, detail="O ajuste manual deve ter pontos diferentes de zero.")

    entry = PointBalanceEntry(
        collaborator_id=collaborator_id,
        entry_type="manual_adjustment",
        points=round(float(points), 2),
        status="pending",
        requires_review=False,
        reason=f"Ajuste manual: {reason.strip()}",
        created_by=user.id if user else None,
    )
    db.add(entry)
    db.flush()
    record_audit_log(
        db,
        user,
        "point_balance_manual_adjustment",
        "point_balance_entry",
        entry.id,
        None,
        snapshot(entry),
    )
    return entry


def resolve_review_entry(
    db: Session,
    entry_id: int,
    points: float,
    user: User | None = None,
    note: str | None = None,
) -> PointBalanceEntry:
    """Resolve um lançamento que ficou pendente de revisão manual (recurrence_action=
    requires_review), definindo o valor do débito de verdade. Sem isto, uma garantia
    marcada para revisão ficava com points=0 para sempre - só podia ser estornada
    (descartada), nunca efetivamente confirmada com um valor."""
    entry = db.get(PointBalanceEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Lançamento de saldo não encontrado.")
    if not entry.requires_review:
        raise HTTPException(status_code=409, detail="Este lançamento não está pendente de revisão manual.")
    if entry.status != "pending":
        raise HTTPException(status_code=409, detail="Somente lançamentos pendentes podem ser resolvidos.")
    if points >= 0:
        raise HTTPException(status_code=422, detail="O valor resolvido deve ser um débito (número negativo).")

    before = snapshot(entry)
    entry.points = round(float(points), 2)
    entry.requires_review = False
    note_text = f"Revisão manual resolvida: {note.strip()}" if note and note.strip() else "Revisão manual resolvida."
    entry.reason = f"{entry.reason}\n{note_text}" if entry.reason else note_text
    db.flush()
    record_audit_log(db, user, "point_balance_review_resolved", "point_balance_entry", entry.id, before, snapshot(entry))
    return entry


def revert_entry(db: Session, entry_id: int, user: User | None = None, reason: str | None = None) -> PointBalanceEntry:
    entry = db.get(PointBalanceEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Lançamento de saldo não encontrado.")
    if entry.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=(
                "Somente lançamentos pendentes podem ser estornados. Um lançamento já aplicado a um fechamento "
                "pago exige um ajuste manual (manual_adjustment) para compensar, em vez de estorno retroativo."
            ),
        )

    before = snapshot(entry)
    entry.status = "reverted"
    entry.reason = f"{entry.reason}\nEstornado: {reason}" if entry.reason and reason else (reason or entry.reason)
    db.flush()
    record_audit_log(db, user, "point_balance_debit_reverted", "point_balance_entry", entry.id, before, snapshot(entry))
    return entry
