from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.calculation import get_setting
from app.services.ixc_client import IxcClient, fetch_login_status_snapshot, get_ixc_client
from app.services.regional import normalize_regional

from .models import OperationLoginCurrentStatus, OperationLoginStatusSnapshot
from .period import parse_ixc_local_datetime

logger = logging.getLogger(__name__)

# Achado real 2026-08-15: o IXC grava datetime em horário LOCAL (America/Porto_Velho, UTC-4), não
# UTC - confirmado comparando `radusuarios.ultima_atualizacao` de logins online AGORA contra o
# relógio UTC real (diferença de ~4h, batendo com o fuso, não com um clock divergente). Uma versão
# anterior deste parser fazia `.replace(tzinfo=timezone.utc)` direto, rotulando hora local como UTC
# sem deslocar - `last_connected_at`/`last_disconnected_at` ficavam 4h adiantados. Corrigido
# reaproveitando `parse_ixc_local_datetime` (já usado pela importação de O.S. desde sempre - mesma
# fonte, mesmo fuso, nunca deveria ter sido reimplementado errado aqui).
_parse_ixc_datetime = parse_ixc_local_datetime


def _parse_ixc_float(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


# O Postgres aceita no máximo 65535 parâmetros por statement - achado real, um único
# `INSERT ... VALUES` com os ~88 mil logins ativos (9 colunas cada = ~790 mil parâmetros) estourava
# esse limite direto. 3000 linhas x 9 colunas = 27000 parâmetros, com folga confortável.
_UPSERT_CHUNK_SIZE = 3000


def upsert_login_current_status(db: Session, rows: list[dict]) -> None:
    """Atualiza `operations_login_current_status` (1 linha por login) em lotes de
    `_UPSERT_CHUNK_SIZE`. `status_changed_at` só avança quando `online` muda de valor em relação à
    linha existente - é isso que faz a detecção de cluster
    (`login_geo_clusters._fetch_recent_disconnections`) virar um filtro indexado em vez de escanear
    o histórico inteiro toda vez (ver docstring do model)."""
    for offset in range(0, len(rows), _UPSERT_CHUNK_SIZE):
        chunk = rows[offset : offset + _UPSERT_CHUNK_SIZE]
        stmt = pg_insert(OperationLoginCurrentStatus).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[OperationLoginCurrentStatus.login_id],
            set_={
                "login": stmt.excluded.login,
                "online": stmt.excluded.online,
                "regional": stmt.excluded.regional,
                "latitude": stmt.excluded.latitude,
                "longitude": stmt.excluded.longitude,
                "last_connected_at": stmt.excluded.last_connected_at,
                "last_disconnected_at": stmt.excluded.last_disconnected_at,
                "captured_at": stmt.excluded.captured_at,
                "status_changed_at": case(
                    (
                        OperationLoginCurrentStatus.online.is_distinct_from(stmt.excluded.online),
                        stmt.excluded.captured_at,
                    ),
                    else_=OperationLoginCurrentStatus.status_changed_at,
                ),
            },
        )
        db.execute(stmt)


def capture_login_status_snapshot(db: Session, client: IxcClient) -> int:
    """Busca o status de conexão atual de todos os logins ativos no IXC. Grava uma linha nova por
    login no histórico append-only (`OperationLoginStatusSnapshot`, nunca upsert - ver docstring do
    model) e faz upsert de `operations_login_current_status` (a tabela que a detecção de cluster
    realmente consulta). Retorna quantas linhas foram gravadas no histórico."""
    captured_at = datetime.now(timezone.utc)
    parsed = []
    regionals = []
    for record in fetch_login_status_snapshot(client):
        parsed.append(
            {
                "login_id": int(record["id"]),
                "login": record.get("login") or "",
                "online": record.get("online") or "",
                "latitude": _parse_ixc_float(record.get("latitude")),
                "longitude": _parse_ixc_float(record.get("longitude")),
                "last_connected_at": _parse_ixc_datetime(record.get("ultima_conexao_inicial")),
                "last_disconnected_at": _parse_ixc_datetime(record.get("ultima_conexao_final")),
            }
        )
        # `regional` só existe em `operations_login_current_status` (não no histórico append-only
        # `OperationLoginStatusSnapshot`, que não tem essa coluna) - por isso fica de fora de
        # `parsed`, guardado à parte na mesma ordem pra juntar só no upsert abaixo.
        regionals.append(normalize_regional(record.get("id_filial")))
    if not parsed:
        return 0

    db.bulk_save_objects([OperationLoginStatusSnapshot(captured_at=captured_at, **fields) for fields in parsed])
    upsert_login_current_status(
        db,
        [
            {**fields, "regional": regional, "captured_at": captured_at, "status_changed_at": captured_at}
            for fields, regional in zip(parsed, regionals)
        ],
    )
    db.commit()
    return len(parsed)


