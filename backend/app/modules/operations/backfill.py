from __future__ import annotations

import argparse
import time
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.ixc_client import IxcApiError, get_ixc_client
from app.services.regional import normalize_regional

from .ixc_ingestion import (
    _clean,
    _fetch_lookup_by_ids,
    _first,
    _status_label,
    _to_int,
    import_current_month_period,
)
from .models import OperationBackfillJob, OperationOpenBacklogJob, OperationOrder
from .period import OPERATIONS_TIMEZONE
from .scope import PRIMARY_IXC_SECTOR_IDS


def _new_job(
    db: Session,
    date_from: date,
    date_to: date,
    sector_ids: list[str],
    *,
    requested_by: int | None = None,
) -> OperationBackfillJob:
    if date_from > date_to:
        raise ValueError("A data inicial do backfill deve ser menor ou igual à data final.")
    job = OperationBackfillJob(
        date_from=date_from,
        date_to=date_to,
        next_date=date_from,
        sector_ids=sector_ids,
        status="pending",
        total_days=(date_to - date_from).days + 1,
        requested_by=requested_by,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def create_backfill_job(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    sector_ids: list[str],
    requested_by: int | None,
) -> OperationBackfillJob:
    return _new_job(
        db,
        date_from,
        date_to,
        list(dict.fromkeys(sector_ids)),
        requested_by=requested_by,
    )


def run_backfill(
    db: Session,
    *,
    date_from: date,
    date_to: date,
    sector_ids: list[str],
    resume_job_id: int | None = None,
    delay_seconds: float = 0.5,
) -> OperationBackfillJob:
    job = db.get(OperationBackfillJob, resume_job_id) if resume_job_id else None
    if resume_job_id and job is None:
        raise ValueError(f"Backfill {resume_job_id} não encontrado.")
    if job is None:
        job = _new_job(db, date_from, date_to, list(dict.fromkeys(sector_ids)))
    if job.status == "completed":
        return job

    client = get_ixc_client()
    job.status = "running"
    job.updated_at = datetime.now(timezone.utc)
    db.commit()

    current = job.next_date
    while current <= job.date_to:
        lock_retries = 0
        api_retries = 0
        try:
            while True:
                try:
                    result = import_current_month_period(
                        db,
                        client,
                        date_from=current,
                        date_to=current,
                        imported_by=job.requested_by,
                        sector_ids=list(job.sector_ids),
                    )
                    break
                except IxcApiError as exc:
                    # Soluços de rede com o IXC (conexão derrubada, timeout) são passageiros e não
                    # devem matar um backfill de meses inteiro por um único dia. Sem este retry, o
                    # job morria e ficava "failed" parado, exigindo retomada manual pela tela.
                    # Precisa vir antes do except RuntimeError abaixo: IxcApiError é subclasse dele.
                    if api_retries >= 5:
                        raise
                    api_retries += 1
                    wait_seconds = 15 * api_retries
                    print(
                        f"backfill_job={job.id} day={current.isoformat()} falha de rede no IXC, "
                        f"tentativa {api_retries}/5, aguardando {wait_seconds}s... ({exc})",
                        flush=True,
                    )
                    db.rollback()
                    time.sleep(wait_seconds)
                except RuntimeError as exc:
                    # Outro import (ciclo automático, clique manual na UI) segurou o lock global
                    # nesse instante - é contenção passageira, não um erro real do dia. Sem este
                    # retry, um backfill de meses inteiro morria por causa de um choque de alguns
                    # segundos com outro processo, e a retomada tinha que ser feita na mão de novo.
                    if "já está em andamento" not in str(exc) or lock_retries >= 5:
                        raise
                    lock_retries += 1
                    wait_seconds = 15 * lock_retries
                    print(
                        f"backfill_job={job.id} day={current.isoformat()} lock ocupado, "
                        f"tentativa {lock_retries}/5, aguardando {wait_seconds}s...",
                        flush=True,
                    )
                    db.rollback()
                    time.sleep(wait_seconds)
            job.fetched_count += result["fetched_count"]
            job.created_count += result["created_count"]
            job.updated_count += result["updated_count"]
            job.unchanged_count += result["unchanged_count"]
            job.rejected_count += result["rejected_count"]
            if result["errors"]:
                job.errors = [*job.errors, {"date": current.isoformat(), "items": result["errors"]}][-100:]
            job.processed_days += 1
            next_day = current + timedelta(days=1)
            job.next_date = next_day
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
            print(
                f"backfill_job={job.id} day={current.isoformat()} "
                f"progress={job.processed_days}/{job.total_days} fetched={result['fetched_count']} "
                f"created={result['created_count']} updated={result['updated_count']} rejected={result['rejected_count']}",
                flush=True,
            )
            current = next_day
            if current <= job.date_to and delay_seconds > 0:
                time.sleep(delay_seconds)
        except Exception as exc:
            db.rollback()
            job = db.get(OperationBackfillJob, job.id)
            job.status = "failed"
            job.updated_at = datetime.now(timezone.utc)
            job.errors = [*job.errors, {"date": current.isoformat(), "reason": str(exc)[:500]}][-100:]
            db.commit()
            raise

    job.status = "completed"
    job.finished_at = datetime.now(timezone.utc)
    job.updated_at = job.finished_at
    db.commit()
    db.refresh(job)
    return job


def create_open_backlog_job(
    db: Session,
    *,
    sector_ids: list[str],
    requested_by: int | None,
) -> OperationOpenBacklogJob:
    deduped = list(dict.fromkeys(sector_ids))
    if not deduped:
        raise ValueError("Informe ao menos um setor para a varredura de backlog aberto.")
    job = OperationOpenBacklogJob(
        sector_ids=deduped,
        status="pending",
        total_sectors=len(deduped),
        requested_by=requested_by,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def run_open_backlog_job(
    db: Session,
    *,
    job_id: int,
    delay_seconds: float = 0.25,
) -> OperationOpenBacklogJob:
    """Roda (ou retoma) um job de varredura de backlog aberto, um setor por vez - mesmo padrão de
    retomada/retry de `run_backfill`, só que particionando por setor em vez de por dia, já que o
    backlog aberto não tem recorte de data. Cada setor já é internamente particionado por status e,
    quando necessário, por faixa de id (ver `ixc_ingestion._fetch_open_backlog_records`)."""
    job = db.get(OperationOpenBacklogJob, job_id)
    if job is None:
        raise ValueError(f"Job de backlog aberto {job_id} não encontrado.")
    if job.status == "completed":
        return job

    client = get_ixc_client()
    job.status = "running"
    job.updated_at = datetime.now(timezone.utc)
    db.commit()

    today = datetime.now(OPERATIONS_TIMEZONE).date()
    pending_sector_ids = list(job.sector_ids)[job.processed_sectors :]
    for sector_id in pending_sector_ids:
        lock_retries = 0
        api_retries = 0
        try:
            while True:
                try:
                    result = import_current_month_period(
                        db,
                        client,
                        date_from=today,
                        date_to=today,
                        imported_by=job.requested_by,
                        sector_ids=[sector_id],
                        open_backlog=True,
                    )
                    break
                except IxcApiError as exc:
                    # Mesmo raciocínio de run_backfill: soluço passageiro de rede com o IXC não deve
                    # matar a varredura inteira por causa de um único setor.
                    if api_retries >= 5:
                        raise
                    api_retries += 1
                    wait_seconds = 15 * api_retries
                    print(
                        f"open_backlog_job={job.id} sector={sector_id} falha de rede no IXC, "
                        f"tentativa {api_retries}/5, aguardando {wait_seconds}s... ({exc})",
                        flush=True,
                    )
                    db.rollback()
                    time.sleep(wait_seconds)
                except RuntimeError as exc:
                    if "já está em andamento" not in str(exc) or lock_retries >= 5:
                        raise
                    lock_retries += 1
                    wait_seconds = 15 * lock_retries
                    print(
                        f"open_backlog_job={job.id} sector={sector_id} lock ocupado, "
                        f"tentativa {lock_retries}/5, aguardando {wait_seconds}s...",
                        flush=True,
                    )
                    db.rollback()
                    time.sleep(wait_seconds)
            job.fetched_count += result["fetched_count"]
            job.created_count += result["created_count"]
            job.updated_count += result["updated_count"]
            job.unchanged_count += result["unchanged_count"]
            job.rejected_count += result["rejected_count"]
            if result["errors"]:
                job.errors = [*job.errors, {"sector_id": sector_id, "items": result["errors"]}][-100:]
            job.processed_sectors += 1
            job.updated_at = datetime.now(timezone.utc)
            db.commit()
            print(
                f"open_backlog_job={job.id} sector={sector_id} "
                f"progress={job.processed_sectors}/{job.total_sectors} fetched={result['fetched_count']} "
                f"created={result['created_count']} updated={result['updated_count']} rejected={result['rejected_count']}",
                flush=True,
            )
            if delay_seconds > 0:
                time.sleep(delay_seconds)
        except Exception as exc:
            db.rollback()
            job = db.get(OperationOpenBacklogJob, job.id)
            job.status = "failed"
            job.updated_at = datetime.now(timezone.utc)
            job.errors = [*job.errors, {"sector_id": sector_id, "reason": str(exc)[:500]}][-100:]
            db.commit()
            raise

    job.status = "completed"
    job.finished_at = datetime.now(timezone.utc)
    job.updated_at = job.finished_at
    db.commit()
    db.refresh(job)
    return job


def repair_existing_dimensions(db: Session) -> dict[str, int]:
    orders = list(db.scalars(select(OperationOrder).order_by(OperationOrder.id)))
    client = get_ixc_client()
    records = [order.raw_payload or {} for order in orders]

    customer_ids = {_to_int(record.get("id_cliente")) for record in records}
    login_ids = {_to_int(record.get("id_login")) for record in records}
    customers = _fetch_lookup_by_ids(client, "cliente", (item for item in customer_ids if item is not None))
    logins = _fetch_lookup_by_ids(client, "radusuarios", (item for item in login_ids if item is not None))
    city_ids = {
        city_id
        for customer in customers.values()
        if (city_id := _to_int(customer.get("id_cidade") or customer.get("cidade"))) is not None
    }
    cities = _fetch_lookup_by_ids(client, "cidade", city_ids)
    state_ids = {
        state_id
        for city in cities.values()
        if (state_id := _to_int(city.get("uf"))) is not None
    }
    state_ids.update(
        state_id
        for customer in customers.values()
        if (state_id := _to_int(customer.get("uf"))) is not None
    )
    states = _fetch_lookup_by_ids(client, "uf", state_ids)
    contract_ids = {
        contract_id
        for login in logins.values()
        if (contract_id := _to_int(login.get("id_contrato"))) is not None
    }
    contracts = _fetch_lookup_by_ids(client, "cliente_contrato", contract_ids)

    changed = 0
    for index, order in enumerate(orders, start=1):
        record = order.raw_payload or {}
        customer = customers.get(_to_int(record.get("id_cliente")) or -1)
        login = logins.get(_to_int(record.get("id_login")) or -1)
        city_id = _to_int((customer or {}).get("id_cidade") or (customer or {}).get("cidade"))
        city = cities.get(city_id or -1)
        state_id = _to_int((city or {}).get("uf") or (customer or {}).get("uf"))
        state = states.get(state_id or -1)
        contract_id = _to_int((login or {}).get("id_contrato") or record.get("id_contrato"))
        contract = contracts.get(contract_id or -1)
        person_code = _first(customer, "tipo_pessoa", "tipo_cliente").upper()
        normalized = {
            "city": _first(city, "nome", "cidade") or None,
            "state": _first(state, "sigla", "nome") or None,
            "person_type": {"F": "Pessoa Física", "J": "Pessoa Jurídica"}.get(person_code, person_code) or None,
            "contract_type": _first(contract, "contrato", "descricao", "nome") or None,
            "regional": normalize_regional(_clean(record.get("id_filial")) or None),
            "status": _status_label(_clean(record.get("status")), bool(order.closed_at or order.is_closed)),
            "responsible_ixc_id": _to_int(record.get("id_tecnico")),
        }
        if any(getattr(order, field) != value for field, value in normalized.items()):
            for field, value in normalized.items():
                setattr(order, field, value)
            changed += 1
        if index % 500 == 0:
            db.commit()
            print(f"normalization_repair={index}/{len(orders)} changed={changed}", flush=True)
    db.commit()
    return {"scanned": len(orders), "changed": changed}


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill retomável do módulo Operação Analítica.")
    parser.add_argument("--date-from", type=_parse_date)
    parser.add_argument("--date-to", type=_parse_date)
    parser.add_argument("--sector-ids", nargs="+", default=list(PRIMARY_IXC_SECTOR_IDS))
    parser.add_argument("--resume-job", type=int)
    parser.add_argument("--delay-seconds", type=float, default=0.5)
    parser.add_argument("--repair-existing", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.repair_existing:
            print(repair_existing_dimensions(db), flush=True)
            return
        if not args.date_from or not args.date_to:
            parser.error("--date-from e --date-to são obrigatórios para o backfill.")
        job = run_backfill(
            db,
            date_from=args.date_from,
            date_to=args.date_to,
            sector_ids=args.sector_ids,
            resume_job_id=args.resume_job,
            delay_seconds=args.delay_seconds,
        )
        print(
            f"backfill_job={job.id} status={job.status} progress={job.processed_days}/{job.total_days} "
            f"created={job.created_count} updated={job.updated_count} rejected={job.rejected_count}",
            flush=True,
        )


if __name__ == "__main__":
    main()
