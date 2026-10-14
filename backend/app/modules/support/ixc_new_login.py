"""Ativação de Novo Login/Transferência de Comodato (assunto 74 do IXC) finalizadas, consultadas AO VIVO.

Pedido do usuário (2026-10-14), para o Dashboard Suporte. Essas O.S. ficam no setor 10 ("Suporte Interno"),
que a importação da Operação Analítica não traz (escopo regular = setores 7, 8 e 9) - incluir o setor 10 ali
mudaria os números da Operação e da Visão Geral. Por isso este indicador pergunta direto ao IXC, só pelo
assunto 74, com um cache curto para não consultar o IXC a cada abertura da tela.

"Finalizada no período" = `status = F` e `data_fechamento` dentro das datas (horário local do IXC). Quem
finalizou = o técnico/responsável da O.S. (`id_tecnico`, tabela `funcionarios`).
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from datetime import date
from typing import Any

from app.services.ixc_client import IxcClient, fetch_funcionarios_by_ids, get_ixc_client

NEW_LOGIN_SUBJECT_ID = "74"
CACHE_TTL_SECONDS = 120
# Teto de segurança: no ritmo atual (~9 O.S./dia) um ano inteiro cabe com folga.
MAX_RECORDS = 5000

_cache: dict[tuple[date, date], tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _fetch_period(client: IxcClient, date_from: date, date_to: date) -> dict[str, Any]:
    grid_param = [
        {"TB": "su_oss_chamado.id_assunto", "OP": "=", "P": NEW_LOGIN_SUBJECT_ID},
        {"TB": "su_oss_chamado.status", "OP": "=", "P": "F"},
        {"TB": "su_oss_chamado.data_fechamento", "OP": ">=", "P": f"{date_from.isoformat()} 00:00:00"},
        {"TB": "su_oss_chamado.data_fechamento", "OP": "<=", "P": f"{date_to.isoformat()} 23:59:59"},
    ]
    records = list(
        client.list_all("su_oss_chamado", grid_param=grid_param, rp=200, sortname="su_oss_chamado.id", max_records=MAX_RECORDS)
    )
    technician_ids = sorted({int(record["id_tecnico"]) for record in records if str(record.get("id_tecnico") or "").isdigit() and int(record["id_tecnico"]) > 0})
    names = {
        int(employee["id"]): str(employee.get("funcionario") or "").strip()
        for employee in fetch_funcionarios_by_ids(client, technician_ids)
        if str(employee.get("id") or "").isdigit()
    }
    counts: Counter[str] = Counter()
    for record in records:
        technician_id = str(record.get("id_tecnico") or "")
        counts[names.get(int(technician_id), "") if technician_id.isdigit() else ""] += 1
    return {"finalized": len(records), "by_name": dict(counts)}


def finalized_in_period(date_from: date, date_to: date, *, client: IxcClient | None = None) -> dict[str, Any]:
    """`{"finalized": total, "by_name": {nome do responsável: quantidade}}` (nome vazio = sem responsável).
    Levanta `IxcApiError` se o IXC estiver indisponível - quem chama decide como mostrar a falha."""
    key = (date_from, date_to)
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]
    result = _fetch_period(client or get_ixc_client(), date_from, date_to)
    with _cache_lock:
        _cache[key] = (time.monotonic(), result)
    return result
