"""Status (presença) dos atendentes para a TV do SGP Suporte.

Fonte: o campo `online` de cada usuário em `GET /api/v1/usuario/` do OPA Suite (confirmado ao vivo em
2026-10-08, ver docs/api-suporte.md). O campo `status` do mesmo registro NÃO é presença - é só
ativo/inativo do cadastro.

Códigos de `online` vistos: `on` online, `off` offline, `pause` em pausa, `au` ausente, `oc` ocupado,
`call` em ligação. "Ligação tocando" NÃO é informada pela API (nenhum campo de conexão traz isso) -
o payload diz isso explicitamente em `ringing_available`, para a tela nunca fingir que sabe.

Quem conta como "atendente da TV": usuário humano ATIVO que atendeu pelo menos uma vez nos últimos
`ACTIVITY_WINDOW_DAYS` dias - nos departamentos escolhidos na configuração da TV, ou em qualquer
departamento se não houver escolha. O OPA tem centenas de usuários cadastrados; sem esse recorte a
rosca seria dominada por quem nunca atende.
"""
from __future__ import annotations

import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import SupportOpaAttendance

# Ordem de exibição (a mesma do painel do OPA) e rótulo de cada código.
PRESENCE_STATES: tuple[tuple[str, str], ...] = (
    ("on", "Online"),
    ("call", "Em ligação"),
    ("au", "Ausente"),
    ("pause", "Em pausa"),
    ("oc", "Ocupado"),
    ("off", "Offline"),
)
KNOWN_CODES = {code for code, _ in PRESENCE_STATES}
CALL_CODE = "call"
ACTIVITY_WINDOW_DAYS = 30
# Quem aparece na lista "quem está em quê": só os estados que pedem atenção (online e offline são
# muitos e não são notícia). Ordem de prioridade na lista; dentro de cada estado, o mais antigo primeiro.
LISTED_STATES: tuple[str, ...] = ("call", "oc", "pause", "au")
AGENT_LIST_LIMIT = 4

# Várias TVs/abas abertas não podem multiplicar as chamadas ao OPA: a lista de usuários fica em
# cache por alguns segundos (a TV consulta a cada ~10 s).
USERS_CACHE_SECONDS = 5
_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"at": 0.0, "records": None}


def _fetch_users(client) -> list[dict[str, Any]]:
    with _cache_lock:
        if _cache["records"] is not None and time.monotonic() - _cache["at"] < USERS_CACHE_SECONDS:
            return _cache["records"]
        records = client.list_user_presence()
        _cache["records"] = records
        _cache["at"] = time.monotonic()
        return records


def reset_users_cache() -> None:
    with _cache_lock:
        _cache["records"] = None
        _cache["at"] = 0.0


def _state_label(code: str) -> str:
    return dict(PRESENCE_STATES).get(code, "Outros")


def _seconds_since(value: Any, now: datetime) -> int | None:
    """Segundos desde `updatedAt` do usuário no OPA. É uma APROXIMAÇÃO de "há quanto tempo está neste
    status": o OPA não expõe o instante em que o status mudou, e `updatedAt` é a última gravação do
    registro (que acompanha a troca de presença, mas qualquer outra alteração do cadastro também a
    move). Sem data válida devolve None - a tela omite o tempo em vez de inventar."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0, int((now - parsed).total_seconds()))


def team_attendant_ids(db: Session, now: datetime, department_ids: list[str] | None) -> set[str]:
    """Ids de quem atendeu nos últimos `ACTIVITY_WINDOW_DAYS` dias (nos departamentos escolhidos,
    se houver). O id do atendente no atendimento é o `_id` do usuário no OPA."""
    statement = select(SupportOpaAttendance.attendant_id).where(
        SupportOpaAttendance.attendant_id.isnot(None),
        SupportOpaAttendance.attendant_id != "",
        SupportOpaAttendance.opened_at >= now - timedelta(days=ACTIVITY_WINDOW_DAYS),
    )
    if department_ids:
        statement = statement.where(SupportOpaAttendance.department_id.in_(department_ids))
    return {str(attendant_id) for attendant_id in db.scalars(statement.distinct())}


def build_presence(db: Session, client, now: datetime, department_ids: list[str] | None = None) -> dict[str, Any]:
    scope_ids = team_attendant_ids(db, now, department_ids)
    users = _fetch_users(client)

    team = [
        user
        for user in users
        if isinstance(user, dict)
        and user.get("tipo") == "user"
        and user.get("status") != "I"  # inativo no cadastro
        and str(user.get("_id")) in scope_ids
    ]

    counts: Counter[str] = Counter()
    unmapped: Counter[str] = Counter()
    for user in team:
        code = user.get("online")
        if code in KNOWN_CODES:
            counts[code] += 1
        else:
            counts["other"] += 1
            unmapped[repr(code)] += 1

    total = len(team)
    states = [{"code": code, "label": label, "total": counts.get(code, 0)} for code, label in PRESENCE_STATES]
    if counts.get("other"):
        states.append({"code": "other", "label": "Outros", "total": counts["other"]})

    listed = [
        {
            "name": str(user.get("nome") or "Atendente sem nome").strip(),
            "state_code": user["online"],
            "state_label": _state_label(user["online"]),
            "seconds_in_state": _seconds_since(user.get("updatedAt"), now),
        }
        for user in team
        if user.get("online") in LISTED_STATES
    ]
    # Prioridade do estado (ligação primeiro), depois o que está há mais tempo; sem tempo vai por último.
    listed.sort(
        key=lambda agent: (
            LISTED_STATES.index(agent["state_code"]),
            -(agent["seconds_in_state"] if agent["seconds_in_state"] is not None else -1),
            agent["name"].casefold(),
        )
    )
    return {
        "generated_at": now,
        "scope": "departments" if department_ids else "all",
        "total": total,
        # Mesma conta do painel do OPA ("12,5% disponível" = 6 online de 48): online / total.
        "available_percentage": round(counts.get("on", 0) / total * 100, 1) if total else None,
        "states": states,
        "agents": listed[:AGENT_LIST_LIMIT],
        "agents_total": len(listed),
        "unmapped_codes": sorted(unmapped),
        "ringing_available": False,
    }