# Configurável pela tela (AppSetting), lido a cada ciclo - mesmo padrão já usado por
# `ixc_scheduler.IXC_SYNC_INTERVAL_MINUTES_KEY`/`IXC_SYNC_ENABLED_KEY`. Pedido do usuário em
# 2026-08-15 (receio de sobrecarregar a API do IXC, e poder desligar o monitoramento de rede
# quando não estiver usando, mantendo só a sincronização de O.S.): antes disso, o intervalo era
# fixo em código e o loop rodava sempre que o IXC estivesse configurado, sem chave própria de
# liga/desliga.
LOGIN_STATUS_SYNC_ENABLED_KEY = "login_status_sync_enabled"
LOGIN_STATUS_SYNC_INTERVAL_MINUTES_KEY = "login_status_sync_interval_minutes"
LOGIN_STATUS_SYNC_DEFAULT_INTERVAL_MINUTES = 5
LOGIN_STATUS_SYNC_MIN_INTERVAL_MINUTES = 2
LOGIN_STATUS_SYNC_MAX_INTERVAL_MINUTES = 120


def _current_login_status_interval_seconds() -> float:
    with SessionLocal() as db:
        raw = get_setting(db, LOGIN_STATUS_SYNC_INTERVAL_MINUTES_KEY, "")
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        minutes = LOGIN_STATUS_SYNC_DEFAULT_INTERVAL_MINUTES
    minutes = min(max(minutes, LOGIN_STATUS_SYNC_MIN_INTERVAL_MINUTES), LOGIN_STATUS_SYNC_MAX_INTERVAL_MINUTES)
    return minutes * 60.0


def _login_status_sync_enabled(default: bool) -> bool:
    with SessionLocal() as db:
        raw = get_setting(db, LOGIN_STATUS_SYNC_ENABLED_KEY, "")
    if not raw:
        return default
    return raw.strip().lower() in {"true", "1", "sim", "yes"}


async def run_login_status_snapshot_loop() -> None:
    """Loop infinito: captura o status de conexão de todos os logins periodicamente. Intervalo e
    liga/desliga configuráveis pela tela (`LOGIN_STATUS_SYNC_INTERVAL_MINUTES_KEY`/
    `LOGIN_STATUS_SYNC_ENABLED_KEY`, lidos a cada ciclo - uma mudança feita na configuração vale no
    próximo ciclo, sem reiniciar o backend). Desligado, o backend continua sincronizando O.S.
    normalmente (loop independente) - só este monitoramento de rede para. Uma falha numa rodada não
    derruba o loop, só é logada."""
    IDLE_POLL_SECONDS = 60.0
    while True:
        settings = get_settings()
        if not settings.ixc_api_base_url or not settings.ixc_api_token:
            await asyncio.sleep(IDLE_POLL_SECONDS)
            continue
        if not _login_status_sync_enabled(default=True):
            await asyncio.sleep(IDLE_POLL_SECONDS)
            continue
        try:
            client = get_ixc_client()
            with SessionLocal() as db:
                captured = await asyncio.to_thread(capture_login_status_snapshot, db, client)
            if captured:
                logger.info("Snapshot de status de login capturado: %d linhas.", captured)
        except Exception:
            logger.exception("Falha ao capturar snapshot de status de login.")
        await asyncio.sleep(_current_login_status_interval_seconds())


