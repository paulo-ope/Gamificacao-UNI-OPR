from __future__ import annotations

import contextlib
import time
from datetime import date, datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import ScoringSubjectRule
from app.services.ixc_client import (
    IxcClient,
    IxcQueryLimitError,
    fetch_service_order_id_bounds,
    fetch_service_orders,
)
from app.services.ixc_importer import KNOWN_OS_TYPE_BY_SUBJECT
from app.services.regional import normalize_regional

from .models import OperationImportRun, OperationOrder, OperationSubjectTypeMapping
from .period import OPERATIONS_TIMEZONE, local_day_query_bounds, parse_ixc_local_datetime
from .scope import IXC_SECTORS


OPERATIONS_IMPORT_LOCK_KEY = 913_275_002
LOOKUP_CHUNK_SIZE = 200
MAX_IXC_RECORDS_PER_QUERY = 3_000
# 2^12 subdivisões - blindagem contra faixa de id patológica (não monotônica/duplicada no IXC),
# nunca deveria ser alcançado em uso normal (uma combinação setor+status real precisaria de mais
# de 3000 * 2^12 O.S. para chegar até aqui).
MAX_ID_PARTITION_DEPTH = 12
# Campos calculados a partir da meta de horas do assunto (nao de um dado proprio da O.S) - ver uso
# em _ingest_records abaixo.
SLA_DERIVED_FIELDS = {"sla_status", "sla_target_hours", "elapsed_hours"}


