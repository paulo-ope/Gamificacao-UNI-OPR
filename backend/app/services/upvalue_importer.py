from __future__ import annotations

import hashlib
import io
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import Collaborator, ImportRun, ImportServiceOrderAudit, ServiceOrder
from app.services.calculation_closure import find_paid_run_for_service_order_context
from app.services.point_balance import detect_post_payment_warranty_debits
from app.services.regional import is_valid_regional, normalize_regional_grouped as normalize_regional
from app.services.sla import normalize_sla_status


SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

UNKNOWN_VALUE = "NAO IDENTIFICADO"
IMPORT_SUCCESS_STATUSES = {"completed", "completed_with_warnings"}
AUDIT_ACTIONS = {"created", "updated", "skipped", "rejected", "blocked_paid_period", "error"}


UPVALUE_COLUMN_ALIASES: dict[str, list[str]] = {
    "os_code": ["ID O.S.", "ID O.S", "ID da O.S", "O.S.", "O.S", "ID", "Protocolo", "Protocolo da O.S", "Codigo", "Codigo O.S"],
    "contract_id": ["ID Contrato", "ID do Contrato", "Contrato", "Codigo Contrato", "Contrato ID"],
    "customer_login": [
        "Login",
        "Login Cliente",
        "Login do Cliente",
        "Login/Contrato",
        "Contrato/Login",
        "Usuario",
        "Usuario PPPoE",
        "Usuário",
        "Usuário PPPoE",
        "ID Login",
        "Codigo Login",
        "Código Login",
    ],
    "customer_name": ["Cliente", "Pessoa", "1 Nome", "1º Nome", "ID Cliente", "Nome Cliente", "Nome do Cliente", "Assinante"],
    "collaborator": ["Responsavel", "Tecnico", "Colaborador", "Equipe", "Tecnico/Equipe", "Executor"],
    "regional": ["Regional", "Filial", "Unidade", "Base"],
    "os_type": ["Tipo Geral", "Solicitacao", "Tipo", "Tipo da O.S", "Grupo", "Processo", "Departamento", "Setor"],
    "os_subject": ["Assunto", "Descricao Solicitacao", "Assunto da O.S", "Tarefa", "Descricao da Tarefa", "Servico"],
    "diagnosis": [
        "Diagnostico",
        "Diagnostico da O.S",
        "Diagnostico Tecnico",
        "Diagnostico do Atendimento",
        "Motivo Diagnostico",
        "Resultado Diagnostico",
        "Desfecho",
        "Causa",
        "Motivo",
    ],
    "status": ["Status", "Situacao", "Status da O.S"],
    "sla_status": ["Status SLA", "Situacao SLA"],
    "sla_hours": ["SLA Horas", "Tempo SLA", "Horas SLA", "SLA em horas", "SLA", "Min. Estimados", "Min Estimados"],
    "closing_time_hours": [
        "Min. Trabalhados",
        "Min Trabalhados",
        "TMF",
        "T.M. Fechamento",
        "Tempo Medio de Fechamento",
        "Tempo de Fechamento",
        "Tempo Total",
        "Duracao",
    ],
    "opened_at": ["DT Abertura", "Data Abertura", "Data de Abertura", "Abertura", "Criado em"],
    "closed_at": ["DT Fechamento", "Data Fechamento", "Data de Fechamento", "Fechamento", "Finalizado em", "Encerrado em"],
    "scheduled_at": ["DT Agendamento", "Data Agendamento", "Data de Agendamento", "Agendamento"],
    "deadline_at": ["DT Prazo", "Data Prazo", "Data de Prazo", "Prazo"],
    "has_reschedule": ["Reagendamento", "Reagendado", "Qtd Reagendamento", "Quantidade de Reagendamentos"],
    "has_pending": ["Pendencia", "Pendente", "Possui Pendencia"],
    "is_warranty": ["Garantia", "Garantia Ativacao", "Garantia Manutencao", "Dentro da Garantia"],
    "is_recurrence": ["Reincidencia", "Recorrencia", "Retorno 30 dias"],
}


