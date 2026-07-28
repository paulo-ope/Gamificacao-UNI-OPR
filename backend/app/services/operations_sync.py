from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Collaborator, ImportRun, ServiceOrder
from app.modules.operations.models import OperationOrder
from app.modules.operations.scope import PRIMARY_SECTOR_NAMES
from app.services.calculation import get_setting, upsert_setting
from app.services.calculation_closure import find_paid_run_for_service_order_context
from app.services.ixc_importer import (
    IXC_PROVIDED_FIELDS,
    KNOWN_OS_TYPE_BY_SUBJECT,
    PENDING_OS_TYPE,
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
    IXC_TECHNICAL_SETOR_IDS) - sem este filtro, O.S. de Comercial/Financeiro/Cobranca/etc. viram
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
    importacao do IXC no modulo operations (ver app/services/ixc_scheduler.py)."""
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
