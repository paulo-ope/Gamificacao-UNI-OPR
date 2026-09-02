from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Collaborator, ImportRun, ServiceOrder
from app.modules.operations.models import OperationOrder
from app.modules.operations.period import OPERATIONS_TIMEZONE
from app.modules.operations.scope import PRIMARY_SECTOR_NAMES
from app.services.calculation import get_setting, upsert_setting
from app.services.calculation_closure import find_paid_run_for_service_order_context
from app.services.ixc_importer import (
    IXC_PROVIDED_FIELDS,
    IXC_IMPORT_LOCK_KEY,
    IXC_IMPORT_LOCK_MAX_WAIT_SECONDS,
    IXC_IMPORT_LOCK_POLL_INTERVAL_SECONDS,
    KNOWN_OS_TYPE_BY_SUBJECT,
    PENDING_OS_TYPE,
    IxcImportLockTimeoutError,
    _ixc_import_lock,
    load_historical_os_type_mapping,
    load_subject_rule_os_type_mapping,
)
from app.services.point_balance import detect_post_payment_warranty_debits
from app.services.regional import is_valid_regional, normalize_regional_grouped
from app.services.upvalue_importer import (
    UNKNOWN_VALUE,
    add_import_audit,
    build_import_result,
    find_existing_service_order,
    get_or_create_collaborator,
    normalize_header,
    reference_date_for_payload,
    values_differ,
)

# Marca d'agua da sincronizacao operations_orders -> service_orders, separada da antiga
# `ixc_sync_last_updated_at` (que marcava progresso da busca direta ao IXC, hoje aposentada -
# ver app/services/ixc_scheduler.py). Usa `source_updated_at` (o `ultima_atualizacao` que o
# proprio IXC reporta) como cursor, com fallback para `first_imported_at` quando ausente -
# NAO usa `last_imported_at`: esse campo e tocado pela ingestao (`ixc_ingestion.py`) toda vez
# que a O.S. e re-buscada, mesmo sem nenhuma mudanca real de dado (o dia corrente/anterior e
# sempre re-importado a cada ciclo do scheduler). Usar `last_imported_at` como watermark fazia
# a sincronizacao reprocessar o mesmo volume de O.S. (hoje+ontem) em TODO ciclo, mesmo quando
# nada mudou - achado real, ver conversa que motivou este ajuste.
OPERATIONS_SYNC_WATERMARK_KEY = "operations_sync_last_source_updated_at"
RECONCILIATION_IMPORT_FILENAME = "operations-orders-reconciliation"
RECONCILIATION_AUDIT_REASON = "Created by operations_orders reconciliation"


def _ensure_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} deve ser timezone-aware.")


def _local_paid_period_reference_date(payload: dict[str, Any]) -> datetime | None:
    reference_date = reference_date_for_payload(payload)
    if reference_date is None:
        return None
    if reference_date.tzinfo is None or reference_date.utcoffset() is None:
        reference_date = reference_date.replace(tzinfo=timezone.utc)
    return reference_date.astimezone(OPERATIONS_TIMEZONE)


def _acquire_ixc_import_transaction_lock(db: Session) -> None:
    """Serializa o lote com a mesma chave do importador IXC, mas no escopo da transacao atual.

    `pg_try_advisory_xact_lock` conflita com `pg_try_advisory_lock` para a mesma chave no
    PostgreSQL, entao o reconciliador continua disputando a mesma exclusao logica do sync/importador.
    A diferenca importante e que o lock transacional e liberado automaticamente no COMMIT/ROLLBACK do
    lote, evitando conexao devolvida ao pool ainda segurando lock de sessao.
    """
    waited = 0.0
    acquired = False
    while waited <= IXC_IMPORT_LOCK_MAX_WAIT_SECONDS:
        acquired = bool(
            db.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": IXC_IMPORT_LOCK_KEY}).scalar()
        )
        if acquired:
            return
        time.sleep(IXC_IMPORT_LOCK_POLL_INTERVAL_SECONDS)
        waited += IXC_IMPORT_LOCK_POLL_INTERVAL_SECONDS

    if not acquired:
        raise IxcImportLockTimeoutError(
            "Outra importação do IXC (sincronização automática ou retroativa) já está em andamento. Tente novamente em instantes."
        )


