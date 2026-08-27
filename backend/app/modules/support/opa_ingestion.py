from __future__ import annotations

import calendar
import contextlib
import logging
import time
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import exists, func, or_, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.opa_client import OpaClient, get_opa_client

from . import opa_attendant_overrides
from .models import (
    SupportOpaAttendance,
    SupportOpaAttendanceRaw,
    SupportOpaDimension,
    SupportOpaImportMonth,
    SupportOpaImportRun,
)
from .opa_filters import TAG_SEPARATOR


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


def _tag_ids_text(record: dict[str, Any]) -> str:
    """Projeta `tags[].id_tag` do payload bruto numa string delimitada pronta
    pra filtro (ver `SupportOpaAttendance.tag_ids_text`). Sempre devolve pelo
    menos o separador sozinho (",") — string vazia significaria "não sei", e
    aqui a gente sabe: o atendimento simplesmente não tem etiqueta."""
    tags = record.get("tags")
    if not isinstance(tags, list):
        return TAG_SEPARATOR
    ids = []
    for tag in tags:
        if not isinstance(tag, dict):
            continue
        tag_id = tag.get("id_tag") or tag.get("_id") or tag.get("id")
        if tag_id and str(tag_id) not in ids:
            ids.append(str(tag_id))
    if not ids:
        return TAG_SEPARATOR
    return f"{TAG_SEPARATOR}{TAG_SEPARATOR.join(ids)}{TAG_SEPARATOR}"


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


def _message_timestamp(message: dict[str, Any]) -> datetime | None:
    return _parse_datetime(_first(message, "data", "createdAt"))


def _message_is_from_client(message: dict[str, Any]) -> bool:
    return bool(message.get("id_user")) and not message.get("id_atend")


def _message_is_from_human_attendant(message: dict[str, Any], human_attendant_ids: set[str]) -> bool:
    attendant_id = message.get("id_atend")
    return bool(attendant_id) and attendant_id in human_attendant_ids


def _load_attendant_types(db: Session) -> dict[str, str]:
    """Mapa source_id -> `attendant_type` resolvido (ex.: "bot", "user"), já
    aplicando o cadastro manual de agente virtual por cima da dimensão sincronizada
    do OPA Suite (`/api/v1/usuario`) — ver `opa_attendant_overrides.resolve_attendant_type`
    pra prioridade. Um atendente sem override e ausente da dimensão (nunca
    sincronizado) simplesmente não aparece aqui — suas mensagens ficam como "tipo
    desconhecido" em quem consome este mapa, nunca classificadas como bot nem como
    humano. Zero chamada nova à API: overrides são uma tabela local."""
    rows = db.execute(
        select(SupportOpaDimension.source_id, SupportOpaDimension.payload_json).where(
            SupportOpaDimension.dimension_type == "user",
        )
    ).all()
    opa_types = {
        source_id: payload.get("tipo")
        for source_id, payload in rows
        if isinstance(payload, dict) and payload.get("tipo")
    }
    overrides = opa_attendant_overrides.load_active_overrides(db)

    resolved: dict[str, str] = {}
    for attendant_id in set(opa_types) | set(overrides):
        attendant_type = opa_attendant_overrides.resolve_attendant_type(
            attendant_id, opa_types.get(attendant_id), overrides
        )
        if attendant_type:
            resolved[attendant_id] = attendant_type
    return resolved


def _human_attendant_ids(attendant_types: dict[str, str]) -> set[str]:
    return {source_id for source_id, tipo in attendant_types.items() if tipo != "bot"}


