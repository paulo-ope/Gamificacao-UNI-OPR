"""Importação do atendimento REAL do IXC (`su_ticket`) para dentro do módulo Suporte/SGP.

Ver docs/STATUS.md (2026-09-11) para o diagnóstico completo: `su_ticket` é o protocolo que o time
abre na aba Atendimentos do IXC e que dispara a abertura de O.S. - nenhuma O.S. é aberta
diretamente. `su_oss_chamado.id_ticket` referencia de volta este registro (ver
`OperationOrder.ticket_id`). Diferente de `opa_ingestion.py` (atendimento por CHAT do OPA Suite,
outra fonte) - as duas convivem no mesmo módulo por decisão explícita do usuário.

Primeira versão: importação manual por período, upsert idempotente por `source_id`, sem
checkpoint/resume/telemetria de run (ao contrário de `opa_ingestion.import_opa_attendances`) - ver
docstring de `import_tickets_for_period`.
"""

from __future__ import annotations

import contextlib
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.services.ixc_client import (
    IxcClient,
    fetch_assuntos,
    fetch_cidades,
    fetch_clientes_by_ids,
    fetch_customer_contracts_by_customer_ids,
    fetch_setores,
    fetch_tickets,
)
from app.services.regional import is_valid_regional, normalize_regional
from app.services.text_normalize import normalize_place_name

from .models import SupportIxcTicket, SupportIxcTicketRaw

SUPPORT_IXC_TICKET_IMPORT_LOCK_KEY = 913_275_004
logger = logging.getLogger(__name__)


