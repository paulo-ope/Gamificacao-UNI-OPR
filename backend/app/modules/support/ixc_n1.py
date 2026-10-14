"""Atendimento do Suporte Interno N1 no IXC: protocolos operacionais e financeiros.

Pedido do usuário (2026-10-06), na aba "Atendimento Suporte Interno N1" do SGP Suporte:
- "operacional" = motivo 90 (`Registro de Atendimento Operacional`);
- "financeiro" = motivo 29 (`Registro de Informação Financeira`);
- só conta protocolo aberto por colaboradores dos grupos de usuários 105 e 117 do IXC
  (`usuarios.id_grupo`). O 105 foi confirmado pelo usuário contra a lista de 38 usuários do grupo; o
  117 (9 usuários, entre eles Bruno Rossow e Maycon Batista) foi incluído inteiro a pedido do usuário
  em 2026-10-06, que informou que os demais do 117 são N2 e podem entrar na contagem. O setor do ticket
  (`id_ticket_setor`) NÃO serve de critério: quase todos caem em Retenção/Comercial.

Quem abriu o protocolo vem de `su_ticket.id_usuarios` (`SupportIxcTicket.opened_by_user_id`) e o grupo
de `SupportIxcUser`, mantido por `sync_ixc_users`. Protocolos sem operador (`id_usuarios = 0`) não
entram: não são de nenhum colaborador.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.ixc_client import IxcClient, fetch_usuarios_by_ids

from .ixc_ticket_queries import _apply_period, _previous_period_bounds
from .models import SupportIxcTicket, SupportIxcUser, utc_now

logger = logging.getLogger(__name__)

# Grupos do IXC cujos usuários entram na contagem (ver docstring do módulo).
N1_IXC_GROUP_IDS = ("105", "117")
# Colaboradores dos grupos acima que NÃO são N1 (são N2) e ficam de fora de toda contagem do N1 - lista
# informada pelo usuário em 2026-10-14. Por id do IXC (`usuarios.id`), não por nome, para não depender de
# grafia: Alessandro Diniz Loss (165), Eberton Peres De Oliveira (124), Emanuelly Ferreira Cavalheiro (417),
# Karlla Conceição de Oliveira (997, grupo 87), Madson Alvernaz Thomazetto (1109), Sabrina Fernandes Da Cunha
# (168), Welington Souza Pinto (615) e Yuri Carvalho Gadelha (771).
N1_EXCLUDED_IXC_USER_IDS = ("165", "124", "417", "997", "1109", "168", "615", "771")
# Os mesmos ids são, ao contrário, os colaboradores N2: `n2_user_name_keys` os usa para contar as O.S. que o N2 abriu.
N2_IXC_USER_IDS = N1_EXCLUDED_IXC_USER_IDS
N1_OPERATIONAL_SUBJECT_ID = "90"
N1_FINANCIAL_SUBJECT_ID = "29"
N1_SUBJECT_IDS = (N1_OPERATIONAL_SUBJECT_ID, N1_FINANCIAL_SUBJECT_ID)

# Atendimento Operacional N2 (pedido do usuário, 2026-10-14): motivos 80 (`Atendimento Interno N2`) e 81
# (`Atendimento Externo N2`) do IXC. Sem filtro de grupo de usuário - todo protocolo desses motivos conta,
# seja quem for o operador. Na resposta, "operational" = motivo 80 e "financial" = motivo 81 (os nomes dos
# campos são os do N1, reaproveitados; quem dá o rótulo é a tela).
N2_INTERNAL_SUBJECT_ID = "80"
N2_EXTERNAL_SUBJECT_ID = "81"
N2_SUBJECT_IDS = (N2_INTERNAL_SUBJECT_ID, N2_EXTERNAL_SUBJECT_ID)

# nível -> (motivo da 1ª coluna, motivo da 2ª coluna, grupos de usuário exigidos ou None)
_LEVELS: dict[str, tuple[str, str, tuple[str, ...] | None]] = {
    "n1": (N1_OPERATIONAL_SUBJECT_ID, N1_FINANCIAL_SUBJECT_ID, N1_IXC_GROUP_IDS),
    "n2": (N2_INTERNAL_SUBJECT_ID, N2_EXTERNAL_SUBJECT_ID, None),
}

# `usuarios.id IN (...)` vai na query do IXC - lote pequeno evita estourar o tamanho do filtro.
_USER_FETCH_BATCH = 100


def _normalized_user_id(value: Any) -> str | None:
    text_value = str(value).strip() if value is not None else ""
    return None if text_value in ("", "0") else text_value


def sync_ixc_users(db: Session, client: IxcClient, *, seen_user_ids: set[str] | None = None) -> int:
    """Atualiza `SupportIxcUser` (nome/grupo/situação) de quem abriu protocolos.

    Resolve `seen_user_ids` (operadores da importação atual - o grupo pode ter mudado) mais todo
    operador já gravado em protocolos do N1 que ainda não tem linha (histórico retroalimentado pela
    migração). Retorna quantos usuários foram gravados/atualizados."""
    wanted = {uid for uid in (seen_user_ids or set()) if uid}

    known = set(db.scalars(select(SupportIxcUser.ixc_user_id)).all())
    historical = set(
        db.scalars(
            select(SupportIxcTicket.opened_by_user_id)
            .where(
                SupportIxcTicket.subject_id.in_(N1_SUBJECT_IDS + N2_SUBJECT_IDS),
                SupportIxcTicket.opened_by_user_id.is_not(None),
            )
            .distinct()
        ).all()
    )
    wanted |= historical - known
    numeric_ids = sorted({int(uid) for uid in wanted if uid.isdigit()})
    if not numeric_ids:
        return 0

    now = utc_now()
    existing = {
        user.ixc_user_id: user
        for user in db.scalars(select(SupportIxcUser).where(SupportIxcUser.ixc_user_id.in_([str(i) for i in numeric_ids])))
    }
    written = 0
    for start in range(0, len(numeric_ids), _USER_FETCH_BATCH):
        for record in fetch_usuarios_by_ids(client, numeric_ids[start : start + _USER_FETCH_BATCH]):
            user_id = _normalized_user_id(record.get("id"))
            if user_id is None:
                continue
            fields = {
                "name": (str(record.get("nome") or "").strip() or None),
                "group_id": _normalized_user_id(record.get("id_grupo")),
                "active": str(record.get("status") or "A").strip().upper() == "A",
                "synced_at": now,
            }
            user = existing.get(user_id)
            if user is None:
                user = SupportIxcUser(ixc_user_id=user_id, **fields)
                db.add(user)
                existing[user_id] = user
            else:
                for key, value in fields.items():
                    setattr(user, key, value)
            written += 1
    db.commit()
    return written


def _n1_base(query, level: str = "n1"):
    first, second, group_ids = _LEVELS[level]
    if group_ids is None:
        # N2: sem exigir grupo - operador sem linha em `SupportIxcUser` também conta (join externo).
        return query.outerjoin(SupportIxcUser, SupportIxcUser.ixc_user_id == SupportIxcTicket.opened_by_user_id).where(
            SupportIxcTicket.subject_id.in_((first, second)),
        )
    return query.join(SupportIxcUser, SupportIxcUser.ixc_user_id == SupportIxcTicket.opened_by_user_id).where(
        SupportIxcUser.group_id.in_(group_ids),
        SupportIxcUser.ixc_user_id.not_in(N1_EXCLUDED_IXC_USER_IDS),
        SupportIxcTicket.subject_id.in_((first, second)),
    )


def n2_user_name_keys():
    """Subconsulta com o nome (sem caixa/espaços) de cada colaborador N2 da lista informada pelo usuário."""
    return select(func.lower(func.trim(SupportIxcUser.name))).where(
        SupportIxcUser.ixc_user_id.in_(N2_IXC_USER_IDS),
        SupportIxcUser.name.is_not(None),
    )


def n1_user_name_keys():
    """Subconsulta com o nome (sem caixa/espaços) de cada colaborador N1: grupos 105/117 menos os N2."""
    return select(func.lower(func.trim(SupportIxcUser.name))).where(
        SupportIxcUser.group_id.in_(N1_IXC_GROUP_IDS),
        SupportIxcUser.ixc_user_id.not_in(N1_EXCLUDED_IXC_USER_IDS),
        SupportIxcUser.name.is_not(None),
    )


def _kind(subject_id: str | None) -> str:
    return "operational" if subject_id in (N1_OPERATIONAL_SUBJECT_ID, N2_INTERNAL_SUBJECT_ID) else "financial"


def _totals(db: Session, date_from: date | None, date_to: date | None, level: str = "n1") -> dict[str, int]:
    query = _n1_base(select(SupportIxcTicket.subject_id, func.count(SupportIxcTicket.id)), level).group_by(
        SupportIxcTicket.subject_id
    )
    query = _apply_period(query, SupportIxcTicket.created_at, date_from, date_to)
    totals = {"operational": 0, "financial": 0}
    for subject_id, count in db.execute(query).all():
        totals[_kind(subject_id)] += int(count)
    return totals


def _daily_series(db: Session, date_from: date, date_to: date, level: str = "n1") -> list[dict[str, Any]]:
    """Um ponto por dia do período, INCLUSIVE os dias sem protocolo (zerados) - o gráfico alinha o
    período atual com o anterior pela posição do dia (dia 1 com dia 1), então as duas séries
    precisam ter o mesmo tamanho, sem buracos."""
    day_column = func.date(SupportIxcTicket.created_at)
    query = _n1_base(select(day_column, SupportIxcTicket.subject_id, func.count(SupportIxcTicket.id)), level).group_by(
        day_column, SupportIxcTicket.subject_id
    )
    query = _apply_period(query, SupportIxcTicket.created_at, date_from, date_to)
    counts: dict[str, dict[str, int]] = {}
    for day_value, subject_id, count in db.execute(query).all():
        # SQLite (testes) devolve string, Postgres devolve `date` - normaliza pra ISO.
        counts.setdefault(str(day_value)[:10], {"operational": 0, "financial": 0})[_kind(subject_id)] += int(count)

    series = []
    for offset in range((date_to - date_from).days + 1):
        day = date_from + timedelta(days=offset)
        values = counts.get(day.isoformat(), {"operational": 0, "financial": 0})
        series.append({"day": day, "operational": values["operational"], "financial": values["financial"]})
    return series


def n1_summary(db: Session, *, date_from: date, date_to: date, level: str = "n1") -> dict[str, Any]:
    """Totais, série diária e quebra por atendente do N1 no período, mais o total e a série diária do
    período imediatamente anterior (mesmo tamanho) pra comparação."""
    totals = _totals(db, date_from, date_to, level)

    # `opened_by_user_id` (e não `SupportIxcUser.ixc_user_id`) pra não perder quem ainda não tem linha em
    # `SupportIxcUser` no N2 (join externo); protocolo sem operador (None/"0") fica de fora, como no N1.
    attendant_query = _n1_base(
        select(
            SupportIxcTicket.opened_by_user_id,
            SupportIxcUser.name,
            SupportIxcUser.active,
            SupportIxcTicket.subject_id,
            func.count(SupportIxcTicket.id),
        ),
        level,
    ).where(SupportIxcTicket.opened_by_user_id.is_not(None)).group_by(
        SupportIxcTicket.opened_by_user_id, SupportIxcUser.name, SupportIxcUser.active, SupportIxcTicket.subject_id
    )
    attendant_query = _apply_period(attendant_query, SupportIxcTicket.created_at, date_from, date_to)
    attendants: dict[str, dict[str, Any]] = {}
    for user_id, name, active, subject_id, count in db.execute(attendant_query).all():
        row = attendants.setdefault(
            user_id,
            {"user_id": user_id, "name": name or f"Usuário {user_id}", "active": True if active is None else bool(active), "operational": 0, "financial": 0},
        )
        row[_kind(subject_id)] += int(count)
    attendant_rows = sorted(
        ({**row, "total": row["operational"] + row["financial"]} for row in attendants.values()),
        key=lambda row: (-row["total"], row["name"]),
    )

    bounds = _previous_period_bounds(date_from, date_to)
    previous = _totals(db, *bounds, level) if bounds else {"operational": 0, "financial": 0}
    previous_daily = _daily_series(db, *bounds, level) if bounds else []

    return {
        "date_from": date_from,
        "date_to": date_to,
        "group_ids": list(_LEVELS[level][2] or ()),
        "operational": totals["operational"],
        "financial": totals["financial"],
        "total": totals["operational"] + totals["financial"],
        "previous_operational": previous["operational"],
        "previous_financial": previous["financial"],
        "daily": _daily_series(db, date_from, date_to, level),
        "previous_daily": previous_daily,
        "attendants": attendant_rows,
    }
