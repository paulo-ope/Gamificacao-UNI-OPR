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
    CollaboratorScore,
    PointBalanceEntry,
    ServiceOrder,
    User,
)
from app.services import scoring_detail
from app.services.audit_log import record_audit_log, snapshot
from app.services.calculation_closure import (
    current_reference_period,
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
        "target_reference_month": entry.target_reference_month,
        "target_reference_year": entry.target_reference_year,
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


def _original_already_debited(db: Session, original: ServiceOrder) -> bool:
    """Uma O.S original so pode ser debitada UMA vez por este mecanismo, nao importa quantos
    retornos de garantia distintos aparecam depois - achado real: um cliente com problema
    cronico (varias visitas ao longo de meses) fazia CADA visita nova gerar um novo debito
    contra a MESMA O.S original (uma chegou a 12 debitos, -72 pontos so dela)."""
    return (
        db.scalar(
            select(PointBalanceEntry.id)
            .where(
                PointBalanceEntry.status != "reverted",
                or_(
                    PointBalanceEntry.original_service_order_id == original.id,
                    PointBalanceEntry.original_os_code == original.os_code,
                ),
            )
            .limit(1)
        )
        is not None
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
    # So a O.S original do mes IMEDIATAMENTE anterior ao mes corrente e elegivel pra esse mecanismo -
    # achado real: uma janela rolante de dias (ex.: 60) podia alcancar 2 meses pra tras dependendo do
    # dia do mes em que a deteccao rodava (ex.: dia 25 de julho alcancava o fim de maio), descontando
    # colaboradores por O.S de um mes que ninguem esperava mais ver mexido.
    current_month, current_year = current_reference_period()
    eligible_month, eligible_year = (
        (12, current_year - 1) if current_month == 1 else (current_month - 1, current_year)
    )
    configured_points = scoring_detail._safe_float(scoring_detail.get_setting(db, "recurrence_penalty_points", "0"), 0)
    # Mesmo criterio da correcao do bonus de CPK (calculation.py: _apply_cpk_adjustment) - se a
    # saude da regional naquele mes ja zerou (ou deixou no piso) o multiplicador do colaborador,
    # a O.S original nunca gerou pagamento de verdade (final_points = net_points * 0 = 0). Cobrar
    # um debito de garantia sobre pontos que a pessoa nunca recebeu penaliza ela por um valor que
    # so existe na regua bruta, nao no que ela de fato ganhou naquele fechamento.
    below_minimum_multiplier = scoring_detail.get_health_below_minimum_multiplier(db)
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
            gap = later_date - original_date
            days_between = int(gap.days)
            classification = scoring_detail.classify_recurrence_pair(
                original,
                later,
                days_between,
                window_days,
                rules,
                identity_label=scoring_detail._recurrence_identity_label_for_fields(original, identity_fields),
                hours_between=gap.total_seconds() / 3600,
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

        original_collaborator = original.collaborator
        if not original_collaborator or not original_collaborator.active or not original_collaborator.is_registered:
            # Achado real: colaborador inativo/nao cadastrado nunca entra num fechamento futuro pra
            # esse debito ser aplicado - ele so ficava acumulando pendente pra sempre, sem efeito
            # nenhum (e virava um passivo "surpresa" se a pessoa fosse cadastrada depois).
            continue

        original_date = _order_date(original)

        paid_run = find_paid_run_for_service_order_context(db, original_date, original.regional)
        period_is_closed = bool(paid_run) or is_period_in_the_past(original_date.month, original_date.year)
        if not period_is_closed:
            # Periodo original ainda e o mes corrente (fuso de Porto Velho) e nao esta pago: o
            # mecanismo normal de recurrence_penalties vai encontrar este par quando aquele periodo
            # for calculado (a O.S posterior ja vai existir).
            continue

        if (original_date.month, original_date.year) != (eligible_month, eligible_year):
            # So o mes imediatamente anterior e elegivel (ver comentario na definicao de
            # eligible_month/eligible_year acima) - qualquer coisa 2+ meses atras nao gera debito novo.
            continue

        if _existing_entry(db, original, later):
            continue

        if _original_already_debited(db, original):
            continue

        if normalized_action in {scoring_detail.normalize("no_penalty"), scoring_detail.normalize("nao_penaliza")}:
            continue

        # Sem fechamento pago (periodo so fechou por ter virado o mes), usa a apuracao mais recente
        # daquele periodo - se existir - so para herdar a regua congelada e compor o motivo do
        # lancamento. Pode nao existir nenhuma (mes nunca calculado) - nesse caso cai no fallback da
        # regua atual, igual ja acontecia para fechamentos pagos sem config_snapshot.
        reference_run = paid_run or find_run_for_service_order_context(db, original_date, original.regional)

        # Multiplicador de saude do colaborador NA ORIGEM (nao no mes em que o debito acaba sendo
        # cobrado) - e o que decide quanto do valor anulado foi de fato recebido de verdade. Uma
        # O.S anulada valia X pontos brutos, mas o colaborador so recebeu X*multiplicador na epoca;
        # estornar o valor bruto cobraria mais do que ele realmente ganhou. Usar o multiplicador do
        # mes da COBRANCA em vez do da origem criaria uma inconsistencia: o mesmo valor recebido de
        # verdade "encolheria" so por coincidencia de quando o sistema conseguiu cobrar (se cair
        # num mes de saude ruim), mesmo a origem tendo sido paga em cheio. Sem score encontrado,
        # mantem o comportamento anterior (multiplicador 1x, sem ajuste).
        origin_health_multiplier = 1.0
        if reference_run is not None:
            original_score = db.scalar(
                select(CollaboratorScore).where(
                    CollaboratorScore.calculation_run_id == reference_run.id,
                    CollaboratorScore.collaborator_id == original.collaborator_id,
                )
            )
            if original_score is not None:
                origin_health_multiplier = float(original_score.health_multiplier)
                if origin_health_multiplier <= below_minimum_multiplier:
                    # Saude zerou o pagamento daquele mes para este colaborador - nao ha nada de
                    # real pra estornar (ver comentario na definicao de below_minimum_multiplier
                    # acima).
                    continue

        if reference_run is not None and later.created_at is not None and later.created_at <= reference_run.created_at:
            # A O.S de retorno ja existia no banco QUANDO o ultimo calculo daquele periodo rodou -
            # o mecanismo normal (recurrence_penalties, que roda toda vez que o periodo e calculado,
            # inclusive em rascunho) ja tinha essa O.S disponivel e ja anulou os pontos direto no
            # total do mes. Gerar TAMBEM um lancamento de saldo aqui duplicaria o desconto (uma vez
            # no total do mes, outra vez no saldo pendente de um pagamento futuro). So prossegue
            # quando a O.S de retorno chegou no banco DEPOIS do ultimo calculo - a razao de existir
            # deste mecanismo (ver docstring da funcao) e cobrir exatamente esse caso: retorno que a
            # apuracao do periodo original nunca teve chance de ver. Achado real: apos o mes corrente
            # virar, 522 de 587 garantias detectadas numa unica passada tinham origem E retorno no
            # mesmo mes (julho), ambas ja importadas semanas antes do ultimo calculo de julho.
            continue

        requires_review = False
        points = 0.0
        reason_note = ""
        if normalized_action == scoring_detail.normalize("requires_review"):
            requires_review = True
            reason_note = "exige revisão manual antes de aplicar qualquer desconto"
        elif normalized_action == scoring_detail.normalize("subtract_original"):
            raw_points = abs(float(configured_points))
            adjusted_points = round(raw_points * origin_health_multiplier, 2)
            points = -adjusted_points
            reason_note = f"desconto configurado de {raw_points:g} pontos"
            if origin_health_multiplier != 1.0:
                reason_note += f", ajustado pelo multiplicador de saúde da origem ({origin_health_multiplier:g}x) para {adjusted_points:g} pontos"
        else:
            snapshot_points = _order_points_from_snapshot(original, reference_run.config_snapshot if reference_run else None)
            if snapshot_points is None:
                snapshot_points = scoring_detail.order_points(original, active_rules_lookup)
                run_descriptor = f"fechamento #{reference_run.id}" if reference_run else "nenhum fechamento calculado"
                reason_note = f"anulação de {snapshot_points:g} pontos (régua atual, {run_descriptor} sem config_snapshot)"
            else:
                reason_note = f"anulação de {snapshot_points:g} pontos (régua vigente no fechamento #{reference_run.id})"
            raw_points = abs(float(snapshot_points))
            adjusted_points = round(raw_points * origin_health_multiplier, 2)
            if origin_health_multiplier != 1.0:
                reason_note += f", ajustado pelo multiplicador de saúde da origem ({origin_health_multiplier:g}x) para {adjusted_points:g} pontos"
            points = -adjusted_points

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
            # Alvo = mes/ano do RETORNO (later), nao da origem - o desconto so pode ser consumido
            # quando o fechamento desse mes (ou de um mes posterior) for pago, mesmo que o mes da
            # origem seja pago antes (ver comentario no model PointBalanceEntry).
            target_reference_month=later_date.month,
            target_reference_year=later_date.year,
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


def pending_entries_by_collaborator_batch(db: Session, collaborator_ids: list[int]) -> dict[int, list[PointBalanceEntry]]:
    """Mesma consulta de `pending_entries_for_collaborator`, mas para vários colaboradores de uma
    só vez - achado real: `calculate_scores` chamava a versão de um colaborador por vez dentro de
    um loop (uma consulta por colaborador do período, ~300+ idas ao banco a cada recálculo), um
    dos maiores gargalos de performance ao recalcular a apuração ou vincular/desvincular acesso
    de portal (que disparava um recálculo completo desnecessariamente - ver page.tsx)."""
    if not collaborator_ids:
        return {}
    entries = list(
        db.scalars(
            select(PointBalanceEntry)
            .where(PointBalanceEntry.collaborator_id.in_(collaborator_ids), PointBalanceEntry.status == "pending")
            .order_by(PointBalanceEntry.created_at.asc(), PointBalanceEntry.id.asc())
        )
    )
    grouped: dict[int, list[PointBalanceEntry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.collaborator_id].append(entry)
    return grouped


def preview_pending_adjustment(
    db: Session,
    collaborator_id: int,
    available_points: float,
    *,
    pending: list[PointBalanceEntry] | None = None,
) -> dict[str, float]:
    """Prévia (não muta nada) do efeito dos lançamentos pendentes - usada para exibir em rascunhos.
    `pending`, se informado (ex.: uma fatia de `pending_entries_by_collaborator_batch`), evita
    rebuscar do banco - quem processa vários colaboradores de uma vez deve buscar em lote."""
    if pending is None:
        pending = pending_entries_for_collaborator(db, collaborator_id)
    pending = [entry for entry in pending if not entry.requires_review]
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
    consumir o lancamento num draft descartavel que nunca chega a ser aprovado.

    Um lancamento com `target_reference_month/year` (post_payment_warranty_debit, alvo = mes do
    RETORNO) so e consumido quando este fechamento e do mes/ano alvo OU de um mes posterior -
    sem isso, o desconto saia do proximo fechamento pago do colaborador em QUALQUER mes, o que
    podia puxar um desconto de garantia de agosto para dentro de um pagamento de julho ainda em
    aberto (achado real). Lancamentos sem alvo (ajuste manual, saldo remanescente) continuam
    sendo consumidos no primeiro pagamento disponivel, como sempre."""
    all_pending = [entry for entry in pending_entries_for_collaborator(db, collaborator.id) if not entry.requires_review]
    pending = [
        entry
        for entry in all_pending
        if entry.target_reference_month is None
        or entry.target_reference_year is None
        or (entry.target_reference_year, entry.target_reference_month) <= (reference_year, reference_month)
    ]
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