# Achado real do incidente de 17/09/2026: `operations_login_status_snapshots` é append-only (ver
# docstring do model) sem nenhuma retenção desde que existe (migration de 2026-08-13) - chegou a
# 66GB (87% do banco) e derrubou o Postgres da VM por falta de espaço em disco. Ligada por padrão
# (diferente de `prune_superseded_drafts`, que é destrutiva sobre registro de pagamento e por isso
# exige opt-in): esta tabela é telemetria pura para detecção de cluster geográfico, não registro de
# negócio, e o crescimento sem limite já causou dois incidentes de indisponibilidade do cockpit.
# Padrão de 7 dias (não 14) por decisão explícita de 17/09/2026: a VM deste projeto tem um único
# disco de 97GB sem possibilidade de expansão nem de anexar um disco adicional - depois do purge
# inicial a folga ficou em ~2,5GB fixos, então quanto menor o volume de dados vivos nesta tabela,
# mais espaço de reuso sobra pros próximos ciclos de captura.
LOGIN_STATUS_RETENTION_ENABLED_KEY = "login_status_retention_enabled"
LOGIN_STATUS_RETENTION_DAYS_KEY = "login_status_retention_days"
LOGIN_STATUS_RETENTION_DEFAULT_DAYS = 7
LOGIN_STATUS_RETENTION_MIN_DAYS = 3
LOGIN_STATUS_RETENTION_MAX_DAYS = 180
# Roda a purga a cada 6h - não precisa ser mais frequente, o volume que importa é o de dias, não o
# de horas.
LOGIN_STATUS_RETENTION_INTERVAL_SECONDS = 6 * 60 * 60
# Cada lote é deletado e comitado em transação própria - achado real do mesmo incidente: com a VM
# operando a poucos GB livres em disco, um único DELETE apagando meses de histórico de uma vez
# gera WAL suficiente para estourar esse espaço livre e derrubar o Postgres de novo antes mesmo de
# terminar a limpeza. Lotes pequenos com uma pausa entre eles dão tempo pro checkpointer/autovacuum
# acompanhar.
_RETENTION_BATCH_SIZE = 20_000
_RETENTION_BATCH_PAUSE_SECONDS = 0.2


def _current_retention_days() -> int:
    with SessionLocal() as db:
        raw = get_setting(db, LOGIN_STATUS_RETENTION_DAYS_KEY, "")
    try:
        days = int(raw)
    except (TypeError, ValueError):
        days = LOGIN_STATUS_RETENTION_DEFAULT_DAYS
    return min(max(days, LOGIN_STATUS_RETENTION_MIN_DAYS), LOGIN_STATUS_RETENTION_MAX_DAYS)


def _retention_enabled(default: bool) -> bool:
    with SessionLocal() as db:
        raw = get_setting(db, LOGIN_STATUS_RETENTION_ENABLED_KEY, "")
    if not raw:
        return default
    return raw.strip().lower() in {"true", "1", "sim", "yes"}


def purge_old_login_status_snapshots(
    db: Session, *, retention_days: int, batch_size: int = _RETENTION_BATCH_SIZE
) -> int:
    """Apaga em lotes linhas de `operations_login_status_snapshots` com `captured_at` mais antigo
    que `retention_days`. Cada lote é sua própria transação (commit por lote, não uma transação só
    pra tudo) - ver `LOGIN_STATUS_RETENTION_INTERVAL_SECONDS` acima para o motivo. Retorna o total
    de linhas removidas."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    total_deleted = 0
    while True:
        batch_ids = db.scalars(
            select(OperationLoginStatusSnapshot.id)
            .where(OperationLoginStatusSnapshot.captured_at < cutoff)
            .limit(batch_size)
        ).all()
        if not batch_ids:
            break
        db.execute(delete(OperationLoginStatusSnapshot).where(OperationLoginStatusSnapshot.id.in_(batch_ids)))
        db.commit()
        total_deleted += len(batch_ids)
        if len(batch_ids) < batch_size:
            break
        time.sleep(_RETENTION_BATCH_PAUSE_SECONDS)
    return total_deleted


async def run_login_status_snapshot_purge_loop() -> None:
    """Loop infinito, roda a cada `LOGIN_STATUS_RETENTION_INTERVAL_SECONDS`: purga snapshots de
    status de login mais antigos que `LOGIN_STATUS_RETENTION_DAYS_KEY` dias. Independe de
    configuração do IXC (roda sempre, mesmo padrão de `run_backlog_snapshot_loop`) - só limpa
    histórico já gravado, não chama a API externa. Liga/desliga e o número de dias são
    configuráveis por AppSetting, lidos a cada ciclo, sem precisar reiniciar o backend. Uma falha
    numa rodada não derruba o loop, só é logada."""
    while True:
        try:
            if _retention_enabled(default=True):
                retention_days = _current_retention_days()
                with SessionLocal() as db:
                    deleted = await asyncio.to_thread(
                        purge_old_login_status_snapshots, db, retention_days=retention_days
                    )
                if deleted:
                    logger.info(
                        "Purga de snapshots de status de login: %d linhas removidas (retenção de %d dias).",
                        deleted,
                        retention_days,
                    )
        except Exception:
            logger.exception("Falha ao purgar snapshots antigos de status de login.")
        await asyncio.sleep(LOGIN_STATUS_RETENTION_INTERVAL_SECONDS)
