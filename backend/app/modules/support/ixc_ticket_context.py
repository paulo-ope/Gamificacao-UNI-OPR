"""Fase 2 do plano de evolução analítica do Atendimento IXC (2026-09-14): contrato de contexto
único, generalizando `_priorities_for_scopes`/breakdown por nível numa única API baseada em
`dimension` + filtros independentes, inspirado no `control_tower()` de Operações
(`app/modules/operations/services.py`) - `path`/`next_level` calculado a partir de quais filtros
já estão fixados, em vez de uma hierarquia de rota rígida.

Diferença deliberada em relação a `ixc_ticket_overview.py` (Visão Geral, mês-calendário +
histórico de N meses no mesmo corte de dia): este módulo usa o MESMO modelo de período livre
(`date_from`/`date_to` + janela anterior de mesmo tamanho) que `ixc_ticket_queries.py`
(drill-down) já usa - unifica em cima do modelo mais simples dos dois, não inventa um terceiro.
Isso é ADITIVO: as rotas antigas (`/ixc/tickets/overview`, `/priorities`, `/breakdown`, ...)
continuam existindo e servindo o frontend atual sem mudança (estratégia strangler, item 15 do
plano) - nenhuma delas foi tocada.
"""

from __future__ import annotations

import base64
import json
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.operations.models import OperationCustomerContract

from .ixc_ticket_overview import CRITICAL_DEVIATION_PCT, IMPROVING_DEVIATION_PCT
from .ixc_ticket_queries import (
    ACTIVE_CONTRACT_STATUS,
    _apply_extra_filters,
    _apply_period,
    _deviation_pct,
    _previous_period_bounds,
    _previous_period_counts,
    city_breakdown,
    neighborhood_breakdown,
    reason_breakdown,
    regional_breakdown,
)
from .ixc_ticket_reach import reach_summary
from .models import SupportIxcTicket

# Ordem-padrão de drill quando `dimension` não é informado - mesmo espírito do
# `CONTROL_TOWER_LEVELS` de Operações: cada nível só entra na lista se ainda não estiver fixado
# por um filtro. `subject`/`sector` não têm hierarquia entre si (são ortogonais, não pai/filho),
# então só `subject` aparece como "próximo nível" natural depois de bairro.
DIMENSION_ORDER = ("regional", "city", "neighborhood", "subject")

# Versão da lógica de agrupamento embutida no `context_key` (item 3 da correção, 2026-09-17) -
# muda só se o SIGNIFICADO dos filtros mudar (ex.: se um dia `subject_id` passar a aceitar uma
# sintaxe diferente) - uma chave de versão antiga decodificada contra a lógica nova poderia
# reproduzir um agrupamento diferente do que gerou o alerta original.
CONTEXT_KEY_VERSION = "v1"