def _classify_bot_human(
    messages: list[dict[str, Any]], attendant_types: dict[str, str]
) -> tuple[bool | None, bool | None, bool | None]:
    """Classifica participação de bot/humano e handoff a partir das MESMAS
    mensagens já buscadas para o TMR (`_human_response_metrics`) — sem nenhuma
    chamada extra à API do OPA Suite. Retorna
    (handled_by_bot, reached_human, bot_to_human_handoff).

    Qualquer valor `None` significa dado insuficiente para classificar (sem
    mensagens recuperáveis, ou nenhum atendente com `tipo` conhecido na
    conversa) — NUNCA interpretar `None` como `False`. `bot_to_human_handoff`
    só é `True` quando existe uma mensagem de bot com timestamp anterior à
    primeira mensagem humana confirmada; caso contrário (bot sem humano, humano
    sem bot, ou nenhum dos dois) é `False`, nunca inferido sem validar a ordem
    real das mensagens.
    """
    classified: list[tuple[str, datetime]] = []
    for message in messages:
        timestamp = _message_timestamp(message)
        if timestamp is None:
            continue
        attendant_id = message.get("id_atend")
        if not attendant_id:
            continue
        attendant_type = attendant_types.get(attendant_id)
        if attendant_type == "bot":
            classified.append(("bot", timestamp))
        elif attendant_type is not None:
            classified.append(("human", timestamp))
        # tipo desconhecido (atendente ainda não sincronizado): mensagem ignorada.

    if not classified:
        return None, None, None

    handled_by_bot = any(role == "bot" for role, _ in classified)
    reached_human = any(role == "human" for role, _ in classified)
    if handled_by_bot and reached_human:
        first_human_at = min(ts for role, ts in classified if role == "human")
        first_bot_at = min(ts for role, ts in classified if role == "bot")
        handoff = first_bot_at < first_human_at
    else:
        handoff = False
    return handled_by_bot, reached_human, handoff


def _message_attendant_summary(
    messages: list[dict[str, Any]], attendant_types: dict[str, str]
) -> dict[str, Any]:
    """Resumo mínimo de quem respondeu (humano) a partir das MESMAS mensagens já
    buscadas pro TMR/classificação bot-humano — zero chamada extra à API do OPA
    Suite. Existe só pra preparar uma comparação futura sobre handoff/atendente
    real (o total de atendimentos por atendente diverge do painel oficial do
    OPA — ver docs/roteiro-comparacao-tmr-opa-suite.md, seção 10.3), NÃO altera
    nenhum cálculo de TMA/TMR/bot-humano existente.

    Mesmo critério de classificação de `_classify_bot_human`: tipo "bot" conta
    como bot, tipo conhecido diferente de bot conta como humano, tipo
    desconhecido (atendente não sincronizado) é ignorado — nunca tratado como
    bot nem como humano. Mensagem de humano sem timestamp parseável entra na
    contagem mas não participa da ordenação primeiro/último (mesmo critério de
    `_classify_bot_human`, que também descarta timestamp ausente).

    Lista de mensagens vazia -> tudo `None` (dado insuficiente, mesmo critério
    de `_classify_bot_human` pra `classified` vazio) — não dá pra distinguir
    "atendimento sem mensagem nenhuma" de "API não devolveu nada pra esse
    atendimento", então nunca vira zero por padrão. Já com mensagens
    presentes, `*_message_count` é uma contagem real (pode ser `0` de
    verdade, ex.: atendimento só de bot tem `human_message_count == 0`)."""
    if not messages:
        return {
            "distinct_human_attendant_ids": None,
            "first_human_attendant_id": None,
            "last_human_attendant_id": None,
            "human_message_count": None,
            "bot_message_count": None,
            "client_message_count": None,
        }

    human_timestamped: list[tuple[str, datetime]] = []
    human_count = 0
    bot_count = 0
    client_count = 0
    for message in messages:
        if _message_is_from_client(message):
            client_count += 1
            continue
        attendant_id = message.get("id_atend")
        if not attendant_id:
            continue
        attendant_type = attendant_types.get(attendant_id)
        if attendant_type == "bot":
            bot_count += 1
        elif attendant_type is not None:
            human_count += 1
            timestamp = _message_timestamp(message)
            if timestamp is not None:
                human_timestamped.append((attendant_id, timestamp))
        # tipo desconhecido: mensagem não contabilizada (mesmo critério de _classify_bot_human).

    human_timestamped.sort(key=lambda item: item[1])
    distinct_ids = sorted({attendant_id for attendant_id, _ in human_timestamped})

    return {
        "distinct_human_attendant_ids": distinct_ids or None,
        "first_human_attendant_id": human_timestamped[0][0] if human_timestamped else None,
        "last_human_attendant_id": human_timestamped[-1][0] if human_timestamped else None,
        "human_message_count": human_count,
        "bot_message_count": bot_count,
        "client_message_count": client_count,
    }