def _clean(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _to_int(value: object) -> int | None:
    if value in (None, "", "0", 0):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _first(record: dict[str, Any] | None, *keys: str) -> str:
    if not record:
        return ""
    for key in keys:
        value = _clean(record.get(key))
        if value:
            return value
    return ""


def _chunks(values: Iterable[int], size: int = LOOKUP_CHUNK_SIZE) -> list[list[int]]:
    items = sorted(set(values))
    return [items[index : index + size] for index in range(0, len(items), size)]


def _fetch_lookup_by_ids(client: IxcClient, table: str, ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for chunk in _chunks(ids):
        grid_param = [{"TB": f"{table}.id", "OP": "IN", "P": ",".join(str(item) for item in chunk)}]
        for record in client.list_all(
            table,
            grid_param=grid_param,
            rp=LOOKUP_CHUNK_SIZE,
            sortname=f"{table}.id",
            max_records=LOOKUP_CHUNK_SIZE,
        ):
            record_id = _to_int(record.get("id"))
            if record_id is not None:
                result[record_id] = record
    return result


def _collect_ids(records: list[dict[str, Any]], *keys: str) -> set[int]:
    values: set[int] = set()
    for record in records:
        for key in keys:
            parsed = _to_int(record.get(key))
            if parsed is not None:
                values.add(parsed)
    return values


def _subject_type_mapping(db: Session) -> dict[str, str]:
    mapping = {
        subject: os_type
        for subject, os_type in db.execute(
            select(OperationSubjectTypeMapping.subject, OperationSubjectTypeMapping.os_type)
            .where(OperationSubjectTypeMapping.active.is_(True))
            .order_by(OperationSubjectTypeMapping.updated_at.desc())
        )
        if subject and os_type
    }
    rows = db.execute(
        select(ScoringSubjectRule.os_subject, ScoringSubjectRule.os_type, ScoringSubjectRule.updated_at)
        .where(ScoringSubjectRule.active.is_(True))
        .order_by(ScoringSubjectRule.updated_at.desc().nullslast())
    ).all()
    for subject, os_type, _ in rows:
        if subject and os_type:
            mapping.setdefault(subject, os_type)
    return mapping


@contextlib.contextmanager
def _import_lock(db: Session):
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        yield
        return

    waited = 0.0
    acquired = False
    while waited <= 30:
        acquired = bool(db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": OPERATIONS_IMPORT_LOCK_KEY}).scalar())
        if acquired:
            break
        time.sleep(1)
        waited += 1
    if not acquired:
        raise RuntimeError("Outra importação analítica do IXC já está em andamento.")
    try:
        yield
    finally:
        db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": OPERATIONS_IMPORT_LOCK_KEY})


def _fetch_period_records(
    client: IxcClient,
    date_from: date,
    date_to: date,
    sector_ids: list[str],
) -> list[dict[str, Any]]:
    if date_from != date_to:
        raise ValueError("A importação analítica deve processar somente um dia por chamada.")
    start, end = local_day_query_bounds(date_from, date_to)
    by_id: dict[str, dict[str, Any]] = {}

    # Duas consultas limitadas ao período: uma cobre as O.S. abertas e a outra as
    # finalizadas no recorte. A união não realiza varredura histórica da tabela.
    for record in fetch_service_orders(
        client,
        opened_after=start,
        opened_before=end,
        setor_ids=sector_ids,
        only_finalized=False,
        max_records=MAX_IXC_RECORDS_PER_QUERY,
    ):
        key = _clean(record.get("id")) or _clean(record.get("protocolo"))
        if key:
            by_id[key] = record
    for record in fetch_service_orders(
        client,
        closed_after=start,
        closed_before=end,
        setor_ids=sector_ids,
        only_finalized=False,
        max_records=MAX_IXC_RECORDS_PER_QUERY,
    ):
        key = _clean(record.get("id")) or _clean(record.get("protocolo"))
        if key:
            by_id[key] = record
    return list(by_id.values())


OPEN_BACKLOG_STATUS_CODES = ("A", "EN", "AS", "AG", "EX", "R", "RAG", "D", "DS")


def _fetch_id_range_partitioned(
    client: IxcClient,
    sector_id: str,
    status_code: str,
    id_min: int,
    id_max: int,
    depth: int = 0,
) -> Iterable[dict[str, Any]]:
    """Busca um (setor, status) que já se sabe estourar o limite de segurança, bissectando a faixa
    de id até cada fatia caber em MAX_IXC_RECORDS_PER_QUERY. Nunca reduz o número de setores/status
    nem o limite de segurança - só estreita o recorte de id. Se uma fatia não puder mais ser
    dividida (id_min == id_max) e ainda assim estourar, ou a profundidade máxima for atingida,
    propaga o IxcQueryLimitError original em vez de mascarar ou entrar em loop."""
    try:
        yield from fetch_service_orders(
            client,
            setor_ids=[sector_id],
            statuses=[status_code],
            id_after=id_min,
            id_before=id_max,
            max_records=MAX_IXC_RECORDS_PER_QUERY,
        )
        return
    except IxcQueryLimitError:
        if id_min >= id_max or depth >= MAX_ID_PARTITION_DEPTH:
            raise
    mid = id_min + (id_max - id_min) // 2
    yield from _fetch_id_range_partitioned(client, sector_id, status_code, id_min, mid, depth + 1)
    yield from _fetch_id_range_partitioned(client, sector_id, status_code, mid + 1, id_max, depth + 1)


def _fetch_backlog_partition(
    client: IxcClient,
    sector_id: str,
    status_code: str,
) -> Iterable[dict[str, Any]]:
    """Busca um (setor, status) do backlog aberto. Caminho feliz: consulta direta, sem custo extra
    quando o recorte cabe no limite. Só descobre os limites de id e aciona o particionamento por
    faixa quando a consulta direta realmente estoura MAX_IXC_RECORDS_PER_QUERY."""
    try:
        yield from fetch_service_orders(
            client,
            setor_ids=[sector_id],
            statuses=[status_code],
            max_records=MAX_IXC_RECORDS_PER_QUERY,
        )
    except IxcQueryLimitError:
        bounds = fetch_service_order_id_bounds(client, setor_ids=[sector_id], statuses=[status_code])
        if bounds is None:
            raise
        id_min, id_max = bounds
        yield from _fetch_id_range_partitioned(client, sector_id, status_code, id_min, id_max)


def _fetch_open_backlog_records(
    client: IxcClient,
    sector_ids: list[str],
    existing_open_source_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Consulta somente o backlog corrente, particionado para proteger o IXC."""
    by_id: dict[str, dict[str, Any]] = {}
    for sector_id in sector_ids:
        for status_code in OPEN_BACKLOG_STATUS_CODES:
            for record in _fetch_backlog_partition(client, sector_id, status_code):
                key = _clean(record.get("id")) or _clean(record.get("protocolo"))
                if key:
                    by_id[key] = record
    # Uma O.S. anteriormente aberta pode ter sido finalizada/cancelada e, por
    # isso, não aparecer mais nas partições de status aberto. Reconsultamos
    # somente esses IDs conhecidos, em lotes limitados, para reconciliar seu
    # estado sem fazer leitura histórica da tabela.
    fetched_ids = set(by_id)
    missing_ids = {
        parsed
        for source_id in (existing_open_source_ids or set()) - fetched_ids
        if (parsed := _to_int(source_id)) is not None
    }
    for record in _fetch_lookup_by_ids(client, "su_oss_chamado", missing_ids).values():
        key = _clean(record.get("id")) or _clean(record.get("protocolo"))
        if key:
            by_id[key] = record
    return list(by_id.values())


def _status_label(code: str, is_closed: bool) -> str:
    normalized = code.upper()
    labels = {
        "A": "Aberta",
        "EN": "Encaminhada",
        "AS": "Assumida",
        "AG": "Agendada",
        "EX": "Em execução",
        "R": "Reagendada",
        "RAG": "Reagendada",
        "D": "Deslocamento",
        "DS": "Deslocamento",
        "F": "Finalizada",
        "C": "Cancelada",
    }
    if normalized in labels:
        return labels[normalized]
    if is_closed:
        return "Finalizada"
    return code or "Não identificado"


def _float_or_none(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _normalize_record(
    record: dict[str, Any],
    lookups: dict[str, dict[int, dict[str, Any]]],
    subject_types: dict[str, str],
    now: datetime,
) -> dict[str, Any]:
    source_id = _clean(record.get("id"))
    if not source_id:
        raise ValueError("O.S. sem identificador no IXC.")

    opened_at = parse_ixc_local_datetime(record.get("data_abertura"))
    if opened_at is None:
        raise ValueError("O.S. sem data de abertura válida.")
    closed_at = parse_ixc_local_datetime(record.get("data_fechamento"))
    assumed_at = parse_ixc_local_datetime(record.get("data_hora_assumido"))
    displacement_started_at = parse_ixc_local_datetime(record.get("data_inicio"))
    execution_started_at = parse_ixc_local_datetime(record.get("data_hora_execucao"))
    finished_at = parse_ixc_local_datetime(record.get("data_final")) or closed_at
    deadline_at = parse_ixc_local_datetime(record.get("data_prazo_limite"))
    scheduled_at = parse_ixc_local_datetime(
        record.get("data_agenda") or record.get("data_agendamento") or record.get("data_reservada")
    )
    source_updated_at = parse_ixc_local_datetime(record.get("ultima_atualizacao"))

    subject = lookups["subjects"].get(_to_int(record.get("id_assunto")) or -1)
    diagnosis_record = lookups["diagnoses"].get(_to_int(record.get("id_su_diagnostico")) or -1)
    responsible_record = lookups["employees"].get(_to_int(record.get("id_tecnico")) or -1)
    ticket_record = lookups["tickets"].get(_to_int(record.get("id_ticket")) or -1)
    creator_id = _to_int(
        record.get("id_usuario")
        or record.get("id_atendente")
        or (ticket_record or {}).get("id_usuarios")
    )
    creator_record = lookups["users"].get(creator_id or -1) or lookups["employees"].get(creator_id or -1)
    sector_record = lookups["sectors"].get(_to_int(record.get("setor")) or -1)
    customer_record = lookups["customers"].get(_to_int(record.get("id_cliente")) or -1)
    login_record = lookups["logins"].get(_to_int(record.get("id_login")) or -1)
    city_id = _to_int(
        (customer_record or {}).get("id_cidade")
        or (customer_record or {}).get("cidade")
        or record.get("id_cidade")
    )
    city_record = lookups["cities"].get(city_id or -1)
    state_id = _to_int((city_record or {}).get("uf") or (customer_record or {}).get("uf"))
    state_record = lookups["states"].get(state_id or -1)
    contract_id = _first(login_record, "id_contrato") or _clean(record.get("id_contrato"))
    contract_record = lookups["contracts"].get(_to_int(contract_id) or -1)

    subject_name = _first(subject, "assunto", "descricao") or "Não identificado"
    os_type = subject_types.get(subject_name) or KNOWN_OS_TYPE_BY_SUBJECT.get(subject_name) or "Pendente de classificação"
    sector_name = _first(sector_record, "setor", "descricao", "nome")
    project = _first(record, "projeto", "id_projeto")
    pop = _first(record, "pop", "id_pop")
    status_code = _clean(record.get("status"))
    is_closed = bool(closed_at or status_code.upper() == "F")

    target_hours = _float_or_none((subject or {}).get("meta_horas_abertura"))
    reference_at = closed_at or now
    elapsed_hours = max(0.0, round((reference_at - opened_at).total_seconds() / 3600, 2))
    if target_hours is None:
        sla_status = "unidentified"
    else:
        sla_status = "on_time" if elapsed_hours <= target_hours else "out_of_time"

    city = _first(city_record, "nome", "cidade") or _first(customer_record, "cidade")
    raw_state = _first(city_record, "uf", "estado") or _first(customer_record, "uf")
    state = _first(state_record, "sigla", "nome") or (raw_state if raw_state and not raw_state.isdigit() else "")
    responsible = _first(responsible_record, "funcionario", "nome")
    responsible_ixc_id = _to_int(record.get("id_tecnico"))
    creator = _first(creator_record, "nome", "funcionario", "usuario")
    customer_name = _first(customer_record, "razao", "nome_social", "fantasia")
    priority = _first(record, "prioridade", "id_prioridade")
    person_type_code = _first(customer_record, "tipo_pessoa", "tipo_cliente").upper()
    person_type = {
        "F": "Pessoa Física",
        "J": "Pessoa Jurídica",
    }.get(person_type_code, person_type_code)

    notes: list[str] = []
    if not responsible:
        notes.append("Responsável não localizado na tabela funcionarios.")
    if creator_id and not creator:
        notes.append("Criador não localizado nas tabelas usuarios/funcionarios.")
    if not city:
        notes.append("Cidade não localizada nas tabelas consultadas.")

    return {
        "source": "ixc",
        "source_order_id": source_id,
        "order_code": f"IXC-{source_id}",
        "protocol": _clean(record.get("protocolo")) or None,
        "contract_id": contract_id or None,
        "customer_id": _clean(record.get("id_cliente")) or None,
        "customer_login": _first(login_record, "login") or None,
        "customer_name": customer_name or None,
        "company_id": _clean(record.get("id_empresa")) or None,
        "regional": normalize_regional(_clean(record.get("id_filial")) or None),
        "state": state or None,
        "city": city or None,
        # "bairro"/"latitude"/"longitude" confirmados como campos separados numa amostra real de
        # 104k+ O.S. já importadas (ver migration 20260811_0048) - diferente de número/CEP, que só
        # existem embutidos dentro da string única de "endereco" (sem chave própria observada).
        "neighborhood": _clean(record.get("bairro")) or None,
        "latitude": _float_or_none(record.get("latitude")),
        "longitude": _float_or_none(record.get("longitude")),
        "contract_type": _first(contract_record, "contrato", "descricao", "nome") or None,
        "person_type": person_type or None,
        "os_type": os_type,
        "os_subject": subject_name,
        "diagnosis": _first(diagnosis_record, "descricao", "diagnostico") or None,
        "department": _first(sector_record, "departamento") or None,
        "sector": sector_name or None,
        "priority": priority or None,
        "creator": creator or None,
        "responsible": responsible or None,
        "responsible_ixc_id": responsible_ixc_id,
        "project": project or None,
        "pop": pop or None,
        "status_code": status_code or None,
        "status": _status_label(status_code, is_closed),
        "is_closed": is_closed,
        "is_internal": bool(project or pop or "intern" in sector_name.lower()),
        "sla_status": sla_status,
        "sla_target_hours": target_hours,
        "elapsed_hours": elapsed_hours,
        "opened_at": opened_at,
        "assumed_at": assumed_at,
        "displacement_started_at": displacement_started_at,
        "execution_started_at": execution_started_at,
        "finished_at": finished_at,
        "deadline_at": deadline_at,
        "scheduled_at": scheduled_at,
        "closed_at": closed_at,
        "source_updated_at": source_updated_at,
        "raw_payload": record,
        "normalization_notes": " ".join(notes) or None,
    }


def import_current_month_period(
    db: Session,
    client: IxcClient,
    *,
    date_from: date,
    date_to: date,
    imported_by: int | None,
    sector_ids: list[str],
    open_backlog: bool = False,
) -> dict[str, Any]:
    with _import_lock(db):
        selected_sector_ids = list(dict.fromkeys(sector_ids))
        if not selected_sector_ids:
            raise ValueError("Informe ao menos um setor para a importação analítica.")
        if open_backlog:
            selected_sector_names = {
                name for sector_id, name in IXC_SECTORS if sector_id in selected_sector_ids
            }
            existing_open_source_ids = set(
                db.scalars(
                    select(OperationOrder.source_order_id).where(
                        OperationOrder.source == "ixc",
                        OperationOrder.is_closed.is_(False),
                        OperationOrder.sector.in_(selected_sector_names),
                    )
                )
            )
            records = _fetch_open_backlog_records(
                client,
                selected_sector_ids,
                existing_open_source_ids,
            )
        else:
            records = _fetch_period_records(client, date_from, date_to, selected_sector_ids)
        run = OperationImportRun(
            date_from=date_from,
            date_to=date_to,
            status="running",
            fetched_count=len(records),
            imported_by=imported_by,
        )
        db.add(run)
        db.flush()

        subject_ids = _collect_ids(records, "id_assunto")
        diagnosis_ids = _collect_ids(records, "id_su_diagnostico")
        employee_ids = _collect_ids(records, "id_tecnico", "id_funcionario")
        ticket_ids = _collect_ids(records, "id_ticket")
        sector_ids = _collect_ids(records, "setor")
        customer_ids = _collect_ids(records, "id_cliente")
        login_ids = _collect_ids(records, "id_login")

        tickets = _fetch_lookup_by_ids(client, "su_ticket", ticket_ids)
        user_ids = _collect_ids(records, "id_usuario", "id_atendente")
        user_ids.update(
            user_id
            for ticket in tickets.values()
            if (user_id := _to_int(ticket.get("id_usuarios"))) is not None
        )
        lookups = {
            "subjects": _fetch_lookup_by_ids(client, "su_oss_assunto", subject_ids),
            "diagnoses": _fetch_lookup_by_ids(client, "su_diagnostico", diagnosis_ids),
            "employees": _fetch_lookup_by_ids(client, "funcionarios", employee_ids),
            "tickets": tickets,
            "users": _fetch_lookup_by_ids(client, "usuarios", user_ids),
            "sectors": _fetch_lookup_by_ids(client, "empresa_setor", sector_ids),
            "customers": _fetch_lookup_by_ids(client, "cliente", customer_ids),
            "logins": _fetch_lookup_by_ids(client, "radusuarios", login_ids),
        }
        city_ids = {
            city_id
            for customer in lookups["customers"].values()
            if (city_id := _to_int(customer.get("id_cidade") or customer.get("cidade"))) is not None
        }
        lookups["cities"] = _fetch_lookup_by_ids(client, "cidade", city_ids)
        state_ids = {
            state_id
            for city in lookups["cities"].values()
            if (state_id := _to_int(city.get("uf"))) is not None
        }
        state_ids.update(
            state_id
            for customer in lookups["customers"].values()
            if (state_id := _to_int(customer.get("uf"))) is not None
        )
        lookups["states"] = _fetch_lookup_by_ids(client, "uf", state_ids)
        contract_ids = {
            contract_id
            for login in lookups["logins"].values()
            if (contract_id := _to_int(login.get("id_contrato"))) is not None
        }
        contract_ids.update(_collect_ids(records, "id_contrato"))
        lookups["contracts"] = _fetch_lookup_by_ids(client, "cliente_contrato", contract_ids)
        subject_types = _subject_type_mapping(db)
        now = datetime.now(timezone.utc)
        errors: list[dict[str, Any]] = []

        comparable_fields = set(OperationOrder.__table__.columns.keys()) - {
            "id", "first_imported_at", "last_imported_at"
        }
        for record in records:
            source_id = _clean(record.get("id")) or _clean(record.get("protocolo"))
            try:
                payload = _normalize_record(record, lookups, subject_types, now)
                existing = db.scalar(
                    select(OperationOrder).where(
                        OperationOrder.source == "ixc",
                        OperationOrder.source_order_id == payload["source_order_id"],
                    )
                )
                if existing is None:
                    db.add(OperationOrder(**payload))
                    run.created_count += 1
                    continue

                changed = False
                sla_derived_changed = False
                for field_name, value in payload.items():
                    if field_name not in comparable_fields:
                        continue
                    if getattr(existing, field_name) != value:
                        setattr(existing, field_name, value)
                        changed = True
                        if field_name in SLA_DERIVED_FIELDS:
                            sla_derived_changed = True
                existing.last_imported_at = now
                if sla_derived_changed and (existing.source_updated_at is None or existing.source_updated_at < now):
                    # sla_status/sla_target_hours/elapsed_hours sao derivados aqui (linha ~346) a
                    # partir da meta de horas do ASSUNTO atual (su_oss_assunto.meta_horas_abertura),
                    # nao de um campo proprio da O.S - uma mudanca de meta na IXC recalcula esses
                    # valores para O.S ja fechadas ha muito tempo, sem que o "ultima_atualizacao"
                    # daquela O.S especifica mude. sync_service_orders_from_operations usa
                    # source_updated_at como cursor incremental (ver operations_sync.py) para nao
                    # reprocessar o volume inteiro todo ciclo - sem este ajuste, a sincronizacao
                    # nunca voltaria a selecionar essa O.S, e o ServiceOrder usado para pontuar/pagar
                    # ficaria com o SLA desatualizado para sempre (achado real: meta de "Mud. de
                    # Tecnologia" mudou de 72h para 168h e o ServiceOrder de O.S antigas ficou preso
                    # em 72h).
                    existing.source_updated_at = now
                if changed:
                    run.updated_count += 1
                else:
                    run.unchanged_count += 1
            except Exception as exc:
                run.rejected_count += 1
                if len(errors) < 50:
                    errors.append({"source_order_id": source_id or None, "reason": str(exc)[:300]})

        run.errors = errors
        run.status = "completed_with_warnings" if run.rejected_count else "completed"
        run.finished_at = datetime.now(timezone.utc)
        db.flush()
        return {
            "run_id": run.id,
            "status": run.status,
            "date_from": run.date_from,
            "date_to": run.date_to,
            "fetched_count": run.fetched_count,
            "created_count": run.created_count,
            "updated_count": run.updated_count,
            "unchanged_count": run.unchanged_count,
            "rejected_count": run.rejected_count,
            "errors": errors,
        }


def import_open_backlog(
    db: Session,
    client: IxcClient,
    *,
    imported_by: int | None,
    sector_ids: list[str],
) -> dict[str, Any]:
    today = datetime.now(OPERATIONS_TIMEZONE).date()
    return import_current_month_period(
        db,
        client,
        date_from=today,
        date_to=today,
        imported_by=imported_by,
        sector_ids=sector_ids,
        open_backlog=True,
    )