def build_context_key(
    *,
    regional: str | None = None,
    city: str | None = None,
    neighborhood: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> str:
    """Identificador DETERMINÍSTICO de um agrupamento (item 3 da correção pedida pelo usuário,
    2026-09-17: "evite ID aleatório se o mesmo agrupamento lógico puder ser reproduzido") - os
    MESMOS filtros sempre geram a MESMA chave, e a chave é decodificável (`parse_context_key`),
    não um hash opaco que exigiria uma tabela de-para no banco. Serializa como JSON compacto com
    chaves ordenadas (determinístico independente da ordem dos argumentos) e codifica em
    base64 URL-safe só pra caber num único segmento de rota/query sem escapar caracteres especiais
    (nomes de regional têm espaço e hífen)."""
    payload = {
        "v": CONTEXT_KEY_VERSION,
        "regional": regional,
        "city": city,
        "neighborhood": neighborhood,
        "subject_id": subject_id,
        "sector_id": sector_id,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def parse_context_key(context_key: str) -> dict[str, Any]:
    """Inverso de `build_context_key` - devolve os filtros originais, prontos pra passar direto
    pra `resolve_context`/`ixc_ticket_queries.list_tickets`. Levanta `ValueError` (traduzido em
    400 pelo router) pra chave malformada ou de versão não suportada - nunca falha em silêncio
    devolvendo um agrupamento diferente do pedido."""
    try:
        padded = context_key + "=" * (-len(context_key) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw)
    except Exception as exc:
        raise ValueError(f"context_key inválida: {context_key!r}") from exc
    if payload.get("v") != CONTEXT_KEY_VERSION:
        raise ValueError(f"context_key de versão não suportada: {payload.get('v')!r}")
    return {
        "regional": payload.get("regional"),
        "city": payload.get("city"),
        "neighborhood": payload.get("neighborhood"),
        "subject_id": payload.get("subject_id"),
        "sector_id": payload.get("sector_id"),
        "date_from": date.fromisoformat(payload["date_from"]) if payload.get("date_from") else None,
        "date_to": date.fromisoformat(payload["date_to"]) if payload.get("date_to") else None,
    }


def _classify_severity(deviation_pct: float | None) -> str:
    if deviation_pct is None:
        return "sem_dado"
    if deviation_pct >= CRITICAL_DEVIATION_PCT:
        return "critico"
    if deviation_pct <= IMPROVING_DEVIATION_PCT:
        return "em_melhora"
    return "dentro_da_curva"


def _next_dimension(*, regional: str | None, city: str | None, neighborhood: str | None, subject_id: str | None) -> str | None:
    if regional is None:
        return "regional"
    if city is None:
        return "city"
    if neighborhood is None:
        return "neighborhood"
    if subject_id is None:
        return "subject"
    return None


def _peer_rate(item: dict[str, Any], *, use_rate: bool) -> float | int | None:
    if use_rate:
        return item.get("tickets_per_1000_contracts")
    return item["ticket_count"]


def _peers_stats(
    *, current_key: str | None, current_ticket_count: int, current_tickets_per_1000: float | None, sibling_items: list[dict[str, Any]]
) -> tuple[float | None, float | None]:
    """Desvio do escopo atual vs. a MÉDIA DOS PARES (demais itens da mesma lista de irmãos, ex.:
    demais regionais quando o escopo é uma regional, demais cidades da mesma regional quando o
    escopo é uma cidade) - fallback de severidade quando o histórico próprio (`deviation_pct`) não
    tem amostra suficiente (item 1 da correção pedida pelo usuário, 2026-09-17: "risco de falso
    negativo especialmente em regionais pequenas"). Reaproveita as mesmas listas que
    `priorities_for_context` já calcula (`regional_breakdown`/`city_breakdown`/
    `neighborhood_breakdown`), não duplica agregação nova - mesmo espírito de pares já usado em
    `ixc_ticket_overview._priorities_for_scopes`, só que a lista de pares vem de UMA query
    (a própria função de breakdown), não de N chamadas por valor.

    Usa `tickets_per_1000_contracts` como métrica quando o escopo atual tem essa taxa disponível
    (regional/cidade com contratos cadastrados); cai pra `ticket_count` bruto quando não (bairro,
    ou cidade sem base ativa suficiente) - nunca mistura as duas unidades entre o valor atual e os
    pares. Devolve `(deviation_pct, peers_avg)` - o segundo valor alimenta o `expected` numérico
    dos `reason_codes` (item 6 da correção, 2026-09-17: "a IA deve entender o motivo do sinal
    lendo somente aquele item")."""
    if not sibling_items:
        return None, None
    use_rate = current_tickets_per_1000 is not None
    current_value = current_tickets_per_1000 if use_rate else current_ticket_count
    if current_value is None:
        return None, None
    peer_values = [
        value
        for item in sibling_items
        if item["key"] != current_key
        for value in [_peer_rate(item, use_rate=use_rate)]
        if value is not None
    ]
    if not peer_values:
        return None, None
    peers_avg = sum(peer_values) / len(peer_values)
    if not peers_avg:
        return None, None
    return round((current_value - peers_avg) / peers_avg * 100, 1), round(peers_avg, 2)


def _resolve_severity_with_basis(
    *, own_deviation_pct: float | None, peers_deviation_pct: float | None
) -> tuple[str, str, float | None]:
    """`severity_basis` explícito - "historical" (padrão), "peers" (fallback quando o histórico
    próprio não tem amostra suficiente) ou "insufficient_data" (nem histórico nem pares
    confiáveis) - NUNCA classifica ausência de amostra como "dentro da curva" (regra explícita do
    usuário, 2026-09-17: "nunca transformar ausência de amostra em normalidade"). Devolve também
    o desvio EFETIVO usado (o que decidiu a severidade), pra quem consome não precisar adivinhar
    qual dos dois campos foi a base."""
    if own_deviation_pct is not None:
        return _classify_severity(own_deviation_pct), "historical", own_deviation_pct
    if peers_deviation_pct is not None:
        return _classify_severity(peers_deviation_pct), "peers", peers_deviation_pct
    return "sem_dado", "insufficient_data", None


def _scope_where(*, regional: str | None, city: str | None, neighborhood: str | None) -> tuple:
    clauses = []
    if regional:
        clauses.append(SupportIxcTicket.regional == regional)
    if city:
        clauses.append(SupportIxcTicket.city == city)
    if neighborhood:
        clauses.append(SupportIxcTicket.neighborhood == neighborhood)
    return tuple(clauses)


def _scope_ticket_count(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    regional: str | None,
    city: str | None,
    neighborhood: str | None,
    subject_id: str | None,
    sector_id: str | None,
) -> int:
    query = select(func.count(SupportIxcTicket.id))
    where = _scope_where(regional=regional, city=city, neighborhood=neighborhood)
    if where:
        query = query.where(*where)
    query = _apply_period(query, SupportIxcTicket.created_at, date_from, date_to)
    query = _apply_extra_filters(query, subject_id=subject_id, sector_id=sector_id)
    return int(db.scalar(query) or 0)


def _scope_contract_count(db: Session, *, regional: str | None, city: str | None) -> int | None:
    """Só existe base de contratos ativos cadastrada por regional/cidade - no nível bairro/motivo
    não há `OperationCustomerContract.neighborhood` populado o bastante pra ser confiável (mesmo
    limite já documentado em `ixc_ticket_queries.MIN_CITY_COVERAGE_PCT`), então devolve `None`
    (não calcula) em vez de um número que parece preciso e não é."""
    if not regional and not city:
        return None
    query = select(func.count(OperationCustomerContract.id)).where(
        OperationCustomerContract.status == ACTIVE_CONTRACT_STATUS
    )
    if regional:
        query = query.where(OperationCustomerContract.regional == regional)
    if city:
        query = query.where(OperationCustomerContract.city == city)
    return int(db.scalar(query) or 0)


def driver_decomposition_for_period(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    regional: str | None = None,
    city: str | None = None,
    neighborhood: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
) -> list[dict[str, Any]]:
    """Mesma ideia de `ixc_ticket_overview.driver_decomposition` (excesso por motivo +
    `contribution_pct`), mas com "esperado" = contagem do MESMO motivo na janela anterior de
    mesmo tamanho (modelo de período livre), em vez da média de N meses-calendário anteriores -
    coerente com o resto deste módulo, que já usa esse modelo pro drill-down."""
    where = _scope_where(regional=regional, city=city, neighborhood=neighborhood)

    current_query = select(SupportIxcTicket.subject_name, func.count(SupportIxcTicket.id)).group_by(
        SupportIxcTicket.subject_name
    )
    if where:
        current_query = current_query.where(*where)
    current_query = _apply_period(current_query, SupportIxcTicket.created_at, date_from, date_to)
    current_query = _apply_extra_filters(current_query, subject_id=subject_id, sector_id=sector_id)
    current_counts = {(name or "Não informado"): count for name, count in db.execute(current_query).all()}

    previous_counts = _previous_period_counts(
        db,
        group_column=SupportIxcTicket.subject_name,
        date_from=date_from,
        date_to=date_to,
        subject_id=subject_id,
        sector_id=sector_id,
        extra_where=where,
    )

    items: list[dict[str, Any]] = []
    for name, current in current_counts.items():
        expected = previous_counts.get(name, 0)
        excess = current - expected
        items.append({"subject_name": name, "current": current, "expected": expected, "excess": excess})

    total_positive_excess = sum(item["excess"] for item in items if item["excess"] > 0)
    for item in items:
        item["contribution_pct"] = (
            round(item["excess"] / total_positive_excess * 100, 1)
            if total_positive_excess > 0 and item["excess"] > 0
            else 0.0
        )

    items.sort(key=lambda item: item["excess"], reverse=True)
    return items


def geographic_concentration(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    regional: str | None,
    city: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
) -> dict[str, Any] | None:
    """Item 5 da correção pedida (2026-09-17): "não quero que a IA agregue na mão" - principal
    cidade e principal bairro do escopo, calculados aqui, não no consumidor. `share_pct` dos DOIS
    níveis é sobre o TOTAL DO ESCOPO ATUAL (não em cascata cidade->bairro) - respondem à MESMA
    pergunta ("que fatia disso está aqui"), não perguntas encadeadas.

    Só calculável com `regional` fixado (sem regional o universo de cidades é grande demais e
    cidades de nomes iguais existem em regionais diferentes). Com `city` já fixado, só a cidade já
    está decidida - calcula só o bairro dentro dela. Com `neighborhood` já fixado, não há mais
    nível geográfico abaixo - devolve `None` (não "zero", a pergunta deixa de fazer sentido).

    LEMBRETE (mesmo do plano, seção 5): `city`/`neighborhood` vêm do CADASTRO DO CLIENTE, não são
    localização exata de uma falha de rede - concentração aqui é indício, não prova de causa."""
    if not regional:
        return None
    total = _scope_ticket_count(
        db, date_from=date_from, date_to=date_to, regional=regional, city=city, neighborhood=None,
        subject_id=subject_id, sector_id=sector_id,
    )
    if not total:
        return None

    result: dict[str, Any] = {"city": None, "neighborhood": None}
    top_city_key = city
    if city is None:
        cities = city_breakdown(db, regional=regional, date_from=date_from, date_to=date_to, subject_id=subject_id, sector_id=sector_id)
        top_city = max(cities, key=lambda item: item["ticket_count"], default=None)
        if top_city is None or top_city["ticket_count"] <= 0:
            return result
        result["city"] = {
            "value": top_city["label"],
            "count": top_city["ticket_count"],
            "share_pct": round(top_city["ticket_count"] / total * 100, 1),
        }
        top_city_key = top_city["key"]

    neighborhoods = neighborhood_breakdown(
        db, regional=regional, city=top_city_key, date_from=date_from, date_to=date_to, subject_id=subject_id, sector_id=sector_id
    )
    top_neighborhood = max(neighborhoods, key=lambda item: item["ticket_count"], default=None)
    if top_neighborhood is not None and top_neighborhood["ticket_count"] > 0:
        result["neighborhood"] = {
            "value": top_neighborhood["label"],
            "count": top_neighborhood["ticket_count"],
            "share_pct": round(top_neighborhood["ticket_count"] / total * 100, 1),
        }
    return result


def resolve_context(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    regional: str | None = None,
    city: str | None = None,
    neighborhood: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
) -> dict[str, Any]:
    """Contexto agregado de um escopo (qualquer combinação de filtros) - o "resumo executivo" que
    alimenta o topo da tela única do item 4 do plano: contagem/base/desvio/severidade, abrangência
    (`ixc_ticket_reach`), motivo dominante do excesso e qual é o próximo nível relevante pra
    continuar o drill (`next_dimension`, `None` quando já não há nível seguinte a abrir)."""
    ticket_count = _scope_ticket_count(
        db,
        date_from=date_from,
        date_to=date_to,
        regional=regional,
        city=city,
        neighborhood=neighborhood,
        subject_id=subject_id,
        sector_id=sector_id,
    )
    contract_count = _scope_contract_count(db, regional=regional, city=city)
    tickets_per_1000 = round(ticket_count / contract_count * 1000, 2) if contract_count else None

    previous_ticket_count = 0
    bounds = _previous_period_bounds(date_from, date_to)
    if bounds is not None:
        previous_from, previous_to = bounds
        previous_ticket_count = _scope_ticket_count(
            db,
            date_from=previous_from,
            date_to=previous_to,
            regional=regional,
            city=city,
            neighborhood=neighborhood,
            subject_id=subject_id,
            sector_id=sector_id,
        )
    deviation_pct = _deviation_pct(ticket_count, previous_ticket_count)

    # Fallback de pares (item 1, 2026-09-17): pares são os IRMÃOS do nível mais fundo já fixado -
    # demais regionais quando só `regional` está fixado, demais cidades DA MESMA regional quando
    # `city` também está, demais bairros DA MESMA cidade quando `neighborhood` também está. Sem
    # nenhum nível fixado (operação inteira), não existe "par" - só há uma operação.
    peers_deviation_pct: float | None = None
    peers_avg: float | None = None
    if neighborhood is not None:
        siblings = neighborhood_breakdown(db, regional=regional, city=city, date_from=date_from, date_to=date_to, subject_id=subject_id, sector_id=sector_id)
        peers_deviation_pct, peers_avg = _peers_stats(
            current_key=neighborhood, current_ticket_count=ticket_count, current_tickets_per_1000=tickets_per_1000, sibling_items=siblings
        )
    elif city is not None:
        siblings = city_breakdown(db, regional=regional, date_from=date_from, date_to=date_to, subject_id=subject_id, sector_id=sector_id)
        peers_deviation_pct, peers_avg = _peers_stats(
            current_key=city, current_ticket_count=ticket_count, current_tickets_per_1000=tickets_per_1000, sibling_items=siblings
        )
    elif regional is not None:
        siblings = regional_breakdown(db, date_from=date_from, date_to=date_to, subject_id=subject_id, sector_id=sector_id)
        peers_deviation_pct, peers_avg = _peers_stats(
            current_key=regional, current_ticket_count=ticket_count, current_tickets_per_1000=tickets_per_1000, sibling_items=siblings
        )

    severity, severity_basis, effective_deviation_pct = _resolve_severity_with_basis(
        own_deviation_pct=deviation_pct, peers_deviation_pct=peers_deviation_pct
    )

    drivers = driver_decomposition_for_period(
        db,
        date_from=date_from,
        date_to=date_to,
        regional=regional,
        city=city,
        neighborhood=neighborhood,
        subject_id=subject_id,
        sector_id=sector_id,
    )
    top_driver = drivers[0] if drivers else None

    reach = reach_summary(
        db,
        date_from=date_from,
        date_to=date_to,
        regional=regional,
        city=city,
        subject_id=subject_id,
        sector_id=sector_id,
        ticket_count=ticket_count if not neighborhood else None,
    )

    # Concentração geográfica (item 5) - só faz sentido enquanto ainda existe nível geográfico
    # abaixo do escopo atual pra decompor (regional sem cidade fixada, ou cidade sem bairro).
    concentration_geo = None
    if neighborhood is None and (regional is not None):
        concentration_geo = geographic_concentration(
            db, date_from=date_from, date_to=date_to, regional=regional, city=city, subject_id=subject_id, sector_id=sector_id
        )

    return {
        "context_key": build_context_key(
            regional=regional, city=city, neighborhood=neighborhood, subject_id=subject_id, sector_id=sector_id,
            date_from=date_from, date_to=date_to,
        ),
        "regional": regional,
        "city": city,
        "neighborhood": neighborhood,
        "date_from": date_from,
        "date_to": date_to,
        "ticket_count": ticket_count,
        "contract_count": contract_count,
        "tickets_per_1000_contracts": tickets_per_1000,
        "previous_ticket_count": previous_ticket_count,
        "deviation_pct": deviation_pct,
        "peers_deviation_pct": peers_deviation_pct,
        "peers_avg": peers_avg,
        "effective_deviation_pct": effective_deviation_pct,
        # "Esperado" numérico que sustenta `effective_deviation_pct` - o mesmo período anterior
        # quando `severity_basis="historical"`, a média dos pares quando `"peers"`. Existe pra
        # `reason_codes` (item 6) poder trazer `current`/`expected` sem o consumidor ter que saber
        # qual dos dois campos brutos usar.
        "expected": peers_avg if severity_basis == "peers" else (previous_ticket_count if severity_basis == "historical" else None),
        "severity": severity,
        "severity_basis": severity_basis,
        "next_dimension": _next_dimension(regional=regional, city=city, neighborhood=neighborhood, subject_id=subject_id),
        "reach": reach,
        "top_driver": top_driver,
        "drivers": drivers,
        "geographic_concentration": concentration_geo,
    }


def priorities_for_context(
    db: Session,
    *,
    dimension: str,
    date_from: date | None,
    date_to: date | None,
    regional: str | None = None,
    city: str | None = None,
    neighborhood: str | None = None,
    subject_id: str | None = None,
    sector_id: str | None = None,
) -> list[dict[str, Any]]:
    """Ranking do PRÓXIMO NÍVEL (item 3 do plano: filtros independentes escolhem a dimensão, não
    uma rota fixa por nível) - camada fina sobre as funções de breakdown já existentes e testadas
    em `ixc_ticket_queries.py`, só acrescentando `severity` (mesmos limiares da Visão Geral) e o
    rótulo de `dimension` em cada item."""
    if dimension not in DIMENSION_ORDER:
        raise ValueError(f"dimension inválida: {dimension!r}")
    if dimension in ("city", "neighborhood", "subject") and not regional:
        raise ValueError("regional é obrigatório para esta dimensão")
    if dimension in ("neighborhood", "subject") and not city:
        raise ValueError("city é obrigatório para esta dimensão")
    if dimension == "subject" and not neighborhood:
        raise ValueError("neighborhood é obrigatório para a dimensão 'subject'")

    if dimension == "regional":
        items = regional_breakdown(db, date_from=date_from, date_to=date_to, subject_id=subject_id, sector_id=sector_id)
    elif dimension == "city":
        items = city_breakdown(
            db, regional=regional, date_from=date_from, date_to=date_to, subject_id=subject_id, sector_id=sector_id
        )
    elif dimension == "neighborhood":
        items = neighborhood_breakdown(
            db,
            regional=regional,
            city=city,
            date_from=date_from,
            date_to=date_to,
            subject_id=subject_id,
            sector_id=sector_id,
        )
    else:
        items = reason_breakdown(
            db,
            regional=regional,
            city=city,
            neighborhood=neighborhood,
            date_from=date_from,
            date_to=date_to,
            subject_id=subject_id,
            sector_id=sector_id,
        )

    # Filtros já fixados ANTES deste nível - a chave de cada item é esses filtros + o próprio item
    # no lugar da dimensão sendo listada (item 3: "a partir dessa chave deve ser possível realizar
    # drill sem a IA reconstruir manualmente os parâmetros").
    base_filters = {"regional": regional, "city": city, "neighborhood": neighborhood, "subject_id": subject_id, "sector_id": sector_id}
    key_field = {"regional": "regional", "city": "city", "neighborhood": "neighborhood", "subject": "subject_id"}[dimension]

    for item in items:
        item["dimension"] = dimension
        peers_deviation_pct, _peers_avg = _peers_stats(
            current_key=item["key"],
            current_ticket_count=item["ticket_count"],
            current_tickets_per_1000=item.get("tickets_per_1000_contracts"),
            sibling_items=items,
        )
        severity, severity_basis, _effective = _resolve_severity_with_basis(
            own_deviation_pct=item["deviation_pct"], peers_deviation_pct=peers_deviation_pct
        )
        item["peers_deviation_pct"] = peers_deviation_pct
        item["severity"] = severity
        item["severity_basis"] = severity_basis
        item["context_key"] = build_context_key(
            **{**base_filters, key_field: item["key"]}, date_from=date_from, date_to=date_to
        )
    return items