def _human_response_metrics(
    messages: list[dict[str, Any]], human_attendant_ids: set[str]
) -> tuple[int | None, datetime | None]:
    """TMR = média dos intervalos entre uma mensagem do cliente e a resposta do
    nosso atendente HUMANO seguinte (id_rota == atendimento). Mensagens de bot são
    ignoradas — não fecham o intervalo pendente nem contam como resposta, conforme
    regra: 'não considerar mensagens automáticas como resposta humana'. Retorna
    também o instante da primeira resposta humana da conversa inteira, separado da
    média das respostas seguintes."""
    timestamped: list[tuple[str, datetime]] = []
    for message in messages:
        timestamp = _message_timestamp(message)
        if timestamp is None:
            continue
        if _message_is_from_client(message):
            timestamped.append(("client", timestamp))
        elif _message_is_from_human_attendant(message, human_attendant_ids):
            timestamped.append(("human", timestamp))
        # mensagens de bot (id_atend fora de human_attendant_ids) são descartadas.
    timestamped.sort(key=lambda item: item[1])

    gaps: list[float] = []
    first_response_at: datetime | None = None
    pending_client_at: datetime | None = None
    for role, timestamp in timestamped:
        if role == "client":
            if pending_client_at is None:
                pending_client_at = timestamp
        else:
            if pending_client_at is not None:
                gap = (timestamp - pending_client_at).total_seconds()
                if gap >= 0:
                    gaps.append(gap)
                    if first_response_at is None:
                        first_response_at = timestamp
                pending_client_at = None
    if not gaps:
        return None, None
    return round(sum(gaps) / len(gaps)), first_response_at


def _message_is_from_any_attendant(message: dict[str, Any]) -> bool:
    return bool(message.get("id_atend"))


def _all_response_metrics(messages: list[dict[str, Any]]) -> int | None:
    """TMR geral = média dos intervalos entre uma mensagem do cliente e a
    próxima mensagem de QUALQUER atendente (bot, humano, ou tipo
    desconhecido) — permite comparação com painéis que não separam bot de
    humano no TMR. Diferente de `_human_response_metrics`: aqui toda resposta
    de atendente fecha o intervalo, mesmo vinda de bot. `tmr_seconds` (TMR
    humano) não é afetado por esta função."""
    timestamped: list[tuple[str, datetime]] = []
    for message in messages:
        timestamp = _message_timestamp(message)
        if timestamp is None:
            continue
        if _message_is_from_client(message):
            timestamped.append(("client", timestamp))
        elif _message_is_from_any_attendant(message):
            timestamped.append(("attendant", timestamp))
    timestamped.sort(key=lambda item: item[1])

    gaps: list[float] = []
    pending_client_at: datetime | None = None
    for role, timestamp in timestamped:
        if role == "client":
            if pending_client_at is None:
                pending_client_at = timestamp
        else:
            if pending_client_at is not None:
                gap = (timestamp - pending_client_at).total_seconds()
                if gap >= 0:
                    gaps.append(gap)
                pending_client_at = None
    if not gaps:
        return None
    return round(sum(gaps) / len(gaps))


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
            records = collector()
            logger.info("dimensao_opa_sincronizada type=%s total=%s", dimension_type, len(records))
            _sync_dimension_records(
                db,
                dimension_type=dimension_type,
                records=records,
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
        "tag_ids_text": _tag_ids_text(record),
        "raw_payload": record,
    }


def active_opa_import_run(db: Session) -> SupportOpaImportRun | None:
    """Última run marcada como `running` — leitura simples, não reflete por si só se o
    lock do Postgres está ocupado (uma run pode ficar presa em `running` se o processo
    morrer sem passar pelo `finally`)."""
    return db.scalar(
        select(SupportOpaImportRun)
        .where(SupportOpaImportRun.status == "running")
        .order_by(SupportOpaImportRun.started_at.desc())
    )


def opa_import_lock_busy(db: Session) -> bool | None:
    """Verifica se o lock consultivo de importação está ocupado, sem tirá-lo de quem
    já o segura: tenta adquirir e, se conseguir, libera imediatamente (lock só estava
    livre). Retorna `None` fora do Postgres ou se a checagem falhar — não é um "não"."""
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return None
    try:
        acquired = bool(
            db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": SUPPORT_OPA_IMPORT_LOCK_KEY}).scalar()
        )
        if acquired:
            db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": SUPPORT_OPA_IMPORT_LOCK_KEY})
        return not acquired
    except SQLAlchemyError:
        return None