@dataclass
class ParsedSpreadsheet:
    dataframe: pd.DataFrame
    detected_columns: list[str]
    normalized_columns: list[str]
    mapped_columns: dict[str, str]


@dataclass
class ImportRowValidationError(ValueError):
    code: str
    reason: str

    def __str__(self) -> str:
        return self.reason


def normalize_header(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def normalize_text(value: Any) -> str:
    if is_empty(value):
        return ""
    return str(value).strip()


def _normalized_aliases() -> dict[str, list[str]]:
    return {field: [normalize_header(alias) for alias in aliases] for field, aliases in UPVALUE_COLUMN_ALIASES.items()}


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and math.isnan(value):
        return True
    text = str(value).strip()
    return text == "" or normalize_header(text) in {"nan", "nat", "null", "none", "nulo", "na", "n_a"}


def serializable_cell(value: Any) -> Any:
    if is_empty(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except ValueError:
            return str(value)
    return value


def row_to_dict(row: pd.Series) -> dict[str, Any]:
    return {str(column): serializable_cell(row[column]) for column in row.index}


def detect_column_mapping(columns: list[str]) -> tuple[list[str], dict[str, str]]:
    normalized_columns = [normalize_header(column) for column in columns]
    normalized_to_original = {
        normalized: original
        for original, normalized in zip(columns, normalized_columns, strict=False)
        if normalized
    }
    aliases = _normalized_aliases()
    mapped: dict[str, str] = {}

    for field, candidates in aliases.items():
        for candidate in candidates:
            if candidate in normalized_to_original:
                mapped[field] = normalized_to_original[candidate]
                break

    return normalized_columns, mapped


def read_spreadsheet(filename: str, contents: bytes, preview_rows: int | None = None) -> ParsedSpreadsheet:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Formato não suportado. Envie .xlsx, .xls ou .csv.")

    read_kwargs = {"dtype": object}
    if preview_rows is not None:
        read_kwargs["nrows"] = preview_rows

    if extension == ".csv":
        dataframe = _read_csv(contents, read_kwargs)
    elif extension == ".xlsx":
        dataframe = pd.read_excel(io.BytesIO(contents), engine="openpyxl", **read_kwargs)
    else:
        dataframe = pd.read_excel(io.BytesIO(contents), engine="xlrd", **read_kwargs)

    dataframe = dataframe.dropna(how="all")
    dataframe.columns = [str(column).strip() for column in dataframe.columns]
    detected_columns = list(dataframe.columns)
    normalized_columns, mapped_columns = detect_column_mapping(detected_columns)
    mapped_columns = refine_sla_column_mapping(dataframe, mapped_columns)
    return ParsedSpreadsheet(
        dataframe=dataframe,
        detected_columns=detected_columns,
        normalized_columns=normalized_columns,
        mapped_columns=mapped_columns,
    )


def _read_csv(contents: bytes, read_kwargs: dict[str, Any]) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "latin1"):
        try:
            return pd.read_csv(io.BytesIO(contents), sep=None, engine="python", encoding=encoding, **read_kwargs)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(io.BytesIO(contents), sep=None, engine="python", encoding="utf-8", **read_kwargs)


def refine_sla_column_mapping(dataframe: pd.DataFrame, mapped_columns: dict[str, str]) -> dict[str, str]:
    mapped = dict(mapped_columns)
    sla_hours_column = mapped.get("sla_hours")
    if not sla_hours_column or mapped.get("sla_status"):
        return mapped

    values = [value for value in dataframe[sla_hours_column].head(80).tolist() if not is_empty(value)]
    if not values:
        return mapped

    status_count = sum(1 for value in values if normalize_sla_status(value) is not None)
    numeric_count = sum(1 for value in values if parse_number(value) is not None)
    if status_count > 0 and status_count >= numeric_count:
        mapped["sla_status"] = sla_hours_column
        mapped.pop("sla_hours", None)
    return mapped


def parse_number(value: Any) -> float | None:
    if is_empty(value):
        return None
    if isinstance(value, int | float):
        return None if isinstance(value, float) and math.isnan(value) else float(value)

    text = str(value).strip().lower()
    text = (
        text.replace("horas", "h")
        .replace("hora", "h")
        .replace("hrs", "h")
        .replace("hr", "h")
        .replace("minutos", "m")
        .replace("minuto", "m")
        .replace("mins", "m")
        .replace("min", "m")
    )
    text = re.sub(r"\s+", "", text)

    if re.fullmatch(r"\d{1,4}:\d{1,2}(?::\d{1,2})?", text):
        parts = [float(part) for part in text.split(":")]
        if len(parts) == 2:
            hours, minutes = parts
            return hours + (minutes / 60)
        hours, minutes, seconds = parts
        return hours + (minutes / 60) + (seconds / 3600)

    hour_match = re.fullmatch(r"(\d+(?:[,.]\d+)?)h(?:(\d+(?:[,.]\d+)?)m?)?", text)
    if hour_match:
        hours = float(hour_match.group(1).replace(",", "."))
        minutes = hour_match.group(2)
        return hours + (float(minutes.replace(",", ".")) / 60 if minutes else 0)

    minute_match = re.fullmatch(r"(\d+(?:[,.]\d+)?)m", text)
    if minute_match:
        return float(minute_match.group(1).replace(",", ".")) / 60

    text = re.sub(r"[^0-9,.-]", "", text)
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_duration_hours(value: Any, column_name: str | None = None) -> float | None:
    parsed = parse_number(value)
    if parsed is None:
        return None

    normalized_column = normalize_header(column_name)
    normalized_value = normalize_header(value)
    value_has_unit = "h" in normalized_value or normalized_value.endswith("m") or "min" in normalized_value
    if (
        not value_has_unit
        and (normalized_column.startswith("min") or "min_trabalhados" in normalized_column or "min_estimados" in normalized_column)
    ):
        return parsed / 60
    return parsed


def parse_bool(value: Any) -> bool:
    if is_empty(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return float(value) > 0

    text = normalize_header(value)
    truthy = {"sim", "yes", "true", "1", "garantia", "reincidencia", "recorrencia", "reagendado", "pendente"}
    falsy = {"nao", "no", "false", "0", "vazio", "none", "null"}
    if text in truthy:
        return True
    if text in falsy:
        return False
    number = parse_number(value)
    if number is not None:
        return number > 0
    return bool(text)


def parse_datetime(value: Any) -> tuple[datetime | None, str | None]:
    if is_empty(value):
        return None, None
    if isinstance(value, int | float) and not isinstance(value, bool):
        if math.isnan(float(value)):
            return None, None
        numeric = float(value)
        try:
            if 20_000 <= numeric <= 80_000:
                parsed = datetime(1899, 12, 30, tzinfo=timezone.utc) + timedelta(days=numeric)
                return parsed, None
            if numeric > 10_000_000_000:
                return datetime.fromtimestamp(numeric / 1000, tz=timezone.utc), None
            if numeric > 1_000_000_000:
                return datetime.fromtimestamp(numeric, tz=timezone.utc), None
        except (OverflowError, OSError, ValueError):
            return None, "Data inválida"
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value, None

    text = str(value).strip()
    dayfirst = not bool(re.match(r"^\d{4}-\d{2}-\d{2}", text))
    parsed = pd.to_datetime(text, dayfirst=dayfirst, errors="coerce")
    if pd.isna(parsed):
        return None, "Data inválida"
    value = parsed.to_pydatetime()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value, None


def build_preview(filename: str, contents: bytes) -> dict[str, Any]:
    parsed = read_spreadsheet(filename, contents, preview_rows=20)
    return {
        "total_rows": len(parsed.dataframe.index),
        "detected_columns": parsed.detected_columns,
        "normalized_columns": parsed.normalized_columns,
        "mapped_columns": parsed.mapped_columns,
        "sample_rows": [row_to_dict(row) for _, row in parsed.dataframe.head(20).iterrows()],
        "errors": [],
    }


def compute_file_hash(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def has_duplicate_successful_import(db: Session, file_hash: str, exclude_import_run_id: int | None = None) -> bool:
    stmt = (
        select(ImportRun.id)
        .where(ImportRun.file_hash == file_hash)
        .where(ImportRun.status.in_(tuple(IMPORT_SUCCESS_STATUSES)))
        .limit(1)
    )
    if exclude_import_run_id is not None:
        stmt = stmt.where(ImportRun.id != exclude_import_run_id)
    return db.scalar(stmt) is not None


def safe_audit_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        normalized = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    text = str(value).strip()
    return text or None


def normalize_compare_value(field_name: str, value: Any) -> Any:
    if isinstance(value, datetime):
        normalized = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.replace(microsecond=0)
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, str):
        text = value.strip()
        if field_name in {"regional"}:
            return normalize_regional(text)
        if field_name in {"os_code", "contract_id", "customer_login"}:
            return text.upper()
        return text
    return value


def values_differ(field_name: str, old_value: Any, new_value: Any) -> bool:
    return normalize_compare_value(field_name, old_value) != normalize_compare_value(field_name, new_value)


def reference_date_for_payload(payload: dict[str, Any]) -> datetime | None:
    return payload.get("closed_at") or payload.get("opened_at")


def add_import_audit(
    db: Session,
    import_run: ImportRun,
    action: str,
    *,
    os_code: str | None = None,
    service_order_id: int | None = None,
    field_name: str | None = None,
    old_value: Any = None,
    new_value: Any = None,
    reason: str | None = None,
    row_number: int | None = None,
    created_by: int | None = None,
) -> None:
    if action not in AUDIT_ACTIONS:
        raise ValueError(f"Ação de auditoria inválida: {action}")
    db.add(
        ImportServiceOrderAudit(
            import_run_id=import_run.id,
            os_code=os_code,
            service_order_id=service_order_id,
            action=action,
            field_name=field_name,
            old_value=safe_audit_value(old_value),
            new_value=safe_audit_value(new_value),
            reason=reason,
            row_number=row_number,
            created_by=created_by,
        )
    )


def register_row_error(
    errors: list[dict[str, Any]],
    row_number: int,
    reason: str,
    row: pd.Series,
) -> None:
    errors.append({"row": row_number, "reason": reason, "data": row_to_dict(row)})


def build_import_result(import_run: ImportRun) -> dict[str, Any]:
    valid_rows = int(import_run.created_count + import_run.updated_count + import_run.skipped_count)
    invalid_rows = int(import_run.rejected_count + import_run.error_rows + import_run.paid_period_blocked_count)
    return {
        "status": import_run.status,
        "imported": int(import_run.created_count + import_run.updated_count),
        "ignored": int(import_run.skipped_count + import_run.rejected_count + import_run.error_rows + import_run.paid_period_blocked_count),
        "errors": import_run.errors,
        "first_errors": import_run.errors[:20],
        "detected_columns": import_run.detected_columns,
        "mapped_columns": import_run.mapped_columns,
        "summary": {
            "total_rows": int(import_run.total_rows),
            "processed_rows": int(import_run.processed_rows),
            "created_count": int(import_run.created_count),
            "updated_count": int(import_run.updated_count),
            "skipped_count": int(import_run.skipped_count),
            "rejected_count": int(import_run.rejected_count),
            "error_count": int(import_run.error_rows),
            "missing_date_count": int(import_run.missing_date_count),
            "duplicate_count": int(import_run.duplicate_count),
            "unknown_collaborator_count": int(import_run.unknown_collaborator_count),
            "required_field_missing_count": int(import_run.required_field_missing_count),
            "paid_period_blocked_count": int(import_run.paid_period_blocked_count),
            "valid_rows": valid_rows,
            "invalid_rows": invalid_rows,
        },
        "import_id": import_run.id,
        "file_name": import_run.filename,
        "file_hash": import_run.file_hash,
        "message": import_run.notes or import_run.error_message,
    }


def register_failed_import_run(
    db: Session,
    filename: str,
    contents: bytes,
    reason: str,
    imported_by: int | None = None,
) -> ImportRun:
    import_run = ImportRun(
        filename=filename,
        file_hash=compute_file_hash(contents),
        source="upvalue",
        status="failed",
        total_rows=0,
        processed_rows=0,
        imported_rows=0,
        rejected_count=0,
        ignored_rows=0,
        error_rows=1,
        imported_by=imported_by,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        error_message=reason,
        notes="Falha ao processar a importação.",
        detected_columns=[],
        mapped_columns={},
        errors=[{"row": 0, "reason": reason, "data": {"file_name": filename}}],
    )
    db.add(import_run)
    db.flush()
    return import_run


def import_upvalue_service_orders(db: Session, filename: str, contents: bytes, imported_by: int | None = None) -> dict[str, Any]:
    parsed = read_spreadsheet(filename, contents)
    total_rows = len(parsed.dataframe.index)
    file_hash = compute_file_hash(contents)
    errors: list[dict[str, Any]] = []

    import_run = ImportRun(
        filename=filename,
        file_hash=file_hash,
        source="upvalue",
        status="completed",
        total_rows=total_rows,
        detected_columns=parsed.detected_columns,
        mapped_columns=parsed.mapped_columns,
        errors=[],
        imported_by=imported_by,
        started_at=datetime.now(timezone.utc),
        notes=None,
    )
    db.add(import_run)
    db.flush()

    if has_duplicate_successful_import(db, file_hash, exclude_import_run_id=import_run.id):
        import_run.status = "rejected"
        import_run.duplicate_count = 1
        import_run.rejected_count = total_rows or 1
        import_run.ignored_rows = import_run.rejected_count
        import_run.error_rows = 0
        import_run.processed_rows = 0
        import_run.finished_at = datetime.now(timezone.utc)
        import_run.error_message = "Arquivo já importado anteriormente."
        import_run.notes = "Arquivo já importado anteriormente."
        import_run.errors = [
            {
                "row": 0,
                "reason": "Arquivo já importado anteriormente",
                "data": {"file_name": filename, "file_hash": file_hash},
            }
        ]
        return build_import_result(import_run)

    touched_orders: list[ServiceOrder] = []

    for offset, (_, row) in enumerate(parsed.dataframe.iterrows(), start=2):
        try:
            payload = build_service_order_payload(row, parsed.mapped_columns, offset)
            provided_fields = set(payload.pop("__provided_fields__", []))
            collaborator_name = payload.pop("collaborator_name")
            existing = find_existing_service_order(db, payload)
            target_paid_run = find_paid_run_for_service_order_context(
                db,
                (existing.closed_at if existing else None) or (existing.opened_at if existing else None) or reference_date_for_payload(payload),
                existing.regional if existing else payload.get("regional"),
            )
            collaborator = None
            if not target_paid_run and (existing is None or "collaborator" in provided_fields):
                collaborator, created_collaborator = get_or_create_collaborator(
                    db,
                    collaborator_name,
                    payload["regional"],
                )
                if created_collaborator:
                    import_run.unknown_collaborator_count += 1
                payload["collaborator_id"] = collaborator.id
                if "collaborator" in provided_fields:
                    provided_fields.add("collaborator_id")
            if existing:
                changes: list[tuple[str, Any, Any]] = []
                for field, value in payload.items():
                    if field not in provided_fields:
                        continue
                    current_value = getattr(existing, field)
                    if values_differ(field, current_value, value):
                        changes.append((field, current_value, value))
                if not changes:
                    import_run.skipped_count += 1
                    add_import_audit(
                        db,
                        import_run,
                        "skipped",
                        os_code=existing.os_code,
                        service_order_id=existing.id,
                        reason="sem alterações",
                        row_number=offset,
                        created_by=imported_by,
                    )
                elif target_paid_run:
                    import_run.paid_period_blocked_count += 1
                    add_import_audit(
                        db,
                        import_run,
                        "blocked_paid_period",
                        os_code=existing.os_code,
                        service_order_id=existing.id,
                        reason="A O.S pertence a um período já marcado como pago e não foi alterada. Para revisar, crie uma revisão pós-pagamento.",
                        row_number=offset,
                        created_by=imported_by,
                    )
                    register_row_error(
                        errors,
                        offset,
                        "A O.S pertence a um período já marcado como pago e não foi alterada. Para revisar, crie uma revisão pós-pagamento.",
                        row,
                    )
                else:
                    for field, old_value, new_value in changes:
                        setattr(existing, field, new_value)
                        add_import_audit(
                            db,
                            import_run,
                            "updated",
                            os_code=existing.os_code,
                            service_order_id=existing.id,
                            field_name=field,
                            old_value=old_value,
                            new_value=new_value,
                            row_number=offset,
                            created_by=imported_by,
                        )
                    import_run.updated_count += 1
                    touched_orders.append(existing)
            else:
                if target_paid_run:
                    import_run.paid_period_blocked_count += 1
                    add_import_audit(
                        db,
                        import_run,
                        "blocked_paid_period",
                        os_code=payload.get("os_code"),
                        reason="A O.S pertence a um período já marcado como pago e não foi criada. Para revisar, crie uma revisão pós-pagamento.",
                        row_number=offset,
                        created_by=imported_by,
                    )
                    register_row_error(
                        errors,
                        offset,
                        "A O.S pertence a um período já marcado como pago e não foi criada. Para revisar, crie uma revisão pós-pagamento.",
                        row,
                    )
                else:
                    service_order = ServiceOrder(**payload)
                    db.add(service_order)
                    db.flush()
                    add_import_audit(
                        db,
                        import_run,
                        "created",
                        os_code=service_order.os_code,
                        service_order_id=service_order.id,
                        reason="O.S criada pela importação",
                        row_number=offset,
                        created_by=imported_by,
                    )
                    import_run.created_count += 1
                    touched_orders.append(service_order)
            import_run.processed_rows += 1
        except ImportRowValidationError as exc:
            import_run.processed_rows += 1
            import_run.rejected_count += 1
            if exc.code == "missing_date":
                import_run.missing_date_count += 1
            if exc.code == "required_field_missing":
                import_run.required_field_missing_count += 1
            add_import_audit(
                db,
                import_run,
                "rejected",
                reason=exc.reason,
                row_number=offset,
                created_by=imported_by,
            )
            register_row_error(errors, offset, exc.reason, row)
        except Exception as exc:
            import_run.processed_rows += 1
            import_run.error_rows += 1
            add_import_audit(
                db,
                import_run,
                "error",
                reason=f"Erro inesperado: {exc}",
                row_number=offset,
                created_by=imported_by,
            )
            register_row_error(errors, offset, f"Erro inesperado: {exc}", row)

    import_run.imported_rows = import_run.created_count + import_run.updated_count
    import_run.ignored_rows = import_run.skipped_count + import_run.rejected_count + import_run.paid_period_blocked_count + import_run.error_rows
    import_run.errors = errors
    import_run.finished_at = datetime.now(timezone.utc)
    if import_run.error_rows or import_run.rejected_count or import_run.paid_period_blocked_count:
        import_run.status = "completed_with_warnings"
    if not import_run.imported_rows and import_run.duplicate_count:
        import_run.status = "rejected"

    if errors:
        print(
            f"[UpValue Import] {filename}: created={import_run.created_count} updated={import_run.updated_count} "
            f"skipped={import_run.skipped_count} rejected={import_run.rejected_count} "
            f"blocked_paid={import_run.paid_period_blocked_count} errors={import_run.error_rows} total={total_rows}"
        )
        for error in errors[:20]:
            print(f"[UpValue Import] row={error['row']} reason={error['reason']} data={error['data']}")

    import_run.notes = (
        "Importação concluída com alertas."
        if import_run.status == "completed_with_warnings"
        else "Importação concluída com sucesso."
    )

    if touched_orders:
        detect_post_payment_warranty_debits(db, touched_orders, triggered_by=imported_by)

    return build_import_result(import_run)


def build_service_order_payload(row: pd.Series, mapped_columns: dict[str, str], row_number: int) -> dict[str, Any]:
    def value(field: str) -> Any:
        column = mapped_columns.get(field)
        if not column:
            return None
        return row.get(column)

    def column(field: str) -> str | None:
        return mapped_columns.get(field)

    provided_fields: set[str] = set()
    for field_name in [
        "os_code",
        "contract_id",
        "customer_login",
        "customer_name",
        "collaborator",
        "regional",
        "os_type",
        "os_subject",
        "diagnosis",
        "status",
        "sla_status",
        "sla_hours",
        "closing_time_hours",
        "opened_at",
        "closed_at",
        "scheduled_at",
        "deadline_at",
        "has_reschedule",
        "has_pending",
        "is_warranty",
        "is_recurrence",
    ]:
        if column(field_name):
            provided_fields.add(field_name)

    opened_at, opened_error = parse_datetime(value("opened_at"))
    closed_at, closed_error = parse_datetime(value("closed_at"))
    scheduled_at, _ = parse_datetime(value("scheduled_at"))
    deadline_at, _ = parse_datetime(value("deadline_at"))
    if opened_at is None and closed_at is not None:
        opened_at = closed_at
    if opened_at is None:
        opened_at = scheduled_at or deadline_at

    os_code = normalize_text(value("os_code"))
    contract_id = normalize_text(value("contract_id"))
    customer_login = normalize_text(value("customer_login"))
    os_subject = normalize_text(value("os_subject")) or UNKNOWN_VALUE
    diagnosis = normalize_text(value("diagnosis")) or "Não informado"
    os_type = normalize_text(value("os_type")) or UNKNOWN_VALUE
    customer_name = normalize_text(value("customer_name")) or "Não informado"
    collaborator_name = normalize_text(value("collaborator")) or UNKNOWN_VALUE
    regional = normalize_regional(normalize_text(value("regional")) or UNKNOWN_VALUE)
    sla_hours = parse_duration_hours(value("sla_hours"), column("sla_hours"))
    closing_time_hours = parse_duration_hours(value("closing_time_hours"), column("closing_time_hours"))
    sla_limit = sla_hours if sla_hours is not None else 24
    closing_time = closing_time_hours if closing_time_hours is not None else 0
    status = normalize_text(value("status"))
    if not status:
        status = "Concluída" if closed_at else "Em andamento"
    sla_status_source = normalize_text(value("sla_status"))
    sla_status = sla_status_source if sla_status_source and parse_number(sla_status_source) is None else ""

    if not any([opened_at, closed_at, scheduled_at, deadline_at]):
        raise ImportRowValidationError("missing_date", "O.S sem data de referência")
    if opened_at is None:
        raise ImportRowValidationError("missing_date", "O.S sem data de referência")

    if not os_code:
        os_code = generated_os_code(customer_login or contract_id, os_subject, opened_at, row_to_dict(row), row_number)

    return {
        "os_code": os_code,
        "contract_id": contract_id or UNKNOWN_VALUE,
        "customer_login": customer_login or None,
        "customer_name": customer_name,
        "collaborator_name": collaborator_name,
        "regional": regional,
        "os_type": os_type,
        "os_subject": os_subject,
        "diagnosis": diagnosis,
        "status": status,
        "sla_status": sla_status or ("Dentro do prazo" if closing_time <= sla_limit else "Fora do prazo"),
        "sla_hours": sla_hours,
        "closing_time_hours": closing_time_hours,
        "opened_at": opened_at,
        "closed_at": closed_at,
        "is_warranty": parse_bool(value("is_warranty")),
        "is_recurrence": parse_bool(value("is_recurrence")),
        "is_priority": bool(sla_hours is not None and sla_hours <= 6),
        "has_reschedule": parse_bool(value("has_reschedule")),
        "has_pending": parse_bool(value("has_pending")),
        "__provided_fields__": sorted(provided_fields),
    }


def generated_os_code(contract_id: str, os_subject: str, opened_at: datetime, row_data: dict[str, Any], row_number: int) -> str:
    raw = f"{contract_id}|{os_subject}|{opened_at.isoformat()}|{row_number}|{row_data}".encode("utf-8")
    return f"UPV-{hashlib.sha1(raw).hexdigest()[:14].upper()}"


def get_or_create_collaborator(
    db: Session, name: str, regional: str, *, collaborators_cache: list[Collaborator] | None = None
) -> tuple[Collaborator, bool]:
    """`collaborators_cache`, se informado, evita buscar todos os colaboradores do banco a cada chamada -
    quem passar deve ter carregado a lista uma vez por rodada de importação e reaproveitado aqui (importa
    muito em lotes grandes, ex. importação retroativa da API do IXC com dezenas de milhares de O.S.). Sem
    isso, mantém o comportamento de sempre (busca do zero) - não muda nada para quem já chama sem o cache."""
    normalized_name = normalize_header(name)
    collaborators = collaborators_cache if collaborators_cache is not None else db.scalars(select(Collaborator)).all()
    for collaborator in collaborators:
        if normalize_header(collaborator.name) == normalized_name:
            if regional and (collaborator.regional != regional or not is_valid_regional(collaborator.regional)):
                collaborator.regional = collaborator.regional or regional
                if not is_valid_regional(collaborator.regional):
                    collaborator.regional = regional
            if not collaborator.active:
                # Achado real: forcar is_registered=False aqui derrubava o cadastro de quem tinha
                # sido desativado temporariamente pela tela (ex.: licenca) SEM passar pela exclusao
                # (que ja zera is_registered explicitamente) - a pessoa reaparecia sem pontuar/pagar
                # ate alguem notar e recadastrar na mao. Reativar so deve reverter o active; o
                # cadastro que ja existia (ou nao) fica como estava.
                collaborator.active = True
            return collaborator, False

    collaborator = Collaborator(
        name=name,
        role="Importado UpValue",
        regional=regional,
        active=True,
        is_registered=False,
    )
    db.add(collaborator)
    db.flush()
    if collaborators_cache is not None:
        collaborators_cache.append(collaborator)
    return collaborator, True


def find_existing_service_order(db: Session, payload: dict[str, Any]) -> ServiceOrder | None:
    os_code = payload.get("os_code")
    if os_code:
        existing = db.scalar(select(ServiceOrder).where(ServiceOrder.os_code == os_code))
        if existing:
            return existing

    identity_clause = (
        ServiceOrder.customer_login == payload["customer_login"]
        if payload.get("customer_login")
        else ServiceOrder.contract_id == payload["contract_id"]
    )

    return db.scalar(
        select(ServiceOrder).where(
            and_(
                identity_clause,
                ServiceOrder.os_subject == payload["os_subject"],
                ServiceOrder.opened_at == payload["opened_at"],
            )
        )
    )
