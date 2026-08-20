from __future__ import annotations

import contextlib
import logging
import time
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import exists, or_, select, text, update
from sqlalchemy.orm import Session

from app.services.opa_client import OpaClient

from .models import SupportOpaAttendance, SupportOpaAttendanceRaw, SupportOpaDimension, SupportOpaImportRun


SUPPORT_OPA_IMPORT_LOCK_KEY = 913_275_003
SUPPORT_OPA_PAGE_LIMIT = 100
SUPPORT_OPA_PAGE_RETRIES = 3
logger = logging.getLogger(__name__)


class OpaImportInterrupted(RuntimeError):
    def __init__(self, message: str, *, run_id: int) -> None:
        super().__init__(message)
        self.run_id = run_id


def _clean(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _first(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record
        for part in key.split("."):
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(part)
        text = _clean(value)
        if text:
            return text
    return ""


def _first_list_dict(record: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = record.get(key)
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, dict):
            return item
    return None


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: object) -> datetime | None:
    text_value = _clean(value)
    if not text_value or text_value in {"0000-00-00", "0000-00-00 00:00:00"}:
        return None
    candidates = [
        text_value,
        text_value.replace("Z", "+00:00"),
        text_value.replace(" ", "T"),
    ]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text_value, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _comparable_value(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return value


def _duration_seconds(record: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = _first(record, key)
        parsed = _int_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _computed_duration_seconds(started_at: datetime | None, finished_at: datetime | None) -> int | None:
    if started_at is None or finished_at is None:
        return None
    seconds = int((finished_at - started_at).total_seconds())
    return seconds if seconds >= 0 else None


def _evaluation_rating(record: dict[str, Any]) -> float | None:
    direct = _float_or_none(_first(record, "avaliacao", "rating", "nota", "satisfacao"))
    if direct is not None:
        return direct
    evaluations = record.get("evaluations")
    if not isinstance(evaluations, list):
        return None
    ratings: list[float] = []
    for item in evaluations:
        if not isinstance(item, dict):
            continue
        rating = _float_or_none(_first(item, "likert.rating", "rating", "nota"))
        if rating is not None:
            ratings.append(rating)
    if not ratings:
        return None
    return sum(ratings) / len(ratings)


def _dimension_id(record: dict[str, Any]) -> str:
    return _first(record, "_id", "id", "codigo", "idMotivo", "value")


def _dimension_name(record: dict[str, Any]) -> str:
    return _first(record, "nome", "name", "fantasia", "razao", "razao_social", "motivo", "descricao", "description", "titulo", "title", "email")


def _sync_dimension_records(
    db: Session,
    *,
    dimension_type: str,
    records: list[dict[str, Any]],
    now: datetime,
) -> None:
    for record in records:
        source_id = _dimension_id(record)
        if not source_id:
            continue
        existing = db.scalar(
            select(SupportOpaDimension).where(
                SupportOpaDimension.dimension_type == dimension_type,
                SupportOpaDimension.source_id == source_id,
            )
        )
        name = _dimension_name(record) or None
        if existing is None:
            db.add(
                SupportOpaDimension(
                    dimension_type=dimension_type,
                    source_id=source_id,
                    name=name,
                    payload_json=record,
                    synced_at=now,
                )
            )
        else:
            existing.name = name
            existing.payload_json = record
            existing.synced_at = now


def _load_dimension_map(db: Session, dimension_type: str) -> dict[str, str]:
    rows = db.scalars(
        select(SupportOpaDimension).where(
            SupportOpaDimension.dimension_type == dimension_type,
            SupportOpaDimension.name.isnot(None),
        )
    ).all()
    return {row.source_id: row.name for row in rows if row.name}


def _sync_opa_dimensions(db: Session, client: OpaClient, now: datetime) -> dict[str, dict[str, str]]:
    collectors = {
        "user": client.list_users,
        "reason": client.list_reasons,
        "department": client.list_departments,
        "tag": client.list_tags,
        "customer": client.list_clients,
    }
    for dimension_type, collector in collectors.items():
        try:
            _sync_dimension_records(
                db,
                dimension_type=dimension_type,
                records=collector(),
                now=now,
            )
        except Exception as exc:
            logger.warning("falha_sincronizar_dimensao_opa type=%s erro=%s", dimension_type, exc)
    db.flush()
    _backfill_customer_names(db)
    return {
        "user": _load_dimension_map(db, "user"),
        "reason": _load_dimension_map(db, "reason"),
        "department": _load_dimension_map(db, "department"),
        "tag": _load_dimension_map(db, "tag"),
        "customer": _load_dimension_map(db, "customer"),
    }


def _lookup_dimension(dimensions: dict[str, dict[str, str]], dimension_type: str, source_id: str | None) -> str | None:
    if not source_id:
        return None
    return dimensions.get(dimension_type, {}).get(source_id)


def _backfill_customer_names(db: Session) -> None:
    customer_name = (
        select(SupportOpaDimension.name)
        .where(
            SupportOpaDimension.dimension_type == "customer",
            SupportOpaDimension.source_id == SupportOpaAttendance.customer_id,
            SupportOpaDimension.name.isnot(None),
        )
        .limit(1)
        .scalar_subquery()
    )
    customer_exists = exists().where(
        SupportOpaDimension.dimension_type == "customer",
        SupportOpaDimension.source_id == SupportOpaAttendance.customer_id,
        SupportOpaDimension.name.isnot(None),
    )
    db.execute(
        update(SupportOpaAttendance)
        .where(
            SupportOpaAttendance.customer_id.isnot(None),
            or_(SupportOpaAttendance.customer_name.is_(None), SupportOpaAttendance.customer_name == ""),
            customer_exists,
        )
        .values(customer_name=customer_name)
    )


def _normalize_attendance(record: dict[str, Any], dimensions: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    dimensions = dimensions or {}
    source_id = _first(record, "id", "_id", "id_atendimento", "atendimento_id", "codigo", "protocolo")
    if not source_id:
        raise ValueError("Atendimento sem identificador no OPA Suite.")

    opened_at = _parse_datetime(
        _first(record, "data_abertura", "dataAbertura", "created_at", "createdAt", "abertura", "inicio", "date")
    )
    if opened_at is None:
        raise ValueError("Atendimento sem data de abertura válida.")

    closed_at = _parse_datetime(
        _first(record, "data_encerramento", "dataEncerramento", "closed_at", "closedAt", "encerramento", "fim")
    )
    first_response_at = _parse_datetime(
        _first(record, "primeira_resposta", "first_response_at", "firstResponseAt", "data_primeira_resposta")
    )
    source_updated_at = _parse_datetime(
        _first(record, "updated_at", "updatedAt", "ultima_atualizacao", "data_atualizacao")
    )
    reason = _first_list_dict(record, "motivos") or {}
    attendant_id = _first(record, "id_atendente", "atendente.id", "usuario.id", "attendant.id") or None
    department_id = _first(record, "departamento.id", "setor.id", "department.id", "id_departamento", "setor_id", "setor") or None
    reason_id = _first(record, "motivo.id", "reason.id", "id_motivo", "motivo_id") or _first(reason, "idMotivo", "_id", "id") or None
    customer_id = _first(record, "id_cliente._id", "id_cliente.id", "id_cliente", "cliente._id", "cliente.id", "customer.id", "cliente_id") or None
    tma_seconds = _duration_seconds(record, "tma_seconds", "tmaSegundos", "tempo_medio_atendimento_segundos", "tma")

    return {
        "source_id": source_id,
        "protocol": _first(record, "protocolo", "protocol", "codigo_protocolo") or None,
        "customer_id": customer_id,
        "customer_name": _first(
            record,
            "id_cliente.nome",
            "id_cliente.fantasia",
            "id_cliente.razao",
            "id_cliente.razao_social",
            "cliente.nome",
            "cliente.fantasia",
            "cliente.razao",
            "cliente.razao_social",
            "customer.name",
            "customer.nome",
            "customer.fantasia",
            "nome_cliente",
            "fantasia_cliente",
            "razao_cliente",
        )
        or _lookup_dimension(dimensions, "customer", customer_id),
        "attendant_id": attendant_id,
        "attendant_name": _first(record, "atendente.nome", "usuario.nome", "attendant.name", "nome_atendente", "atendente")
        or _lookup_dimension(dimensions, "user", attendant_id),
        "department_id": department_id,
        "department_name": _first(record, "departamento.nome", "setor.nome", "department.name", "nome_departamento")
        or _lookup_dimension(dimensions, "department", department_id),
        "reason_id": reason_id,
        "reason_name": _first(record, "motivo.nome", "motivo.descricao", "reason.name", "nome_motivo", "motivo")
        or _first(reason, "nome", "motivo", "descricao")
        or _lookup_dimension(dimensions, "reason", reason_id),
        "channel": _first(record, "canal", "channel") or None,
        "channel_id": _first(record, "canal_id", "channel_id", "channel.id") or None,
        "channel_customer": _first(record, "canal_cliente", "channel_customer", "telefone", "phone") or None,
        "status": _first(record, "status.nome", "status.descricao", "status") or None,
        "opened_at": opened_at,
        "closed_at": closed_at,
        "first_response_at": first_response_at,
        "rating": _evaluation_rating(record),
        "tma_seconds": tma_seconds if tma_seconds is not None else _computed_duration_seconds(opened_at, closed_at),
        "tmr_seconds": _duration_seconds(record, "tmr_seconds", "tmrSegundos", "tempo_medio_resposta_segundos", "tmr"),
        "source_updated_at": source_updated_at,
        "raw_payload": record,
    }


@contextlib.contextmanager
def _support_opa_import_lock(db: Session):
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        yield
        return

    waited = 0.0
    acquired = False
    while waited <= 30:
        acquired = bool(db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": SUPPORT_OPA_IMPORT_LOCK_KEY}).scalar())
        if acquired:
            break
        time.sleep(1)
        waited += 1
    if not acquired:
        raise RuntimeError("Outra importação do OPA Suite já está em andamento.")
    try:
        yield
    finally:
        db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": SUPPORT_OPA_IMPORT_LOCK_KEY})


def _fetch_attendance_page_with_retry(
    client: OpaClient,
    *,
    date_from: date,
    date_to: date,
    limit: int,
    skip: int,
):
    last_exc: Exception | None = None
    for attempt in range(1, SUPPORT_OPA_PAGE_RETRIES + 1):
        try:
            return client.list_attendances(
                opened_after=date_from.isoformat(),
                opened_before=date_to.isoformat(),
                limit=limit,
                skip=skip,
            )
        except Exception as exc:
            last_exc = exc
            if attempt >= SUPPORT_OPA_PAGE_RETRIES:
                break
            time.sleep(min(attempt, 5))
    assert last_exc is not None
    raise last_exc


def _run_result(run: SupportOpaImportRun) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "status": run.status,
        "date_from": run.date_from,
        "date_to": run.date_to,
        "pages_processed": run.pages_processed,
        "fetched_count": run.fetched_count,
        "created_count": run.created_count,
        "updated_count": run.updated_count,
        "unchanged_count": run.unchanged_count,
        "rejected_count": run.rejected_count,
        "errors": run.errors or [],
    }


def _process_attendance_pages(
    db: Session,
    client: OpaClient,
    *,
    run: SupportOpaImportRun,
    start_skip: int,
    started_mono: float,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    dimensions = _sync_opa_dimensions(db, client, now)
    errors: list[dict[str, Any]] = list(run.errors or [])
    comparable_fields = set(SupportOpaAttendance.__table__.columns.keys()) - {
        "id",
        "first_imported_at",
        "last_imported_at",
    }

    skip = start_skip
    row_number = run.fetched_count
    try:
        while True:
            page = _fetch_attendance_page_with_retry(
                client,
                date_from=run.date_from,
                date_to=run.date_to,
                limit=run.page_limit,
                skip=skip,
            )
            if not page.records:
                run.checkpoint_json = {
                    "skip": skip,
                    "next_skip": skip,
                    "page_limit": run.page_limit,
                    "finished_reason": "empty_page",
                }
                break

            run.fetched_count += len(page.records)

            for record in page.records:
                row_number += 1
                try:
                    payload = _normalize_attendance(record, dimensions)
                    if payload["opened_at"].date() < run.date_from or payload["opened_at"].date() > run.date_to:
                        raise ValueError("Atendimento fora do período solicitado; a API OPA pode ter ignorado o filtro de data.")

                    raw = db.scalar(
                        select(SupportOpaAttendanceRaw).where(
                            SupportOpaAttendanceRaw.source_id == payload["source_id"]
                        )
                    )
                    if raw is None:
                        db.add(
                            SupportOpaAttendanceRaw(
                                source_id=payload["source_id"],
                                payload_json=record,
                                opened_at=payload["opened_at"],
                                closed_at=payload["closed_at"],
                                source_updated_at=payload["source_updated_at"],
                                synced_at=now,
                            )
                        )
                    else:
                        raw.payload_json = record
                        raw.opened_at = payload["opened_at"]
                        raw.closed_at = payload["closed_at"]
                        raw.source_updated_at = payload["source_updated_at"]
                        raw.synced_at = now

                    existing = db.scalar(
                        select(SupportOpaAttendance).where(SupportOpaAttendance.source_id == payload["source_id"])
                    )
                    if existing is None:
                        db.add(SupportOpaAttendance(**payload))
                        run.created_count += 1
                        continue

                    changed = False
                    for field_name, value in payload.items():
                        if field_name not in comparable_fields:
                            continue
                        if _comparable_value(getattr(existing, field_name)) != _comparable_value(value):
                            setattr(existing, field_name, value)
                            changed = True
                    existing.last_imported_at = now
                    if changed:
                        run.updated_count += 1
                    else:
                        run.unchanged_count += 1
                except Exception as exc:
                    run.rejected_count += 1
                    if len(errors) < 50:
                        errors.append({"row": row_number, "reason": str(exc)[:300]})

            run.pages_processed += 1
            skip += len(page.records)
            run.next_skip = skip
            run.checkpoint_json = {
                "skip": skip - len(page.records),
                "next_skip": skip,
                "page_limit": run.page_limit,
                "last_page_records": len(page.records),
                "total": page.total,
            }
            run.errors = errors
            db.flush()

            if page.total is not None and skip >= page.total:
                run.checkpoint_json = {
                    **run.checkpoint_json,
                    "finished_reason": "total_reached",
                }
                break
            if len(page.records) < run.page_limit:
                run.checkpoint_json = {
                    **run.checkpoint_json,
                    "finished_reason": "short_page",
                }
                break
    except Exception as exc:
        run.errors = errors
        run.status = "interrupted" if run.next_skip > start_skip else "failed"
        run.last_error = str(exc)[:500]
        run.finished_at = datetime.now(timezone.utc)
        run.duration_ms = round((time.monotonic() - started_mono) * 1000)
        db.flush()
        if run.status == "interrupted":
            raise OpaImportInterrupted(str(exc), run_id=run.id) from exc
        raise

    run.errors = errors
    run.status = "completed_with_warnings" if run.rejected_count else "completed"
    run.finished_at = datetime.now(timezone.utc)
    run.duration_ms = round((time.monotonic() - started_mono) * 1000)
    run.last_error = None
    db.flush()
    return _run_result(run)


def import_opa_attendances(
    db: Session,
    client: OpaClient,
    *,
    date_from: date,
    date_to: date,
    imported_by: int | None,
) -> dict[str, Any]:
    if date_from > date_to:
        raise ValueError("A data inicial não pode ser maior que a data final.")

    with _support_opa_import_lock(db):
        started_mono = time.monotonic()
        run = SupportOpaImportRun(
            provider="opa",
            entity="attendance",
            mode="manual" if imported_by is not None else "scheduled",
            date_from=date_from,
            date_to=date_to,
            status="running",
            page_limit=SUPPORT_OPA_PAGE_LIMIT,
            next_skip=0,
            checkpoint_json={"skip": 0, "page_limit": SUPPORT_OPA_PAGE_LIMIT},
            imported_by=imported_by,
        )
        db.add(run)
        db.flush()
        return _process_attendance_pages(
            db,
            client,
            run=run,
            start_skip=0,
            started_mono=started_mono,
        )


def resume_opa_import_run(
    db: Session,
    client: OpaClient,
    *,
    run_id: int,
    imported_by: int | None,
) -> dict[str, Any]:
    with _support_opa_import_lock(db):
        run = db.get(SupportOpaImportRun, run_id)
        if run is None:
            raise ValueError("Run de importação OPA não encontrada.")
        if run.status in {"completed", "completed_with_warnings"}:
            raise ValueError("Run concluída não pode ser retomada.")
        if run.status == "running":
            raise RuntimeError("Run de importação OPA já está em execução.")
        if run.next_skip <= 0:
            raise ValueError("Run não possui checkpoint válido para retomada.")

        started_mono = time.monotonic()
        run.status = "running"
        run.mode = "resume"
        run.imported_by = imported_by
        run.finished_at = None
        run.last_error = None
        run.checkpoint_json = {
            **(run.checkpoint_json or {}),
            "resume_started_at": datetime.now(timezone.utc).isoformat(),
            "resume_from_skip": run.next_skip,
        }
        db.flush()
        return _process_attendance_pages(
            db,
            client,
            run=run,
            start_skip=run.next_skip,
            started_mono=started_mono,
        )
