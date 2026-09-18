"""Importação da base de contratos de cliente do IXC (`cliente_contrato`) por regional.

Ver docs/STATUS.md (2026-09-11): denominador de "atendimento por 1.000 clientes" - cadastro puro,
sem O.S./atendimento, sincronizado à parte. Enum de `status`/`status_internet` ainda não confirmado
(ver docstring de `fetch_customer_contracts` em ixc_client.py) - esta ingestão só normaliza e
persiste o código cru, não classifica "ativo/inativo".
"""

from __future__ import annotations

import contextlib
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.services.ixc_client import IxcClient, fetch_cidades, fetch_clientes_by_ids, fetch_customer_contracts
from app.services.regional import normalize_regional
from app.services.text_normalize import normalize_place_name

from .models import OperationCustomerContract

OPERATIONS_CUSTOMER_CONTRACT_IMPORT_LOCK_KEY = 913_275_005
logger = logging.getLogger(__name__)


@contextlib.contextmanager
def _customer_contract_import_lock(db: Session):
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        yield
        return

    waited = 0.0
    acquired = False
    while waited <= 30:
        acquired = bool(
            db.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": OPERATIONS_CUSTOMER_CONTRACT_IMPORT_LOCK_KEY}
            ).scalar()
        )
        if acquired:
            break
        time.sleep(1)
        waited += 1
    if not acquired:
        raise RuntimeError("Outra importação de contratos de cliente já está em andamento.")
    try:
        yield
    finally:
        # Mesmo achado real de `support/ixc_ticket_ingestion._ticket_import_lock` (2026-09-11): um
        # erro de banco dentro do `with` deixa a sessão precisando de rollback, e chamar
        # `db.execute` direto aqui levantaria `PendingRollbackError`, matando o unlock e deixando
        # o lock concedido pra sempre na conexão. `rollback()` primeiro limpa esse estado; o
        # unlock em si nunca deve propagar por cima do erro original do chamador.
        try:
            db.rollback()
            db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": OPERATIONS_CUSTOMER_CONTRACT_IMPORT_LOCK_KEY})
        except Exception:
            logger.exception(
                "Falha ao liberar o lock de importação de contratos de cliente - pode ficar preso "
                "até a conexão fechar."
            )


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_contract_record(
    record: dict[str, Any],
    *,
    cidades: dict[int, dict[str, Any]],
    clientes: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    # Achado real em produção (2026-09-11): `cliente_contrato.cidade` NÃO é o nome da cidade - é
    # o id_cidade (FK pra tabela `cidade`), mesmo caso já corrigido em
    # `ixc_ticket_ingestion._normalize_ticket_record`. Sem resolver isso, virava código numérico
    # solto no drill-down por cidade.
    contract_cidade = cidades.get(_to_int(record.get("cidade")) or -1) or {}
    city = _clean(contract_cidade.get("nome")) or None
    # `bairro` é campo próprio do contrato (texto livre, não FK) - diferente de `cidade`,
    # não precisa resolver contra outra tabela.
    neighborhood = _clean(record.get("bairro")) or None

    # Achado real em produção (2026-09-11, pedido explícito do usuário depois de eu ter desistido
    # cedo demais): `cliente_contrato.cidade` vem "0" (vazio) na GRANDE maioria dos contratos, mas
    # o CADASTRO do cliente (`cliente.cidade`/`cliente.bairro`) tem a informação em praticamente
    # 100% de uma amostra real de 10 contratos sem cidade no próprio campo - confirmado ao vivo
    # contra a API. Fallback simétrico ao que `ixc_ticket_ingestion.py` já faz (lá o contrato é
    # fallback do cliente; aqui o cliente é fallback do contrato) - nunca inventa, só busca no
    # cadastro que já tem o dado antes de desistir e marcar "sem cidade".
    if not city or not neighborhood:
        cliente = clientes.get(_to_int(record.get("id_cliente")) or -1) or {}
        if not city:
            cliente_cidade = cidades.get(_to_int(cliente.get("cidade")) or -1) or {}
            city = _clean(cliente_cidade.get("nome")) or None
        if not neighborhood:
            neighborhood = _clean(cliente.get("bairro")) or None

    return {
        "source_contract_id": _clean(record.get("id")),
        "customer_id": _clean(record.get("id_cliente")) or None,
        "regional": normalize_regional(_clean(record.get("id_filial")) or None),
        "city": city,
        # Bairro é texto livre (não FK) - normaliza caixa/espaço antes de gravar, mesmo achado de
        # `ixc_ticket_ingestion.py` (2026-09-12): sem isso "CENTRO"/"Centro"/"centro" fragmentam
        # o drill-down em linhas separadas.
        "neighborhood": normalize_place_name(neighborhood),
        "status": _clean(record.get("status")) or None,
        "status_internet": _clean(record.get("status_internet")) or None,
    }


def import_customer_contracts(
    db: Session,
    client: IxcClient,
    *,
    filial_ids: list[str] | None = None,
) -> dict[str, int]:
    """Importa `cliente_contrato` do IXC, upsert idempotente por `source_contract_id`.

    Sem filtro de período - é um snapshot de cadastro, não um fluxo temporal. Chamar de novo
    reimporta e atualiza o que mudou; nunca cria duplicata (mesma chave de upsert de
    `import_tickets_for_period`)."""
    with _customer_contract_import_lock(db):
        records = list(fetch_customer_contracts(client, filial_ids=filial_ids))

        cidades = {
            cid: cidade
            for cidade in fetch_cidades(client)
            if (cid := _to_int(cidade.get("id"))) is not None
        }

        # Fallback de cidade/bairro via cadastro do cliente (ver `_normalize_contract_record`) -
        # só busca quem PRECISA (contrato sem cidade OU sem bairro), em lotes pequenos (não um IN
        # gigante numa chamada só) - achado real 2026-09-11: chamadas muito grandes ao IXC já
        # falharam com "Connection refused"/"Server disconnected" nesta sessão.
        fallback_customer_ids = sorted({
            cid
            for record in records
            if (cid := _to_int(record.get("id_cliente")))
            and (not _clean(record.get("cidade")) or record.get("cidade") == "0" or not _clean(record.get("bairro")))
        })
        clientes: dict[int, dict[str, Any]] = {}
        _CLIENTE_FALLBACK_CHUNK_SIZE = 500
        for offset in range(0, len(fallback_customer_ids), _CLIENTE_FALLBACK_CHUNK_SIZE):
            chunk = fallback_customer_ids[offset : offset + _CLIENTE_FALLBACK_CHUNK_SIZE]
            for cliente in fetch_clientes_by_ids(client, chunk):
                cliente_id = _to_int(cliente.get("id"))
                if cliente_id is not None:
                    clientes[cliente_id] = cliente

        now = datetime.now(timezone.utc)
        result = {"fetched": len(records), "created": 0, "updated": 0, "unchanged": 0, "rejected": 0}
        comparable_fields = set(OperationCustomerContract.__table__.columns.keys()) - {
            "id", "raw_payload", "first_imported_at", "last_imported_at",
        }

        for record in records:
            payload = _normalize_contract_record(record, cidades=cidades, clientes=clientes)
            if not payload["source_contract_id"]:
                result["rejected"] += 1
                continue

            existing = db.scalar(
                select(OperationCustomerContract).where(
                    OperationCustomerContract.source_contract_id == payload["source_contract_id"]
                )
            )
            if existing is None:
                db.add(OperationCustomerContract(**payload, raw_payload=record))
                result["created"] += 1
                continue

            changed = False
            for field_name, value in payload.items():
                if field_name not in comparable_fields:
                    continue
                if getattr(existing, field_name) != value:
                    setattr(existing, field_name, value)
                    changed = True
            if existing.raw_payload != record:
                existing.raw_payload = record
                changed = True
            existing.last_imported_at = now
            if changed:
                result["updated"] += 1
            else:
                result["unchanged"] += 1

        db.commit()
        return result