def _opa_import_busy_message(db: Session) -> str:
    active_run = active_opa_import_run(db)
    if active_run is not None and active_run.mode == "scheduled":
        return "A sincronização automática do OPA está em andamento. Aguarde a conclusão para iniciar uma importação manual."
    if active_run is not None:
        return "Já existe uma importação do OPA Suite em andamento. Aguarde a conclusão antes de tentar novamente."
    return "Há uma importação do OPA Suite em andamento, mas a run ativa ainda não pôde ser identificada. Aguarde alguns instantes e tente novamente."


def _create_running_import_run(
    *, mode: str, date_from: date, date_to: date, imported_by: int | None
) -> int:
    """Cria a run já como `running` numa sessão própria, commitada na hora — chamada
    só DEPOIS que o lock de importação já foi adquirido (nunca antes: evitaria linha
    órfã em "running" se o lock estiver ocupado), e ANTES do processamento longo de
    páginas. Assim outras conexões (ex.: o probe de `/opa-sync-status`) enxergam a run
    ativa assim que a importação realmente começa, não só quando tudo termina e a
    transação principal (que segura o lock) commita.

    Usa uma sessão separada de propósito: a sessão principal do import mantém o lock
    consultivo do Postgres atrelado à sua conexão pelo tempo todo; um `commit()` nela
    no meio do processamento devolveria a conexão pro pool e poderia trocar de conexão
    física na sequência, quebrando essa associação (o unlock no fim rodaria na conexão
    errada). Uma sessão à parte nunca toca na conexão que segura o lock.
    """
    with SessionLocal() as run_db:
        run = SupportOpaImportRun(
            provider="opa",
            entity="attendance",
            mode=mode,
            date_from=date_from,
            date_to=date_to,
            status="running",
            page_limit=SUPPORT_OPA_PAGE_LIMIT,
            next_skip=0,
            checkpoint_json={"skip": 0, "page_limit": SUPPORT_OPA_PAGE_LIMIT},
            imported_by=imported_by,
        )
        run_db.add(run)
        run_db.commit()
        return run.id


def _mark_resumed_run_running(run_id: int, *, imported_by: int | None, checkpoint: dict) -> None:
    """Mesma lógica de `_create_running_import_run`, mas pra retomada de uma run
    existente: grava `status="running"` numa sessão própria e já commitada, sem tocar
    na sessão que segura o lock."""
    with SessionLocal() as run_db:
        run_db.execute(
            update(SupportOpaImportRun)
            .where(SupportOpaImportRun.id == run_id)
            .values(
                status="running",
                mode="resume",
                imported_by=imported_by,
                finished_at=None,
                last_error=None,
                checkpoint_json=checkpoint,
            )
        )
        run_db.commit()