@contextlib.contextmanager
def _ticket_import_lock(db: Session):
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        yield
        return

    waited = 0.0
    acquired = False
    while waited <= 30:
        acquired = bool(
            db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": SUPPORT_IXC_TICKET_IMPORT_LOCK_KEY}).scalar()
        )
        if acquired:
            break
        time.sleep(1)
        waited += 1
    if not acquired:
        raise RuntimeError("Outra importação de atendimento IXC já está em andamento.")
    try:
        yield
    finally:
        # Achado real (2026-09-11, primeiro ciclo em produção): se o corpo do `with` levantar um
        # erro de BANCO (não um erro genérico de rede/Python), a sessão fica marcada como
        # "precisa rollback" e um `db.execute` direto aqui levantaria `PendingRollbackError`,
        # mascarando a exceção original e MATANDO este unlock antes de rodar - o lock ficava
        # concedido pra sempre na conexão, travando todo ciclo seguinte (destravado manualmente
        # via `pg_terminate_backend`). `rollback()` primeiro limpa esse estado antes de tentar
        # desbloquear; o unlock em si nunca deve propagar (senão troca o erro original do
        # chamador por um erro de limpeza, mais difícil de diagnosticar).
        try:
            db.rollback()
            db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": SUPPORT_IXC_TICKET_IMPORT_LOCK_KEY})
        except Exception:
            logger.exception(
                "Falha ao liberar o lock de importação de atendimento IXC - pode ficar preso até a "
                "conexão fechar."
            )


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_ixc_datetime(value: Any) -> datetime | None:
    """`su_ticket.data_criacao`/`data_ultima_alteracao` vêm no formato "YYYY-MM-DD HH:MM:SS" no
    horário local do servidor IXC (não UTC - mesma ressalva de `fetch_latest_service_order_timestamp`
    em ixc_client.py). Marcado como aware em UTC de propósito simplificador: a ingestão bruta não
    faz conversão de fuso, a interpretação correta de período acontece na leitura (mesmo gap já
    documentado para o OPA em docs/plano-analise-opa-suite-atendimentos.md)."""
    text_value = _clean(value)
    if not text_value or text_value.startswith("0000-00-00"):
        return None
    try:
        naive = datetime.strptime(text_value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            naive = datetime.strptime(text_value, "%Y-%m-%d")
        except ValueError:
            return None
    return naive.replace(tzinfo=timezone.utc)


def _cliente_display_name(cliente: dict[str, Any]) -> str | None:
    """Mesma ordem de prioridade de `ixc_importer._cliente_display_name` (razão social > nome
    social > fantasia) - reimplementada aqui em vez de importada pra não acoplar o módulo Suporte
    ao módulo Operações (o projeto já evita essa mistura, ver docs/plano-integracao-opa-suite.md
    item 4)."""
    for field_name in ("razao", "nome_social", "fantasia"):
        value = _clean(cliente.get(field_name))
        if value:
            return value
    return None


def _comparable_value(value: Any) -> Any:
    """SQLite (usado nos testes) não preserva `tzinfo` no round-trip de `DateTime(timezone=True)`
    - sem isso, `created_at`/`source_updated_at` comparariam aware contra naive e marcariam
    "mudou" em toda reimportação, mesmo sem mudança real (mesmo problema já resolvido em
    `opa_ingestion._comparable_value`)."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return value


def _pick_fallback_contract(contracts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Um cliente pode ter mais de um contrato - prioriza o ativo (`status == "A"`); empate (ou
    nenhum ativo) desempata pelo mais recentemente atualizado. Critério simples, documentado como
    tal: não há hoje um "contrato principal" explícito no cadastro do cliente pra usar em vez
    disso."""
    if not contracts:
        return None
    return max(
        contracts,
        key=lambda c: (_clean(c.get("status")) == "A", _clean(c.get("ultima_atualizacao"))),
    )


def _normalize_ticket_record(
    record: dict[str, Any],
    *,
    clientes: dict[int, dict[str, Any]],
    assuntos: dict[int, dict[str, Any]],
    cidades: dict[int, dict[str, Any]],
    contracts_by_customer: dict[int, dict[str, Any]],
    setores: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    cliente = clientes.get(_to_int(record.get("id_cliente")) or -1) or {}
    assunto = assuntos.get(_to_int(record.get("id_assunto")) or -1) or {}
    contract = contracts_by_customer.get(_to_int(record.get("id_cliente")) or -1) or {}
    setor = setores.get(_to_int(record.get("id_ticket_setor")) or -1) or {}

    # Achado real em produção (2026-09-11): `su_ticket.id_filial` às vezes vem com um código
    # inválido (aparece como "NAO IDENTIFICADO" - ~3.500 atendimentos numa amostra de 30 dias),
    # mesmo o cliente tendo um contrato ativo com regional própria. Pedido explícito do usuário:
    # o atendimento é protocolado no cadastro do cliente, que tem um CONTRATO com `id_filial`
    # próprio - usa isso como fallback antes de desistir e marcar como não identificado.
    regional = normalize_regional(_clean(record.get("id_filial")) or None)
    if not is_valid_regional(regional):
        fallback_regional = normalize_regional(_clean(contract.get("id_filial")) or None)
        if is_valid_regional(fallback_regional):
            regional = fallback_regional

    # Achado real em produção (2026-09-11): `cliente.cidade` NÃO é o nome da cidade - é o
    # id_cidade (FK pra tabela `cidade`, mesmo padrão já usado por `ixc_ingestion.py` pra O.S.).
    # Sem resolver isso, a coluna city ficava cheia de códigos numéricos ("20", "3828") em vez do
    # nome, quebrando o drill-down por cidade.
    cliente_cidade = cidades.get(_to_int(cliente.get("cidade")) or -1) or {}
    city = _clean(cliente_cidade.get("nome")) or None
    neighborhood = _clean(cliente.get("bairro")) or None
    # Fallback simétrico: se o CLIENTE não tem cidade/bairro preenchido (raro, mas acontece junto
    # com filial inválida), o CONTRATO tem os dois campos próprios (`cidade`/`bairro`,
    # `cliente_contrato.bairro` confirmado como texto livre, não FK).
    if not city or not neighborhood:
        contract_cidade = cidades.get(_to_int(contract.get("cidade")) or -1) or {}
        if not city:
            city = _clean(contract_cidade.get("nome")) or None
        if not neighborhood:
            neighborhood = _clean(contract.get("bairro")) or None

    return {
        "source_id": _clean(record.get("id")),
        "protocol": _clean(record.get("protocolo")) or None,
        "customer_id": _clean(record.get("id_cliente")) or None,
        "customer_name": _cliente_display_name(cliente),
        "contract_id": _clean(record.get("id_contrato")) or None,
        "regional": regional,
        # Bairro/tipo de localidade vêm do CADASTRO DO CLIENTE por padrão (com fallback pro
        # contrato acima), nunca do campo `endereco` do próprio ticket (texto livre não
        # parseável com segurança - ver docstring de `fetch_tickets` em ixc_client.py).
        "city": city,
        # Bairro é texto livre digitado no cadastro (não FK) - normaliza caixa/espaço antes de
        # gravar, senão "CENTRO"/"Centro"/"centro" viram 3 linhas separadas no drill-down (achado
        # real, 2026-09-12). Ver `app/services/text_normalize.normalize_place_name`.
        "neighborhood": normalize_place_name(neighborhood),
        "locality_type": _clean(cliente.get("tipo_localidade")) or None,
        "subject_id": _clean(record.get("id_assunto")) or None,
        "subject_name": _clean(assunto.get("assunto")) or None,
        "sector_id": _clean(record.get("id_ticket_setor")) or None,
        "sector_name": _clean(setor.get("setor")) or None,
        "status": _clean(record.get("status")) or None,
        "sub_status": _clean(record.get("su_status")) or None,
        "channel_id": _clean(record.get("id_canal_atendimento")) or None,
        "workflow_process_id": _clean(record.get("id_wfl_processo")) or None,
        "priority": _clean(record.get("prioridade")) or None,
        "title": _clean(record.get("titulo")) or None,
        # `menssagem` (grafia original do IXC) é o relato protocolado - pedido explícito do
        # usuário (2026-09-11) pra aparecer no nó final do drill-down. Pode conter PII digitada
        # no texto (nome/telefone do cliente) - ver ressalva na docstring do campo no model.
        "report": _clean(record.get("menssagem")) or None,
        "created_at": _parse_ixc_datetime(record.get("data_criacao")),
        "source_updated_at": _parse_ixc_datetime(record.get("data_ultima_alteracao")),
    }


def import_tickets_for_period(
    db: Session,
    client: IxcClient,
    *,
    created_after: str,
    created_before: str,
    filial_ids: list[str] | None = None,
) -> dict[str, int]:
    """Importa atendimentos IXC (`su_ticket`) de um período, upsert idempotente por `source_id`.

    Enriquecimento em lote (nunca por ticket, mesmo padrão de `ixc_importer.py`): resolve
    `id_cliente` -> cidade/bairro/tipo_localidade via `fetch_clientes_by_ids`, e `id_assunto` ->
    nome via `fetch_assuntos` (mesma tabela `su_oss_assunto` que a O.S. já usa).

    Sem checkpoint/resume/telemetria de run nesta primeira versão (diferente de
    `opa_ingestion.import_opa_attendances`) - adequado para importação manual de um período curto;
    se o backfill completo (552 mil tickets em 2026-09-11) precisar rodar sem supervisão, replicar
    o padrão de `SupportOpaImportRun` antes de automatizar.
    """
    with _ticket_import_lock(db):
        records = list(
            fetch_tickets(client, created_after=created_after, created_before=created_before, filial_ids=filial_ids)
        )

        cliente_ids = sorted({cid for cid in (_to_int(r.get("id_cliente")) for r in records) if cid})
        clientes = {
            cid: c
            for c in fetch_clientes_by_ids(client, cliente_ids)
            if (cid := _to_int(c.get("id"))) is not None
        }

        assunto_ids = {aid for aid in (_to_int(r.get("id_assunto")) for r in records) if aid}
        assuntos: dict[int, dict[str, Any]] = {}
        if assunto_ids:
            for assunto in fetch_assuntos(client):
                assunto_id = _to_int(assunto.get("id"))
                if assunto_id in assunto_ids:
                    assuntos[assunto_id] = assunto

        # `su_ticket.id_ticket_setor` -> `empresa_setor` (mesma tabela que a O.S. já usa via
        # `fetch_setores`) - tabela pequena (~20 setores), busca inteira sempre que houver algum
        # ticket com setor preenchido.
        setor_ids = {sid for sid in (_to_int(r.get("id_ticket_setor")) for r in records) if sid}
        setores: dict[int, dict[str, Any]] = {}
        if setor_ids:
            for setor in fetch_setores(client):
                setor_id = _to_int(setor.get("id"))
                if setor_id in setor_ids:
                    setores[setor_id] = setor

        # `cliente.cidade` é o id_cidade (FK), não o nome - resolvido em lote contra a tabela
        # `cidade` inteira (pequena, ~500 municípios de RO, mesmo padrão de `ixc_ingestion.py`).
        cidades = {
            cid: cidade
            for cidade in fetch_cidades(client)
            if (cid := _to_int(cidade.get("id"))) is not None
        }

        # Fallback de regional/cidade/bairro via contrato do cliente (ver `_normalize_ticket_record`)
        # - só busca contrato pra quem PRECISA (filial inválida ou cidade/bairro ausente do
        # cliente), nunca pro lote inteiro, mesmo espírito de "nunca por ticket" dos outros
        # enriquecimentos.
        fallback_customer_ids = sorted({
            cid
            for record in records
            if (cid := _to_int(record.get("id_cliente")))
            and (
                not is_valid_regional(normalize_regional(_clean(record.get("id_filial")) or None))
                or not _clean((clientes.get(cid) or {}).get("bairro"))
                or not _clean((clientes.get(cid) or {}).get("cidade"))
            )
        })
        contracts_by_customer_raw: dict[int, list[dict[str, Any]]] = {}
        if fallback_customer_ids:
            for contract in fetch_customer_contracts_by_customer_ids(client, fallback_customer_ids):
                contract_customer_id = _to_int(contract.get("id_cliente"))
                if contract_customer_id is not None:
                    contracts_by_customer_raw.setdefault(contract_customer_id, []).append(contract)
        contracts_by_customer = {
            cid: best
            for cid, contracts in contracts_by_customer_raw.items()
            if (best := _pick_fallback_contract(contracts)) is not None
        }

        now = datetime.now(timezone.utc)
        result = {"fetched": len(records), "created": 0, "updated": 0, "unchanged": 0, "rejected": 0}
        comparable_fields = set(SupportIxcTicket.__table__.columns.keys()) - {
            "id", "raw_payload", "first_imported_at", "last_imported_at",
        }

        for record in records:
            payload = _normalize_ticket_record(
                record,
                clientes=clientes,
                assuntos=assuntos,
                cidades=cidades,
                contracts_by_customer=contracts_by_customer,
                setores=setores,
            )
            if not payload["source_id"]:
                result["rejected"] += 1
                continue

            raw = db.scalar(select(SupportIxcTicketRaw).where(SupportIxcTicketRaw.source_id == payload["source_id"]))
            if raw is None:
                db.add(
                    SupportIxcTicketRaw(
                        source_id=payload["source_id"],
                        payload_json=record,
                        created_at=payload["created_at"],
                        source_updated_at=payload["source_updated_at"],
                        synced_at=now,
                    )
                )
            else:
                raw.payload_json = record
                raw.created_at = payload["created_at"]
                raw.source_updated_at = payload["source_updated_at"]
                raw.synced_at = now

            existing = db.scalar(select(SupportIxcTicket).where(SupportIxcTicket.source_id == payload["source_id"]))
            if existing is None:
                db.add(SupportIxcTicket(**payload, raw_payload=record))
                result["created"] += 1
                continue

            changed = False
            for field_name, value in payload.items():
                if field_name not in comparable_fields:
                    continue
                if _comparable_value(getattr(existing, field_name)) != _comparable_value(value):
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
