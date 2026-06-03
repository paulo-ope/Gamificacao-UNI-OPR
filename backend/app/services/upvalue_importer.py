from __future__ import annotations

import hashlib
import io
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

from app.models import Collaborator, ImportRun, ServiceOrder
from app.services.regional import is_valid_regional, normalize_regional
from app.services.sla import normalize_sla_status


SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

UNKNOWN_VALUE = "NAO IDENTIFICADO"


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
        raise ValueError("Formato nao suportado. Envie .xlsx, .xls ou .csv.")

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
            return None, "Data invalida"
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
        return None, "Data invalida"
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


def import_upvalue_service_orders(db: Session, filename: str, contents: bytes) -> dict[str, Any]:
    parsed = read_spreadsheet(filename, contents)
    total_rows = len(parsed.dataframe.index)
    imported = 0
    errors: list[dict[str, Any]] = []

    for offset, (_, row) in enumerate(parsed.dataframe.iterrows(), start=2):
        try:
            payload = build_service_order_payload(row, parsed.mapped_columns, offset)
            collaborator = get_or_create_collaborator(
                db,
                payload.pop("collaborator_name"),
                payload["regional"],
            )
            payload["collaborator_id"] = collaborator.id
            existing = find_existing_service_order(db, payload)
            if existing:
                for field, value in payload.items():
                    setattr(existing, field, value)
            else:
                db.add(ServiceOrder(**payload))
            imported += 1
        except ValueError as exc:
            errors.append({"row": offset, "reason": str(exc), "data": row_to_dict(row)})
        except Exception as exc:
            errors.append({"row": offset, "reason": f"Erro inesperado: {exc}", "data": row_to_dict(row)})

    ignored = len(errors)
    if errors:
        print(f"[UpValue Import] {filename}: imported={imported} ignored={ignored} total={total_rows}")
        for error in errors[:20]:
            print(f"[UpValue Import] row={error['row']} reason={error['reason']} data={error['data']}")

    import_run = ImportRun(
        filename=filename,
        source="upvalue",
        total_rows=total_rows,
        imported_rows=imported,
        ignored_rows=ignored,
        error_rows=ignored,
        detected_columns=parsed.detected_columns,
        mapped_columns=parsed.mapped_columns,
        errors=errors,
    )
    db.add(import_run)
    db.commit()
    db.refresh(import_run)

    return {
        "imported": imported,
        "ignored": ignored,
        "errors": errors,
        "first_errors": errors[:20],
        "detected_columns": parsed.detected_columns,
        "mapped_columns": parsed.mapped_columns,
        "summary": {
            "total_rows": total_rows,
            "valid_rows": imported,
            "invalid_rows": ignored,
        },
        "import_id": import_run.id,
    }


def build_service_order_payload(row: pd.Series, mapped_columns: dict[str, str], row_number: int) -> dict[str, Any]:
    def value(field: str) -> Any:
        column = mapped_columns.get(field)
        if not column:
            return None
        return row.get(column)

    def column(field: str) -> str | None:
        return mapped_columns.get(field)

    opened_at, opened_error = parse_datetime(value("opened_at"))
    closed_at, closed_error = parse_datetime(value("closed_at"))
    scheduled_at, _ = parse_datetime(value("scheduled_at"))
    deadline_at, _ = parse_datetime(value("deadline_at"))
    if opened_at is None and closed_at is not None:
        opened_at = closed_at
    if opened_at is None:
        opened_at = scheduled_at or deadline_at or datetime.now(timezone.utc)

    os_code = normalize_text(value("os_code"))
    contract_id = normalize_text(value("contract_id"))
    customer_login = normalize_text(value("customer_login"))
    os_subject = normalize_text(value("os_subject")) or UNKNOWN_VALUE
    diagnosis = normalize_text(value("diagnosis")) or "Nao informado"
    normalized_diagnosis = normalize_header(diagnosis)
    if not os_code:
        os_code = generated_os_code(customer_login or contract_id, os_subject, opened_at, row_to_dict(row), row_number)

    collaborator_name = normalize_text(value("collaborator")) or UNKNOWN_VALUE

    regional = normalize_regional(normalize_text(value("regional")) or UNKNOWN_VALUE)
    sla_hours = parse_duration_hours(value("sla_hours"), column("sla_hours"))
    closing_time_hours = parse_duration_hours(value("closing_time_hours"), column("closing_time_hours"))
    sla_limit = sla_hours if sla_hours is not None else 24
    closing_time = closing_time_hours if closing_time_hours is not None else 0
    status = normalize_text(value("status"))
    if not status:
        status = "Concluida" if closed_at else "Em andamento"
    sla_status_source = normalize_text(value("sla_status"))
    sla_status = sla_status_source if sla_status_source and parse_number(sla_status_source) is None else ""

    return {
        "os_code": os_code,
        "contract_id": contract_id or UNKNOWN_VALUE,
        "customer_login": customer_login or None,
        "customer_name": normalize_text(value("customer_name")) or "Nao informado",
        "collaborator_name": collaborator_name,
        "regional": regional,
        "os_type": normalize_text(value("os_type")) or UNKNOWN_VALUE,
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
    }


def generated_os_code(contract_id: str, os_subject: str, opened_at: datetime, row_data: dict[str, Any], row_number: int) -> str:
    raw = f"{contract_id}|{os_subject}|{opened_at.isoformat()}|{row_number}|{row_data}".encode("utf-8")
    return f"UPV-{hashlib.sha1(raw).hexdigest()[:14].upper()}"


def get_or_create_collaborator(db: Session, name: str, regional: str) -> Collaborator:
    normalized_name = normalize_header(name)
    collaborators = db.scalars(select(Collaborator)).all()
    for collaborator in collaborators:
        if normalize_header(collaborator.name) == normalized_name:
            if regional and (collaborator.regional != regional or not is_valid_regional(collaborator.regional)):
                collaborator.regional = collaborator.regional or regional
                if not is_valid_regional(collaborator.regional):
                    collaborator.regional = regional
            if not collaborator.active:
                collaborator.active = True
                collaborator.is_registered = False
            return collaborator

    collaborator = Collaborator(
        name=name,
        role="Importado UpValue",
        regional=regional,
        active=True,
        is_registered=False,
    )
    db.add(collaborator)
    db.flush()
    return collaborator


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