def _persist_run_terminal_status(run: SupportOpaImportRun) -> None:
    """Grava o status final da run (completed/completed_with_warnings/interrupted/
    failed) numa transação própria e já commitada, independente do que o chamador
    (rota ou scheduler) fizer depois com a sessão principal.

    Sem isso, uma falha cujo tipo não é `OpaImportInterrupted` faz o chamador reverter
    (`db.rollback()`) a sessão inteira — incluindo o `run.status = "failed"` que
    `_process_attendance_pages` acabou de gravar — e a run fica presa em "running"
    pra sempre (o problema de visibilidade original, só que permanente).
    """
    with SessionLocal() as status_db:
        status_db.execute(
            update(SupportOpaImportRun)
            .where(SupportOpaImportRun.id == run.id)
            .values(
                status=run.status,
                last_error=run.last_error,
                errors=run.errors,
                pages_processed=run.pages_processed,
                fetched_count=run.fetched_count,
                created_count=run.created_count,
                updated_count=run.updated_count,
                unchanged_count=run.unchanged_count,
                rejected_count=run.rejected_count,
                next_skip=run.next_skip,
                checkpoint_json=run.checkpoint_json,
                finished_at=run.finished_at,
                duration_ms=run.duration_ms,
            )
        )
        status_db.commit()


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
        raise RuntimeError(_opa_import_busy_message(db))
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
    attendant_types = _load_attendant_types(db)
    human_attendant_ids = _human_attendant_ids(attendant_types)
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

                    try:
                        messages = client.list_messages(payload["source_id"])
                        avg_human_seconds, first_human_response_at = _human_response_metrics(
                            messages, human_attendant_ids
                        )
                        if avg_human_seconds is not None:
                            payload["tmr_seconds"] = avg_human_seconds
                        if first_human_response_at is not None:
                            payload["first_response_at"] = first_human_response_at

                        avg_all_seconds = _all_response_metrics(messages)
                        if avg_all_seconds is not None:
                            payload["tmr_all_responses_seconds"] = avg_all_seconds

                        handled_by_bot, reached_human, handoff = _classify_bot_human(messages, attendant_types)
                        payload["handled_by_bot"] = handled_by_bot
                        payload["reached_human"] = reached_human
                        payload["bot_to_human_handoff"] = handoff

                        payload.update(_message_attendant_summary(messages, attendant_types))
                    except Exception as exc:
                        logger.warning("falha_calcular_tmr source_id=%s erro=%s", payload["source_id"], exc)

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
        _persist_run_terminal_status(run)
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
        run_id = _create_running_import_run(
            mode="manual" if imported_by is not None else "scheduled",
            date_from=date_from,
            date_to=date_to,
            imported_by=imported_by,
        )
        run = db.get(SupportOpaImportRun, run_id)
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
        resume_from_skip = run.next_skip
        resume_checkpoint = {
            **(run.checkpoint_json or {}),
            "resume_started_at": datetime.now(timezone.utc).isoformat(),
            "resume_from_skip": resume_from_skip,
        }
        _mark_resumed_run_running(run_id, imported_by=imported_by, checkpoint=resume_checkpoint)
        db.refresh(run)
        return _process_attendance_pages(
            db,
            client,
            run=run,
            start_skip=resume_from_skip,
            started_mono=started_mono,
        )