def _empty_reconciliation_result(*, dry_run: bool) -> dict[str, Any]:
    return {
        "dry_run": dry_run,
        "analyzed_count": 0,
        "candidate_count": 0,
        "existing_by_os_code": 0,
        "existing_by_fallback": 0,
        "blocked_paid_period": 0,
        "invalid_collaborator": 0,
        "invalid": 0,
        "ready_to_create": 0,
        "created_count": 0,
        "error_count": 0,
        "ready_os_codes": [],
        "created_os_codes": [],
        "errors": [],
        "batches": [],
    }


def _merge_reconciliation_result(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in (
        "analyzed_count",
        "candidate_count",
        "existing_by_os_code",
        "existing_by_fallback",
        "blocked_paid_period",
        "invalid_collaborator",
        "invalid",
        "ready_to_create",
        "created_count",
        "error_count",
    ):
        target[key] += int(source.get(key) or 0)
    target["ready_os_codes"].extend(source.get("ready_os_codes") or [])
    target["created_os_codes"].extend(source.get("created_os_codes") or [])
    target["errors"].extend(source.get("errors") or [])
    target["batches"].extend(source.get("batches") or [])


def _existing_match_type(existing: ServiceOrder, payload: dict[str, Any]) -> str:
    return "os_code" if payload.get("os_code") and existing.os_code == payload.get("os_code") else "fallback"


def _find_existing_collaborator_readonly(
    *,
    name: str,
    ixc_employee_id: int | None,
    collaborators_cache: list[Collaborator],
) -> Collaborator | None:
    if ixc_employee_id is not None:
        for collaborator in collaborators_cache:
            if collaborator.ixc_employee_id == ixc_employee_id:
                return collaborator if collaborator.active else None

    normalized_name = normalize_header(name)
    if not normalized_name:
        return None
    for collaborator in collaborators_cache:
        if normalize_header(collaborator.name) == normalized_name:
            return collaborator if collaborator.active else None
    return None


def _operation_reconciliation_query(
    *,
    date_from: datetime,
    date_to: datetime,
    collaborator_id: int | None = None,
    responsible_ixc_id: int | None = None,
    operation_order_ids: list[int] | None = None,
    os_codes: list[str] | None = None,
):
    query = select(OperationOrder).where(
        OperationOrder.source == "ixc",
        OperationOrder.is_closed.is_(True),
        OperationOrder.sector.in_(PRIMARY_SECTOR_NAMES),
        OperationOrder.closed_at >= date_from,
        OperationOrder.closed_at < date_to,
    )
    if responsible_ixc_id is not None:
        query = query.where(OperationOrder.responsible_ixc_id == responsible_ixc_id)
    if operation_order_ids:
        query = query.where(OperationOrder.id.in_(operation_order_ids))
    if os_codes:
        query = query.where(OperationOrder.order_code.in_(os_codes))
    if collaborator_id is not None:
        collaborator_subquery = select(Collaborator.ixc_employee_id).where(Collaborator.id == collaborator_id)
        query = query.where(OperationOrder.responsible_ixc_id.in_(collaborator_subquery))
    cursor = func.coalesce(OperationOrder.source_updated_at, OperationOrder.first_imported_at)
    return query.order_by(cursor.asc(), OperationOrder.id.asc())


def _load_reconciliation_batch_orders(
    db: Session,
    *,
    operation_order_ids: list[int],
    date_from: datetime,
    date_to: datetime,
    collaborator_id: int | None,
    responsible_ixc_id: int | None,
    os_codes: list[str] | None,
) -> list[OperationOrder]:
    if not operation_order_ids:
        return []
    return list(
        db.scalars(
            _operation_reconciliation_query(
                date_from=date_from,
                date_to=date_to,
                collaborator_id=collaborator_id,
                responsible_ixc_id=responsible_ixc_id,
                operation_order_ids=operation_order_ids,
                os_codes=os_codes,
            )
        )
    )


def _finalize_reconciliation_import_run(
    import_run: ImportRun,
    *,
    errors: list[dict[str, Any]],
) -> None:
    import_run.imported_rows = import_run.created_count + import_run.updated_count
    import_run.ignored_rows = (
        import_run.skipped_count
        + import_run.rejected_count
        + import_run.paid_period_blocked_count
        + import_run.error_rows
    )
    import_run.errors = errors
    import_run.finished_at = datetime.now(timezone.utc)
    if import_run.error_rows or import_run.paid_period_blocked_count or import_run.rejected_count:
        import_run.status = "completed_with_warnings"
    import_run.notes = (
        "Reconciliação concluída com alertas."
        if import_run.status == "completed_with_warnings"
        else "Reconciliação concluída com sucesso."
    )


def _resolve_collaborator(
    db: Session,
    *,
    name: str,
    regional: str,
    ixc_employee_id: int | None,
    collaborators_cache: list[Collaborator],
) -> tuple[Collaborator, bool]:
    """Casa o tecnico responsavel pela O.S a um `Collaborator`, priorizando o id do funcionario
    no IXC (`ixc_employee_id`) sobre o nome - nome pode ter grafia diferente entre o cadastro do
    colaborador e o que vem em `operations_orders.responsible`. Colaboradores cadastrados antes
    dessa mudanca (sem `ixc_employee_id` ainda) sao casados por nome normalizado (mesma logica de
    `get_or_create_collaborator`) e tem o id gravado retroativamente na primeira ocorrencia -
    autocura o vinculo dai em diante.
    """
    if ixc_employee_id is not None:
        for collaborator in collaborators_cache:
            if collaborator.ixc_employee_id == ixc_employee_id:
                if regional and (collaborator.regional != regional or not is_valid_regional(collaborator.regional)):
                    collaborator.regional = collaborator.regional or regional
                    if not is_valid_regional(collaborator.regional):
                        collaborator.regional = regional
                if not collaborator.active:
                    # Achado real: ver o mesmo comentario em upvalue_importer.get_or_create_collaborator -
                    # forcar is_registered=False aqui derrubava o cadastro de quem so tinha sido
                    # desativado temporariamente (nao excluido) pela tela.
                    collaborator.active = True
                return collaborator, False

    collaborator, created = get_or_create_collaborator(
        db, name, regional, collaborators_cache=collaborators_cache
    )
    if ixc_employee_id is not None and collaborator.ixc_employee_id is None:
        collaborator.ixc_employee_id = ixc_employee_id
    return collaborator, created


def build_service_order_payload_from_operation_order(
    order: OperationOrder, subject_types: dict[str, str]
) -> dict[str, Any]:
    """Monta o payload de `ServiceOrder` a partir de uma O.S. ja normalizada em `operations_orders`
    - sem nenhuma nova chamada ao IXC, ja que o modulo de operacoes ja resolveu assunto/diagnostico/
    cliente/login/etc. Espelha `build_service_order_payload_from_ixc` (mesmos campos, mesmas regras),
    trocando so a fonte dos dados brutos.
    """
    os_subject = order.os_subject or UNKNOWN_VALUE
    os_type = (
        subject_types.get(os_subject)
        or KNOWN_OS_TYPE_BY_SUBJECT.get(os_subject)
        or order.os_type
        or PENDING_OS_TYPE
    )
    raw_payload = order.raw_payload or {}

    return {
        "os_code": order.order_code,
        "contract_id": order.contract_id or UNKNOWN_VALUE,
        "customer_login": order.customer_login or None,
        "customer_name": order.customer_name or "Não informado",
        "collaborator_name": order.responsible or UNKNOWN_VALUE,
        "responsible_ixc_id": order.responsible_ixc_id,
        # Agrupado porque `operations_orders.regional` vem granular por filial (é a identidade da
        # Operação Analítica) e a gamificação apura/paga São Miguel do Guaporé, Seringueiras e São
        # Francisco do Guaporé como uma regional só.
        "regional": normalize_regional_grouped(order.regional) if order.regional else UNKNOWN_VALUE,
        "os_type": os_type,
        "os_subject": os_subject,
        "diagnosis": order.diagnosis or "Não informado",
        "status": "Concluída",
        # Copiado diretamente do calculo ja feito em operations/ixc_ingestion.py - nao recalculado
        # aqui, para garantir que o SLA exibido no dashboard analitico e o usado na pontuacao sejam
        # literalmente o mesmo numero (ver normalize_sla_status em app/services/sla.py).
        "sla_status": order.sla_status or "",
        "sla_hours": order.sla_target_hours,
        "closing_time_hours": order.elapsed_hours,
        "opened_at": order.opened_at,
        "closed_at": order.closed_at,
        "is_warranty": False,
        "is_recurrence": False,
        "is_priority": bool(order.sla_target_hours is not None and order.sla_target_hours <= 6),
        "has_reschedule": bool(str(raw_payload.get("data_reagendar") or "").strip()),
        "has_pending": False,
        "__provided_fields__": list(IXC_PROVIDED_FIELDS),
    }


def _classify_or_create_reconciliation_order(
    db: Session,
    *,
    order: OperationOrder,
    subject_types: dict[str, str],
    collaborators_cache: list[Collaborator],
    dry_run: bool,
    import_run: ImportRun | None,
    row_number: int,
    imported_by: int | None,
) -> tuple[str, ServiceOrder | None, dict[str, Any] | None]:
    payload = build_service_order_payload_from_operation_order(order, subject_types)
    payload.pop("__provided_fields__", None)
    collaborator_name = payload.pop("collaborator_name")
    ixc_employee_id = payload.pop("responsible_ixc_id")
    os_code = payload.get("os_code") or order.order_code

    existing = find_existing_service_order(db, payload)
    if existing:
        return _existing_match_type(existing, payload), None, None

    target_paid_run = find_paid_run_for_service_order_context(
        db,
        _local_paid_period_reference_date(payload),
        payload.get("regional"),
    )
    if target_paid_run:
        if import_run is not None:
            reason = "A O.S pertence a um período já marcado como pago e não foi criada. Para revisar, crie uma revisão pós-pagamento."
            add_import_audit(
                db,
                import_run,
                "blocked_paid_period",
                os_code=os_code,
                reason=reason,
                row_number=row_number,
                created_by=imported_by,
            )
        return "blocked_paid_period", None, None

    collaborator = _find_existing_collaborator_readonly(
        name=collaborator_name,
        ixc_employee_id=ixc_employee_id,
        collaborators_cache=collaborators_cache,
    )
    if collaborator is None:
        return (
            "invalid_collaborator",
            None,
            {
                "row": row_number,
                "os_code": os_code,
                "operation_order_id": order.id,
                "reason": "Colaborador ativo não encontrado para a O.S.",
            },
        )

    payload["collaborator_id"] = collaborator.id
    if dry_run:
        return "ready", None, None

    service_order = ServiceOrder(**payload)
    db.add(service_order)
    db.flush()
    if import_run is not None:
        add_import_audit(
            db,
            import_run,
            "created",
            os_code=service_order.os_code,
            service_order_id=service_order.id,
            reason=RECONCILIATION_AUDIT_REASON,
            row_number=row_number,
            created_by=imported_by,
        )
    return "created", service_order, None


def _process_reconciliation_orders(
    db: Session,
    *,
    orders: list[OperationOrder],
    subject_types: dict[str, str],
    collaborators_cache: list[Collaborator],
    dry_run: bool,
    import_run: ImportRun | None,
    imported_by: int | None,
    batch_number: int | None = None,
    row_offset: int = 0,
) -> tuple[dict[str, Any], list[ServiceOrder]]:
    result = _empty_reconciliation_result(dry_run=dry_run)
    touched_orders: list[ServiceOrder] = []

    for index, order in enumerate(orders, start=1):
        row_number = row_offset + index
        os_code = order.order_code
        result["analyzed_count"] += 1
        try:
            status, service_order, error = _classify_or_create_reconciliation_order(
                db,
                order=order,
                subject_types=subject_types,
                collaborators_cache=collaborators_cache,
                dry_run=dry_run,
                import_run=import_run,
                row_number=row_number,
                imported_by=imported_by,
            )
            if status == "os_code":
                result["existing_by_os_code"] += 1
                if import_run is not None:
                    import_run.skipped_count += 1
            elif status == "fallback":
                result["existing_by_fallback"] += 1
                if import_run is not None:
                    import_run.skipped_count += 1
            elif status == "blocked_paid_period":
                result["candidate_count"] += 1
                result["blocked_paid_period"] += 1
                if import_run is not None:
                    import_run.paid_period_blocked_count += 1
            elif status == "invalid_collaborator":
                result["candidate_count"] += 1
                result["invalid_collaborator"] += 1
                result["errors"].append(error)
                if import_run is not None:
                    import_run.rejected_count += 1
            elif status == "ready":
                result["candidate_count"] += 1
                result["ready_to_create"] += 1
                result["ready_os_codes"].append(os_code)
            elif status == "created":
                result["candidate_count"] += 1
                result["ready_to_create"] += 1
                result["created_count"] += 1
                result["created_os_codes"].append(os_code)
                if service_order is not None:
                    touched_orders.append(service_order)
                if import_run is not None:
                    import_run.created_count += 1
            if import_run is not None:
                import_run.processed_rows += 1
        except Exception as exc:
            if not dry_run:
                raise
            result["candidate_count"] += 1
            result["error_count"] += 1
            error = {
                "row": row_number,
                "os_code": os_code,
                "operation_order_id": order.id,
                "reason": f"Erro inesperado: {exc}",
            }
            result["errors"].append(error)
            if import_run is not None:
                import_run.processed_rows += 1
                import_run.error_rows += 1
                add_import_audit(
                    db,
                    import_run,
                    "error",
                    os_code=os_code,
                    reason=error["reason"],
                    row_number=row_number,
                    created_by=imported_by,
                )

    if batch_number is not None:
        result["batches"].append(
            {
                "batch_number": batch_number,
                "candidate_count": result["candidate_count"],
                "created_count": result["created_count"],
                "skipped_count": result["existing_by_os_code"] + result["existing_by_fallback"],
                "error_count": result["error_count"],
            }
        )
    return result, touched_orders


def reconcile_missing_service_orders_from_operations(
    db: Session,
    *,
    date_from: datetime,
    date_to: datetime,
    collaborator_id: int | None = None,
    responsible_ixc_id: int | None = None,
    operation_order_ids: list[int] | None = None,
    os_codes: list[str] | None = None,
    dry_run: bool = True,
    batch_size: int = 25,
    imported_by: int | None = None,
) -> dict[str, Any]:
    """Reconcilia lacunas de `operations_orders` em `service_orders` sem depender da watermark.

    Dry-run e leitura pura: nao cria ImportRun, Collaborator, ServiceOrder, auditoria nem atualiza
    timestamps. A execucao real usa lock consultivo transacional por lote, com a mesma chave da
    importacao IXC, para evitar corrida com sync incremental/backfills sem segurar lock de sessao
    entre commits.
    """
    _ensure_timezone_aware(date_from, "date_from")
    _ensure_timezone_aware(date_to, "date_to")
    if date_from >= date_to:
        raise ValueError("date_from deve ser menor que date_to.")
    if batch_size <= 0:
        raise ValueError("batch_size deve ser maior que zero.")

    operation_order_ids = list(dict.fromkeys(operation_order_ids or []))
    os_codes = list(dict.fromkeys(os_codes or []))
    orders = list(
        db.scalars(
            _operation_reconciliation_query(
                date_from=date_from,
                date_to=date_to,
                collaborator_id=collaborator_id,
                responsible_ixc_id=responsible_ixc_id,
                operation_order_ids=operation_order_ids,
                os_codes=os_codes,
            )
        )
    )

    if dry_run:
        subject_types = {**load_historical_os_type_mapping(db), **load_subject_rule_os_type_mapping(db)}
        collaborators_cache = list(db.scalars(select(Collaborator)))
        result, _ = _process_reconciliation_orders(
            db,
            orders=orders,
            subject_types=subject_types,
            collaborators_cache=collaborators_cache,
            dry_run=True,
            import_run=None,
            imported_by=imported_by,
        )
        return result

    final_result = _empty_reconciliation_result(dry_run=False)
    candidate_refs = [(order.id, order.order_code) for order in orders]

    for batch_number, start in enumerate(range(0, len(candidate_refs), batch_size), start=1):
        batch_refs = candidate_refs[start : start + batch_size]
        batch_order_ids = [order_id for order_id, _ in batch_refs]
        batch_os_codes = [os_code for _, os_code in batch_refs]
        try:
            _acquire_ixc_import_transaction_lock(db)
            batch_orders = _load_reconciliation_batch_orders(
                db,
                operation_order_ids=batch_order_ids,
                date_from=date_from,
                date_to=date_to,
                collaborator_id=collaborator_id,
                responsible_ixc_id=responsible_ixc_id,
                os_codes=os_codes,
            )
            batch_subject_types = {**load_historical_os_type_mapping(db), **load_subject_rule_os_type_mapping(db)}
            batch_collaborators_cache = list(db.scalars(select(Collaborator)))
            import_run = ImportRun(
                filename=RECONCILIATION_IMPORT_FILENAME,
                file_hash=None,
                source="ixc",
                status="completed",
                total_rows=len(batch_orders),
                detected_columns=[],
                mapped_columns={},
                errors=[],
                imported_by=imported_by,
                started_at=datetime.now(timezone.utc),
                notes=None,
            )
            db.add(import_run)
            db.flush()
            batch_result, _ = _process_reconciliation_orders(
                db,
                orders=batch_orders,
                subject_types=batch_subject_types,
                collaborators_cache=batch_collaborators_cache,
                dry_run=False,
                import_run=import_run,
                imported_by=imported_by,
                batch_number=batch_number,
                row_offset=start,
            )
            _finalize_reconciliation_import_run(import_run, errors=batch_result["errors"])
            db.commit()
            _merge_reconciliation_result(final_result, batch_result)
        except Exception as exc:
            db.rollback()
            batch_error = {
                "batch_number": batch_number,
                "reason": f"Rollback do lote: {exc}",
                "os_codes": batch_os_codes,
            }
            final_result["analyzed_count"] += len(batch_refs)
            final_result["candidate_count"] += len(batch_refs)
            final_result["error_count"] += len(batch_refs)
            final_result["errors"].append(batch_error)
            final_result["batches"].append(
                {
                    "batch_number": batch_number,
                    "candidate_count": len(batch_refs),
                    "created_count": 0,
                    "skipped_count": 0,
                    "error_count": len(batch_refs),
                }
            )
            # Um lote com erro nao interrompe os demais - o objetivo da reconciliacao e cobrir o
            # intervalo de datas inteiro; um lote com problema (achado real: um unico registro
            # inesperado abortava silenciosamente todos os lotes seguintes, sem nenhum sinal no
            # resultado de que o restante do intervalo nunca foi tentado) so deve pular esse lote,
            # nunca os demais.
            continue
    return final_result


def reconcile_recent_missing_service_orders_from_operations(
    db: Session,
    *,
    days: int = 7,
    dry_run: bool = True,
    batch_size: int = 25,
    imported_by: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if days <= 0:
        raise ValueError("days deve ser maior que zero.")
    reference = now or datetime.now(timezone.utc)
    return reconcile_missing_service_orders_from_operations(
        db,
        date_from=reference - timedelta(days=days),
        date_to=reference,
        dry_run=dry_run,
        batch_size=batch_size,
        imported_by=imported_by,
    )


def sync_service_orders_from_operations(
    db: Session,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    imported_by: int | None = None,
) -> dict[str, Any]:
    """Projeta `operations_orders` (a unica fonte de importacao do IXC, ver
    app/modules/operations/ixc_ingestion.py) em `service_orders`, reaproveitando todo o pipeline de
    matching/auditoria/bloqueio de periodo pago que o importador UpValue/IXC ja usa - so troca de
    onde vem o payload bruto. Roda apos cada ciclo de importacao do modulo operations (ver
    app/services/ixc_scheduler.py).

    `operations_orders` cobre setores alem dos tecnicos (o modulo de operacoes analiticas existe
    para analytics organizacional mais amplo - ver IXC_SECTORS em modules/operations/scope.py, e o
    backfill por CLI aceita --sector-ids arbitrario). A gamificacao so pontua trabalho tecnico de
    campo (decisao do dono do produto, a mesma que o importador antigo aplicava via
    PRIMARY_IXC_SECTOR_IDS/PRIMARY_SECTOR_NAMES, mesma fonte usada aqui) - sem este filtro,
    O.S. de Comercial/Financeiro/Cobranca/etc. viram
    `ServiceOrder` e criam colaboradores fantasma (atendentes desses setores) no ranking.
    """
    cursor = func.coalesce(OperationOrder.source_updated_at, OperationOrder.first_imported_at)
    query = select(OperationOrder).where(
        OperationOrder.source == "ixc",
        OperationOrder.is_closed.is_(True),
        OperationOrder.sector.in_(PRIMARY_SECTOR_NAMES),
    )
    if since is not None:
        query = query.where(cursor > since)
    if until is not None:
        query = query.where(cursor <= until)
    orders = list(db.scalars(query.order_by(cursor.asc())))

    subject_types = {**load_historical_os_type_mapping(db), **load_subject_rule_os_type_mapping(db)}
    collaborators_cache = list(db.scalars(select(Collaborator)))

    errors: list[dict[str, Any]] = []
    import_run = ImportRun(
        filename="operations-orders-sync",
        file_hash=None,
        source="ixc",
        status="completed",
        total_rows=len(orders),
        detected_columns=[],
        mapped_columns={},
        errors=[],
        imported_by=imported_by,
        started_at=datetime.now(timezone.utc),
        notes=None,
    )
    db.add(import_run)
    db.flush()

    touched_orders: list[ServiceOrder] = []
    max_cursor_seen = since

    for offset, order in enumerate(orders, start=1):
        order_cursor = order.source_updated_at or order.first_imported_at
        max_cursor_seen = max(max_cursor_seen or order_cursor, order_cursor)
        try:
            payload = build_service_order_payload_from_operation_order(order, subject_types)
            provided_fields = set(payload.pop("__provided_fields__", []))
            collaborator_name = payload.pop("collaborator_name")
            ixc_employee_id = payload.pop("responsible_ixc_id")
            existing = find_existing_service_order(db, payload)
            target_paid_run = find_paid_run_for_service_order_context(
                db,
                (existing.closed_at if existing else None) or (existing.opened_at if existing else None) or reference_date_for_payload(payload),
                existing.regional if existing else payload.get("regional"),
            )
            if not target_paid_run and (existing is None or "collaborator" in provided_fields):
                collaborator, created_collaborator = _resolve_collaborator(
                    db,
                    name=collaborator_name,
                    regional=payload["regional"],
                    ixc_employee_id=ixc_employee_id,
                    collaborators_cache=collaborators_cache,
                )
                if created_collaborator:
                    import_run.unknown_collaborator_count += 1
                payload["collaborator_id"] = collaborator.id
                if "collaborator" in provided_fields:
                    provided_fields.add("collaborator_id")

            if existing:
                changes: list[tuple[str, Any, Any]] = []
                for field_name, value in payload.items():
                    if field_name not in provided_fields:
                        continue
                    current_value = getattr(existing, field_name)
                    if values_differ(field_name, current_value, value):
                        changes.append((field_name, current_value, value))
                if not changes:
                    import_run.skipped_count += 1
                    add_import_audit(
                        db, import_run, "skipped", os_code=existing.os_code, service_order_id=existing.id,
                        reason="sem alterações", row_number=offset, created_by=imported_by,
                    )
                elif target_paid_run:
                    import_run.paid_period_blocked_count += 1
                    reason = "A O.S pertence a um período já marcado como pago e não foi alterada. Para revisar, crie uma revisão pós-pagamento."
                    add_import_audit(
                        db, import_run, "blocked_paid_period", os_code=existing.os_code,
                        service_order_id=existing.id, reason=reason, row_number=offset, created_by=imported_by,
                    )
                    errors.append({"row": offset, "reason": reason, "os_code": existing.os_code})
                else:
                    for field_name, old_value, new_value in changes:
                        setattr(existing, field_name, new_value)
                        add_import_audit(
                            db, import_run, "updated", os_code=existing.os_code, service_order_id=existing.id,
                            field_name=field_name, old_value=old_value, new_value=new_value,
                            row_number=offset, created_by=imported_by,
                        )
                    import_run.updated_count += 1
                    touched_orders.append(existing)
            else:
                if target_paid_run:
                    import_run.paid_period_blocked_count += 1
                    reason = "A O.S pertence a um período já marcado como pago e não foi criada. Para revisar, crie uma revisão pós-pagamento."
                    add_import_audit(
                        db, import_run, "blocked_paid_period", os_code=payload.get("os_code"),
                        reason=reason, row_number=offset, created_by=imported_by,
                    )
                    errors.append({"row": offset, "reason": reason, "os_code": payload.get("os_code")})
                else:
                    service_order = ServiceOrder(**payload)
                    db.add(service_order)
                    db.flush()
                    add_import_audit(
                        db, import_run, "created", os_code=service_order.os_code, service_order_id=service_order.id,
                        reason="O.S criada a partir da sincronização com o módulo de operações analíticas",
                        row_number=offset, created_by=imported_by,
                    )
                    import_run.created_count += 1
                    touched_orders.append(service_order)
            import_run.processed_rows += 1
        except Exception as exc:
            import_run.processed_rows += 1
            import_run.error_rows += 1
            add_import_audit(
                db, import_run, "error", reason=f"Erro inesperado: {exc}", row_number=offset, created_by=imported_by,
            )
            errors.append({"row": offset, "reason": f"Erro inesperado: {exc}", "os_code": order.order_code})

    import_run.imported_rows = import_run.created_count + import_run.updated_count
    import_run.ignored_rows = import_run.skipped_count + import_run.rejected_count + import_run.paid_period_blocked_count + import_run.error_rows
    import_run.errors = errors
    import_run.finished_at = datetime.now(timezone.utc)
    if import_run.error_rows or import_run.paid_period_blocked_count:
        import_run.status = "completed_with_warnings"
    import_run.notes = (
        "Sincronização concluída com alertas." if import_run.status == "completed_with_warnings" else "Sincronização concluída com sucesso."
    )

    if touched_orders:
        detect_post_payment_warranty_debits(db, touched_orders, triggered_by=imported_by)

    result = build_import_result(import_run)
    result["watermark_candidate"] = max_cursor_seen.isoformat() if max_cursor_seen else None
    return result


def run_operations_to_service_orders_sync(db: Session, *, imported_by: int | None = None) -> dict[str, Any]:
    """Ponto de entrada periodico: le a marca d'agua salva, sincroniza so o que `operations_orders`
    recebeu/atualizou desde entao, e avanca a marca d'agua. Pensada pra rodar logo apos cada ciclo de
    importacao do IXC no modulo operations (ver app/services/ixc_scheduler.py).

    Adquire o mesmo lock consultivo (`_ixc_import_lock`, ver ixc_importer.py) que o backfill manual
    (`import_ixc_service_orders`) ja usa - antes, so o caminho manual travava, e o comentario que
    dizia "sincronizacao periodica e backfill manual nunca rodam ao mesmo tempo" nao era garantido
    por codigo nenhum. Sem esse lock compartilhado, os dois caminhos rodando ao mesmo tempo podiam
    criar `Collaborator` duplicado pro mesmo nome novo ou colidir na chave unica de `os_code` (mesmo
    risco que motivou o lock no caminho manual)."""
    with _ixc_import_lock(db):
        watermark_raw = get_setting(db, OPERATIONS_SYNC_WATERMARK_KEY, "")
        since = datetime.fromisoformat(watermark_raw) if watermark_raw else None
        until = datetime.now(timezone.utc)

        result = sync_service_orders_from_operations(db, since=since, until=until, imported_by=imported_by)
        result["watermark_used"] = watermark_raw or None

        new_watermark = result.get("watermark_candidate") or until.isoformat()
        upsert_setting(
            db, OPERATIONS_SYNC_WATERMARK_KEY, new_watermark,
            description="Até quando (source_updated_at de operations_orders) a projeção para service_orders já processou.",
        )
        db.flush()
        result["watermark_advanced_to"] = new_watermark
        return result


def backfill_collaborator_ixc_ids(db: Session) -> dict[str, int]:
    """Backfill unico: para colaboradores existentes sem `ixc_employee_id`, tenta casar por nome
    normalizado contra `operations_orders.responsible`/`responsible_ixc_id` (o mesmo par que a
    sincronizacao periodica usa dai em diante). Nao faz nenhuma chamada ao IXC - so lê o que ja foi
    importado."""
    known_ids_by_name: dict[str, int] = {}
    rows = db.execute(
        select(OperationOrder.responsible, OperationOrder.responsible_ixc_id)
        .where(OperationOrder.responsible.is_not(None), OperationOrder.responsible_ixc_id.is_not(None))
        .distinct()
    ).all()
    for name, ixc_id in rows:
        normalized = normalize_header(name)
        if normalized and normalized not in known_ids_by_name:
            known_ids_by_name[normalized] = ixc_id

    changed = 0
    collaborators = list(db.scalars(select(Collaborator).where(Collaborator.ixc_employee_id.is_(None))))
    used_ids: set[int] = set()
    for collaborator in collaborators:
        ixc_id = known_ids_by_name.get(normalize_header(collaborator.name))
        if ixc_id is not None and ixc_id not in used_ids:
            collaborator.ixc_employee_id = ixc_id
            used_ids.add(ixc_id)
            changed += 1
    db.commit()
    return {"scanned": len(collaborators), "changed": changed}
