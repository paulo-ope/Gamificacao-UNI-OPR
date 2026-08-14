from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.ixc_client import IxcClient, fetch_login_status_snapshot, get_ixc_client
from app.services.regional import normalize_regional

from .models import OperationLoginCurrentStatus, OperationLoginStatusSnapshot

logger = logging.getLogger(__name__)

# O IXC usa "0000-00-00 00:00:00" pra "nunca conectado" (não NULL) - visto direto na resposta real
# de `radusuarios` pra logins de fibra monitorados por sinal óptico, que não abrem sessão PPPoE.
_IXC_EMPTY_DATETIME_PREFIX = "0000-00-00"


def _parse_ixc_datetime(value: str | None) -> datetime | None:
    if not value or value.startswith(_IXC_EMPTY_DATETIME_PREFIX):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


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


async def run_login_status_snapshot_loop() -> None:
    """Loop infinito: captura o status de conexão de todos os logins periodicamente. Intervalo fixo
    em código (não configurável pela tela, ao contrário de `ixc_scheduler`) porque essa captura é
    read-only e independente da sincronização de O.S. - não compartilha o mesmo botão de
    liga/desliga. Uma falha numa rodada não derruba o loop, só é logada."""
    POLL_SECONDS = 300.0
    while True:
        settings = get_settings()
        if not settings.ixc_api_base_url or not settings.ixc_api_token:
            await asyncio.sleep(POLL_SECONDS)
            continue
        try:
            client = get_ixc_client()
            with SessionLocal() as db:
                captured = await asyncio.to_thread(capture_login_status_snapshot, db, client)
            if captured:
                logger.info("Snapshot de status de login capturado: %d linhas.", captured)
        except Exception:
            logger.exception("Falha ao capturar snapshot de status de login.")
        await asyncio.sleep(POLL_SECONDS)