def _create_pending_import_run(*, mode: str, date_from: date, date_to: date, imported_by: int | None) -> int:
    """Mesma ideia de `_create_running_import_run`, mas pra importação em BACKGROUND
    (ver `run_opa_import_background_job`): cria a run como "pending" (não "running")
    porque o lock consultivo ainda não foi adquirido - só a `BackgroundTasks` que vai
    tentar, depois que a requisição HTTP já respondeu com o `run_id`. Uma run "pending"
    órfã (processo derrubado antes de tentar o lock) é inofensiva pro resto do sistema,
    diferente de uma "running" órfã - por isso o status separado."""
    with SessionLocal() as run_db:
        run = SupportOpaImportRun(
            provider="opa",
            entity="attendance",
            mode=mode,
            date_from=date_from,
            date_to=date_to,
            status="pending",
            page_limit=SUPPORT_OPA_PAGE_LIMIT,
            next_skip=0,
            checkpoint_json={"skip": 0, "page_limit": SUPPORT_OPA_PAGE_LIMIT},
            imported_by=imported_by,
        )
        run_db.add(run)
        run_db.commit()
        return run.id


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _maybe_mark_month_complete(db: Session, *, run_id: int, date_from: date, date_to: date, status: str) -> None:
    """Marca `SupportOpaImportMonth` como "complete" quando uma run termina cobrindo um
    mês calendário INTEIRO (date_from/date_to batendo exatamente com o 1º e o último dia
    do mês) sem falhar - definição operacional de "completo", já que o OPA Suite não
    expõe um total esperado por mês pra validar contra. Uma run parcial (ex.: um recorte
    de 10 dias) nunca marca nada, mesmo que tenha sucesso - só runs de mês inteiro."""
    if status not in ("completed", "completed_with_warnings"):
        return
    first_day, last_day = _month_bounds(date_from.year, date_from.month)
    if date_from != first_day or date_to != last_day:
        return
    year_month = date_from.strftime("%Y-%m")
    range_start = datetime(first_day.year, first_day.month, first_day.day, tzinfo=timezone.utc)
    if first_day.month == 12:
        range_end = datetime(first_day.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        range_end = datetime(first_day.year, first_day.month + 1, 1, tzinfo=timezone.utc)
    count = db.scalar(
        select(func.count(SupportOpaAttendance.id)).where(
            SupportOpaAttendance.opened_at >= range_start,
            SupportOpaAttendance.opened_at < range_end,
        )
    ) or 0
    now = datetime.now(timezone.utc)
    existing = db.scalar(select(SupportOpaImportMonth).where(SupportOpaImportMonth.year_month == year_month))
    if existing is None:
        db.add(
            SupportOpaImportMonth(
                year_month=year_month,
                status="complete",
                attendance_count=count,
                last_run_id=run_id,
                last_verified_at=now,
            )
        )
    else:
        existing.status = "complete"
        existing.attendance_count = count
        existing.last_run_id = run_id
        existing.last_verified_at = now
    db.commit()


def run_opa_import_background_job(run_id: int) -> None:
    """Processa em background uma run já criada como "pending" (ver
    `_create_pending_import_run`) - o endpoint `POST /opa-imports` devolve o `run_id`
    na hora, sem bloquear a requisição HTTP com um import de mês inteiro (que pode
    levar minutos por causa da busca de mensagens por atendimento pra TMR), e o
    frontend acompanha o progresso via `GET /opa/sync-runs/{run_id}`.

    Mesma semântica de commit/rollback de `import_opa_period` (router.py), só que sem
    resposta HTTP: `OpaImportInterrupted` faz commit (o que já foi processado fica
    salvo, o status "interrupted" já foi persistido à parte por `_process_attendance_pages`);
    qualquer outra exceção faz rollback (nada persistido além do status "failed", que
    também já foi gravado à parte quando veio de dentro do processamento de páginas)."""
    with SessionLocal() as db:
        run = db.get(SupportOpaImportRun, run_id)
        if run is None or run.status != "pending":
            return
        client = get_opa_client()
        started_mono = time.monotonic()
        try:
            with _support_opa_import_lock(db):
                run.status = "running"
                db.flush()
                _process_attendance_pages(db, client, run=run, start_skip=0, started_mono=started_mono)
            db.commit()
        except OpaImportInterrupted:
            db.commit()
            return
        except RuntimeError as exc:
            # Lock ocupado além do tempo de espera - a run nunca chegou a rodar
            # (status ainda "pending"), diferente de uma falha durante o processamento
            # (que já teria marcado "failed" sozinha via _persist_run_terminal_status).
            db.rollback()
            with SessionLocal() as err_db:
                err_db.execute(
                    update(SupportOpaImportRun)
                    .where(SupportOpaImportRun.id == run_id)
                    .values(status="failed", last_error=str(exc)[:500], finished_at=datetime.now(timezone.utc))
                )
                err_db.commit()
            return
        except Exception:
            db.rollback()
            logger.exception("Falha inesperada na importação OPA em background run_id=%s", run_id)
            return

    with SessionLocal() as status_db:
        finished_run = status_db.get(SupportOpaImportRun, run_id)
        if finished_run is not None:
            _maybe_mark_month_complete(
                status_db,
                run_id=finished_run.id,
                date_from=finished_run.date_from,
                date_to=finished_run.date_to,
                status=finished_run.status,
            )


def import_months_status(db: Session, year_months: list[str]) -> dict[str, dict[str, Any]]:
    """Status de cada mês pedido (formato "AAAA-MM") - "missing" pra quem não tem
    nenhuma linha em `SupportOpaImportMonth` ainda (nunca uma run de mês inteiro
    terminou com sucesso pra ele)."""
    rows = {
        row.year_month: row
        for row in db.scalars(select(SupportOpaImportMonth).where(SupportOpaImportMonth.year_month.in_(year_months)))
    }
    result: dict[str, dict[str, Any]] = {}
    for year_month in year_months:
        row = rows.get(year_month)
        if row is None:
            result[year_month] = {"year_month": year_month, "status": "missing", "attendance_count": 0, "last_verified_at": None}
        else:
            result[year_month] = {
                "year_month": year_month,
                "status": row.status,
                "attendance_count": row.attendance_count,
                "last_verified_at": row.last_verified_at,
            }
    return result
