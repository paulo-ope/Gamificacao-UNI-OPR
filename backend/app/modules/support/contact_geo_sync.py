"""Resolve de onde fala o cliente de cada atendimento do OPA (cidade, bairro, regional, coordenadas).

O cadastro do cliente no OPA carrega o `id` do cliente no IXC (`payload_json["id"]` da dimensão
`customer`; validado em 2026-10-20 contra os tickets do IXC). Com esse `id` o cadastro do IXC dá
cidade/bairro/regional, pela mesma regra que `ixc_ticket_ingestion._normalize_ticket_record` usa
para os tickets. A resolução é feita UMA vez por cliente e guardada em `SupportContactGeo`: nenhuma
chamada nova ao OPA e o IXC é consultado em lote, só para clientes ainda não resolvidos.

Não grava CPF, telefone nem texto de mensagem."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.ixc_client import (
    IxcClient,
    fetch_cidades,
    fetch_clientes_by_ids,
    fetch_customer_contracts_by_customer_ids,
)
from app.services.regional import is_valid_regional, normalize_regional
from app.services.text_normalize import normalize_place_name

from .ixc_ticket_ingestion import _clean, _pick_fallback_contract, _to_int
from .models import SupportContactGeo, SupportOpaAttendance, SupportOpaDimension

logger = logging.getLogger(__name__)

# Atendimentos mais antigos que isso não entram no radar, então não vale resolver o cliente deles.
LOOKBACK_DAYS = 35
# Clientes resolvidos por ciclo: o primeiro ciclo é o maior (~60 mil clientes nos últimos 35 dias) e
# vai se esgotando em vários ciclos, do atendimento mais recente para o mais antigo.
BATCH_CUSTOMERS = 1500
IXC_CHUNK = 200
RETRY_NOT_FOUND_AFTER = timedelta(days=7)
# A tabela `cidade` do IXC tem ~7 mil linhas (73 páginas, ~15 s) e quase nunca muda: baixar a cada
# ciclo seria desperdício. Cache de processo com validade de 24 h.
CIDADES_CACHE_SECONDS = 24 * 3600
_cidades_cache: tuple[float, dict[int, dict[str, Any]]] | None = None
STATUS_OK = "ok"
STATUS_NOT_FOUND = "not_found"


def _coordinate(value: Any, *, low: float, high: float) -> float | None:
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high and number != 0 else None


def _coordinates(opa_payload: dict[str, Any]) -> tuple[float | None, float | None]:
    """Latitude/longitude do cadastro do OPA; descarta valor fora do Brasil (cadastro com coordenada
    zerada ou trocada) em vez de plotar o cliente no meio do oceano."""
    latitude = _coordinate(opa_payload.get("latitude"), low=-34.0, high=6.0)
    longitude = _coordinate(opa_payload.get("longitude"), low=-74.0, high=-34.0)
    if latitude is None or longitude is None:
        return None, None
    return latitude, longitude


def resolve_location(
    cliente: dict[str, Any],
    contract: dict[str, Any] | None,
    cidades: dict[int, dict[str, Any]],
    opa_payload: dict[str, Any],
) -> dict[str, Any]:
    """Cidade/bairro/regional de um cliente. Mesma ordem dos tickets: cadastro do cliente primeiro,
    contrato como fallback; a regional vem do contrato (o cliente não tem filial própria) e, se o
    contrato não tiver filial válida, da filial do cadastro do OPA."""
    contract = contract or {}
    city = _clean((cidades.get(_to_int(cliente.get("cidade")) or -1) or {}).get("nome")) or None
    neighborhood = _clean(cliente.get("bairro")) or None
    if not city:
        city = _clean((cidades.get(_to_int(contract.get("cidade")) or -1) or {}).get("nome")) or None
    if not neighborhood:
        neighborhood = _clean(contract.get("bairro")) or None

    regional: str | None = None
    for candidate in (contract.get("id_filial"), opa_payload.get("id_filial")):
        normalized = normalize_regional(_clean(candidate) or None)
        if is_valid_regional(normalized):
            regional = normalized
            break

    latitude, longitude = _coordinates(opa_payload)
    return {
        "regional": regional,
        "city": city,
        "neighborhood": normalize_place_name(neighborhood),
        "latitude": latitude,
        "longitude": longitude,
    }


def _load_cidades(client: IxcClient) -> dict[int, dict[str, Any]]:
    global _cidades_cache
    if _cidades_cache is not None and time.monotonic() - _cidades_cache[0] < CIDADES_CACHE_SECONDS:
        return _cidades_cache[1]
    cidades = {
        cid: cidade
        for cidade in fetch_cidades(client)
        if (cid := _to_int(cidade.get("id"))) is not None
    }
    _cidades_cache = (time.monotonic(), cidades)
    return cidades


def _pending_customers(db: Session, now: datetime, limit: int) -> list[tuple[str, dict[str, Any]]]:
    """Clientes com atendimento recente que ainda não têm localização (ou cujo "não achado" já
    passou do prazo de nova tentativa), do atendimento mais recente para o mais antigo."""
    cutoff = now - timedelta(days=LOOKBACK_DAYS)
    retry_before = now - RETRY_NOT_FOUND_AFTER
    customer_ids = db.scalars(
        select(SupportOpaAttendance.customer_id)
        .join(
            SupportOpaDimension,
            (SupportOpaDimension.dimension_type == "customer")
            & (SupportOpaDimension.source_id == SupportOpaAttendance.customer_id),
        )
        .outerjoin(SupportContactGeo, SupportContactGeo.opa_customer_id == SupportOpaAttendance.customer_id)
        .where(
            SupportOpaAttendance.opened_at >= cutoff,
            SupportOpaAttendance.customer_id.is_not(None),
            (SupportContactGeo.id.is_(None))
            | ((SupportContactGeo.status == STATUS_NOT_FOUND) & (SupportContactGeo.resolved_at < retry_before)),
        )
        # JSON não tem igualdade no Postgres, então o payload sai numa segunda consulta, não no GROUP BY.
        .group_by(SupportOpaAttendance.customer_id)
        .order_by(func.max(SupportOpaAttendance.opened_at).desc())
        .limit(limit)
    ).all()
    if not customer_ids:
        return []
    payloads = dict(
        db.execute(
            select(SupportOpaDimension.source_id, SupportOpaDimension.payload_json).where(
                SupportOpaDimension.dimension_type == "customer",
                SupportOpaDimension.source_id.in_(customer_ids),
            )
        ).all()
    )
    return [(customer_id, payloads.get(customer_id) or {}) for customer_id in customer_ids]


def sync_contact_geo(
    db: Session,
    client: IxcClient,
    *,
    now: datetime | None = None,
    limit: int = BATCH_CUSTOMERS,
) -> dict[str, int]:
    """Resolve até `limit` clientes pendentes. Faz flush, não commit (quem chama decide)."""
    now = now or datetime.now(timezone.utc)
    result = {"pending": 0, "resolved": 0, "not_found": 0, "no_ixc_id": 0}

    pending = _pending_customers(db, now, limit)
    result["pending"] = len(pending)
    if not pending:
        return result

    # `id` do cadastro do OPA = `id_cliente` do IXC. Cliente sem `id` numérico (prospect/fornecedor
    # cadastrado só no OPA) não existe no IXC e não tem como ser localizado.
    by_ixc_id: dict[int, list[tuple[str, dict[str, Any]]]] = {}
    for opa_customer_id, payload in pending:
        ixc_id = _to_int(payload.get("id"))
        if ixc_id is None:
            _upsert(db, opa_customer_id, None, STATUS_NOT_FOUND, {}, now)
            result["no_ixc_id"] += 1
            continue
        by_ixc_id.setdefault(ixc_id, []).append((opa_customer_id, payload))

    if by_ixc_id:
        cidades = _load_cidades(client)
        ixc_ids = sorted(by_ixc_id)
        for start in range(0, len(ixc_ids), IXC_CHUNK):
            chunk = ixc_ids[start : start + IXC_CHUNK]
            clientes = {
                cid: cliente
                for cliente in fetch_clientes_by_ids(client, chunk)
                if (cid := _to_int(cliente.get("id"))) is not None
            }
            contracts_raw: dict[int, list[dict[str, Any]]] = {}
            for contract in fetch_customer_contracts_by_customer_ids(client, chunk):
                cid = _to_int(contract.get("id_cliente"))
                if cid is not None:
                    contracts_raw.setdefault(cid, []).append(contract)
            for ixc_id in chunk:
                cliente = clientes.get(ixc_id)
                for opa_customer_id, payload in by_ixc_id[ixc_id]:
                    if cliente is None:
                        _upsert(db, opa_customer_id, str(ixc_id), STATUS_NOT_FOUND, {}, now)
                        result["not_found"] += 1
                        continue
                    location = resolve_location(
                        cliente, _pick_fallback_contract(contracts_raw.get(ixc_id, [])), cidades, payload
                    )
                    _upsert(db, opa_customer_id, str(ixc_id), STATUS_OK, location, now)
                    result["resolved"] += 1
            db.flush()
    db.flush()
    logger.info("Radar de Contatos: localização de clientes resolvida: %s", result)
    return result


def _upsert(
    db: Session,
    opa_customer_id: str,
    ixc_customer_id: str | None,
    status: str,
    location: dict[str, Any],
    now: datetime,
) -> None:
    row = db.scalar(select(SupportContactGeo).where(SupportContactGeo.opa_customer_id == opa_customer_id))
    if row is None:
        row = SupportContactGeo(opa_customer_id=opa_customer_id)
        db.add(row)
    row.ixc_customer_id = ixc_customer_id
    row.status = status
    row.regional = location.get("regional")
    row.city = location.get("city")
    row.neighborhood = location.get("neighborhood")
    row.latitude = location.get("latitude")
    row.longitude = location.get("longitude")
    row.resolved_at = now
