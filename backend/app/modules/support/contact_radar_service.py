"""Radar de Contatos do Suporte Interno: de onde os clientes estão entrando em contato pelo OPA.

Cada atendimento do OPA aponta para um cliente (`customer_id`); `SupportContactGeo` (alimentada por
`contact_geo_sync`) diz a cidade, o bairro e a regional desse cliente no IXC. Aqui o atendimento é
agrupado por regional > cidade > bairro e comparado com o que é normal em cada nível:

- modo "janela" (ao vivo): últimos N minutos, comparados com a MESMA janela dos 7 dias anteriores;
- modo "período": de uma data a outra (dias inclusivos, fuso America/Porto_Velho), comparado com o
  período imediatamente anterior de mesmo tamanho.

As regionais seguem o agrupamento oficial (`normalize_regional_grouped`): São Miguel do Guaporé, Seringueiras e
São Francisco do Guaporé formam uma só (São Francisco do Guaporé), e São Felipe D'Oeste entra em Rolim de Moura.

A regional de cada contato é a da CIDADE do cliente (a regional onde está a maioria dos clientes dela), não
a do contrato de cada um: um cliente de Presidente Médici com o contrato cadastrado na filial de Ji-Paraná
entra em Presidente Médici. Cidade nova ou sem maioria clara cai na regional do próprio cliente.

Contagem principal por CLIENTE distinto, não por atendimento: um cliente que insiste não pode
inflar o número de uma cidade. Atendimento sem cliente identificado fica fora dos grupos e é
mostrado à parte ("não localizados"), para a tela não passar a impressão de cobertura total.

A leitura é agregada no banco (uma linha por cliente e canal), então um período de um mês não carrega
dezenas de milhares de atendimentos em memória.

Só leitura. Não expõe CPF, telefone nem nome de cliente."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.services.regional import normalize_regional_grouped

from .models import SupportContactGeo, SupportOpaAttendance, SupportOpaDimension
from .opa_filters import SUPPORT_TIMEZONE, TAG_SEPARATOR, _selected_values

WINDOW_CHOICES = (15, 30, 60, 180, 720, 1440)
MAX_RANGE_DAYS = 31
BASELINE_DAYS = 7
# Teto de linhas agregadas lidas por consulta (cliente x canal), só uma salvaguarda.
MAX_ROWS = 200000
MAX_SERIES_ROWS = 400000
# Calibração inicial, a revisar com dados reais: só marca "acima do usual" quem tem volume mínimo de
# clientes distintos E pelo menos o dobro do normal naquele recorte.
ELEVATED_MIN_CUSTOMERS = 5
ELEVATED_MIN_RATIO = 2.0
# Enquanto a localização dos clientes antigos não foi toda resolvida (carga inicial), o período de
# comparação tem cobertura menor que o atual e tudo pareceria "acima do usual". Abaixo desta cobertura
# na comparação o radar não marca alerta.
MIN_HISTORY_COVERAGE = 0.7
# E a cobertura da comparação tem de ser parecida com a do período atual: clientes recentes são resolvidos
# primeiro, então um histórico com 75% contra 96% agora inflaria a variação em ~30% e geraria alarme falso.
HISTORY_VS_CURRENT_MIN = 0.9
# Etiqueta que o atendimento tem mas que não está no cadastro local (o OPA só lista etiqueta por nome exato, então o
# cadastro não se refaz sozinho): aparece neutra, em vez de sumir e fazer o protocolo parecer sem etiqueta.
UNKNOWN_TAG_LABEL = "Etiqueta sem cadastro"
NO_REGIONAL_LABEL = "Regional não identificada"
NO_CITY_LABEL = "Cidade não informada"
NO_NEIGHBORHOOD_LABEL = "Bairro não informado"
# Bairros mostrados por cidade (Ji-Paraná tem centenas; o resto vira ruído numa tela de plantão).
TOP_NEIGHBORHOODS_PER_CITY = 50
LEVELS = ("regional", "city", "neighborhood")

Period = tuple[datetime, datetime]


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def period_bounds(date_from: date, date_to: date) -> Period:
    """Início e fim (exclusivo) em UTC dos dias inclusivos `date_from`..`date_to` no fuso do suporte."""
    start = datetime.combine(date_from, time.min, tzinfo=SUPPORT_TIMEZONE)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=SUPPORT_TIMEZONE)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def city_regionals(db: Session) -> dict[str, str]:
    """Regional de cada cidade: a que tem mais clientes localizados nela (empate: ordem alfabética). A regional
    do cadastro do cliente vem do contrato e, para uma minoria, é de outra filial que não a da cidade."""
    counts = db.execute(
        select(SupportContactGeo.city, SupportContactGeo.regional, func.count())
        .where(SupportContactGeo.status == "ok", SupportContactGeo.city.is_not(None), SupportContactGeo.regional.is_not(None))
        .group_by(SupportContactGeo.city, SupportContactGeo.regional)
    ).all()
    # Soma por regional AGRUPADA: uma cidade dividida entre as três filiais de São Francisco do Guaporé é
    # uma cidade de uma regional só, e não três regionais disputando.
    grouped: dict[tuple[str, str], int] = defaultdict(int)
    for city, regional, count in counts:
        grouped[(city, normalize_regional_grouped(regional))] += count
    best: dict[str, tuple[int, str]] = {}
    for (city, regional), count in grouped.items():
        current = best.get(city)
        if current is None or (-count, regional) < (-current[0], current[1]):
            best[city] = (count, regional)
    return {city: regional for city, (_, regional) in best.items()}


def _regional_of(city: str | None, own_regional: str | None, city_regional: dict[str, str]) -> str | None:
    """Regional (agrupada) de um contato: a da cidade; sem cidade conhecida, a do próprio cliente."""
    regional = city_regional.get(city) if city else None
    regional = regional or own_regional
    return normalize_regional_grouped(regional) if regional else None


def _grouped_scope(allowed_regionals: list[str]) -> set[str]:
    """Escopo do gestor regional na identidade agrupada: quem gere uma das três filiais de São Francisco
    enxerga as três, como na gamificação (as três apuram juntas)."""
    return {normalize_regional_grouped(regional) for regional in allowed_regionals}


def _load_rows(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    channel: str | None,
    department_id: str | None,
    allowed_regionals: list[str],
    city_regional: dict[str, str],
) -> list[dict[str, Any]]:
    contacts = func.count(SupportOpaAttendance.id)
    query = (
        select(
            SupportOpaAttendance.customer_id,
            SupportOpaAttendance.channel,
            SupportContactGeo.regional,
            SupportContactGeo.city,
            SupportContactGeo.neighborhood,
            SupportContactGeo.latitude,
            SupportContactGeo.longitude,
            SupportContactGeo.status,
            contacts.label("contacts"),
        )
        .outerjoin(SupportContactGeo, SupportContactGeo.opa_customer_id == SupportOpaAttendance.customer_id)
        .where(SupportOpaAttendance.opened_at >= start, SupportOpaAttendance.opened_at < end)
        .group_by(
            SupportOpaAttendance.customer_id,
            SupportOpaAttendance.channel,
            SupportContactGeo.regional,
            SupportContactGeo.city,
            SupportContactGeo.neighborhood,
            SupportContactGeo.latitude,
            SupportContactGeo.longitude,
            SupportContactGeo.status,
        )
        .limit(MAX_ROWS)
    )
    if channel:
        query = query.where(SupportOpaAttendance.channel == channel)
    if department_ids := _selected_values(department_id):
        query = query.where(SupportOpaAttendance.department_id.in_(department_ids))
    rows = [
        {
            "customer_id": row.customer_id,
            "channel": row.channel or "outro",
            # Regional da cidade; sem cidade conhecida, a do próprio cliente.
            "regional": _regional_of(row.city, row.regional, city_regional),
            "city": row.city,
            "neighborhood": row.neighborhood,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "located": row.status == "ok" and bool(row.city),
            "contacts": row.contacts,
        }
        for row in db.execute(query).all()
    ]
    if allowed_regionals:
        # Gestor regional só enxerga a própria regional: atendimento sem localização não pode ser atribuído
        # a ela, então sai (e o volume total não vaza). O filtro vem depois de trocar pela regional da cidade.
        scope = _grouped_scope(allowed_regionals)
        rows = [row for row in rows if row["located"] and row["regional"] in scope]
    return rows


def bucket_minutes(*, by_range: bool, window_minutes: int, range_days: int) -> int:
    """Largura de cada ponto da série: 5 min até 1 h, 15 min até 3 h, 1 h até 24 h; no período, 1 h
    até 2 dias e 1 dia acima disso."""
    if by_range:
        return 60 if range_days <= 2 else 1440
    if window_minutes <= 60:
        return 5
    if window_minutes <= 180:
        return 15
    return 60


def _series(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    step_minutes: int,
    aligned: bool,
    channel: str | None,
    department_id: str | None,
    allowed_regionals: list[str],
    city_regional: dict[str, str],
) -> list[dict[str, Any]]:
    """Contatos por intervalo de tempo (com os intervalos vazios preenchidos com zero, para o gráfico não
    "pular"). `aligned` alinha o primeiro intervalo a um múltiplo da largura (janela ao vivo); no período o
    primeiro intervalo começa na meia-noite de Porto Velho."""
    query = (
        select(
            SupportOpaAttendance.opened_at,
            SupportOpaAttendance.customer_id,
            SupportOpaAttendance.channel,
            SupportContactGeo.status,
            SupportContactGeo.city,
            SupportContactGeo.regional,
        )
        .outerjoin(SupportContactGeo, SupportContactGeo.opa_customer_id == SupportOpaAttendance.customer_id)
        .where(SupportOpaAttendance.opened_at >= start, SupportOpaAttendance.opened_at < end)
        .limit(MAX_SERIES_ROWS)
    )
    if channel:
        query = query.where(SupportOpaAttendance.channel == channel)
    if department_ids := _selected_values(department_id):
        query = query.where(SupportOpaAttendance.department_id.in_(department_ids))

    step = timedelta(minutes=step_minutes)
    first = start
    if aligned:
        epoch = int(start.timestamp()) // (step_minutes * 60) * (step_minutes * 60)
        first = datetime.fromtimestamp(epoch, tz=timezone.utc)
    points: dict[datetime, dict[str, Any]] = {}
    cursor = first
    while cursor < end:
        points[cursor] = {"start": cursor, "contacts": 0, "located_contacts": 0, "customers": set(), "by_channel": defaultdict(int)}
        cursor += step

    for opened_at, customer_id, row_channel, status, city, regional in db.execute(query).all():
        located = status == "ok" and bool(city)
        if allowed_regionals and not (located and _regional_of(city, regional, city_regional) in _grouped_scope(allowed_regionals)):
            continue
        moment = _as_utc(opened_at)
        key = first + ((moment - first) // step) * step
        point = points.get(key)
        if point is None:
            continue
        point["contacts"] += 1
        point["by_channel"][row_channel or "outro"] += 1
        if located:
            point["located_contacts"] += 1
            point["customers"].add(customer_id)
    return [
        {**point, "customers": len(point["customers"]), "by_channel": dict(point["by_channel"])}
        for point in points.values()
    ]


def _group_key(row: dict[str, Any], level: str) -> tuple[str, ...]:
    """Chave do grupo no nível pedido. A cidade e o bairro carregam a regional na chave porque a regional
    vem do contrato do cliente: a mesma cidade pode aparecer em mais de uma regional, e cada pedaço tem de
    ficar sob a sua."""
    regional = row["regional"] or NO_REGIONAL_LABEL
    if level == "regional":
        return (regional,)
    city = row["city"] or NO_CITY_LABEL
    if level == "city":
        return (regional, city)
    return (regional, city, row["neighborhood"] or NO_NEIGHBORHOOD_LABEL)


def _count_customers(rows: list[dict[str, Any]], level: str) -> dict[tuple[str, ...], set[str]]:
    groups: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for row in rows:
        if row["located"]:
            groups[_group_key(row, level)].add(row["customer_id"])
    return groups


def _baseline(
    db: Session,
    periods: list[Period],
    **filters: Any,
) -> tuple[dict[str, dict[tuple[str, ...], float]], float, dict[str, Any]]:
    """Média de clientes distintos por grupo (regional, cidade e bairro) nos períodos de comparação, a
    cobertura de localização desses períodos e os totais médios por período (para a variação dos cartões)."""
    totals: dict[str, dict[tuple[str, ...], float]] = {level: defaultdict(float) for level in LEVELS}
    located_contacts = 0
    all_contacts = 0
    customers_total = 0
    for start, end in periods:
        rows = _load_rows(db, start=start, end=end, **filters)
        all_contacts += sum(r["contacts"] for r in rows)
        located_contacts += sum(r["contacts"] for r in rows if r["located"])
        customers_total += len({r["customer_id"] for r in rows if r["located"]})
        for level in LEVELS:
            for key, customers in _count_customers(rows, level).items():
                totals[level][key] += len(customers)
    count = len(periods) or 1
    averaged = {level: {key: value / count for key, value in groups.items()} for level, groups in totals.items()}
    coverage = located_contacts / all_contacts if all_contacts else 0.0
    previous = {
        "contacts": round(all_contacts / count, 1),
        "customers": round(customers_total / count, 1),
        "coverage_pct": round(located_contacts * 100 / all_contacts, 1) if all_contacts else None,
    }
    return averaged, coverage, previous


def _centroids(rows: list[dict[str, Any]], level: str) -> dict[tuple[str, ...], tuple[float, float]]:
    sums: dict[tuple[str, ...], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    seen: set[tuple[tuple[str, ...], str]] = set()
    for row in rows:
        if not row["located"] or row["latitude"] is None or row["longitude"] is None:
            continue
        key = _group_key(row, level)
        # Cada cliente pesa uma vez (ele aparece uma linha por canal), senão quem liga várias vezes puxa
        # o centro do bairro.
        marker = (key, row["customer_id"] or "")
        if marker in seen:
            continue
        seen.add(marker)
        acc = sums[key]
        acc[0] += row["latitude"]
        acc[1] += row["longitude"]
        acc[2] += 1
    return {key: (acc[0] / acc[2], acc[1] / acc[2]) for key, acc in sums.items() if acc[2]}


def _stat(customers: int, baseline: float, alerts_enabled: bool) -> dict[str, Any]:
    ratio = round(customers / baseline, 1) if baseline >= 0.5 else None
    elevated = alerts_enabled and customers >= ELEVATED_MIN_CUSTOMERS and customers >= ELEVATED_MIN_RATIO * max(baseline, 1.0)
    return {"customers": customers, "baseline": round(baseline, 1), "ratio": ratio, "elevated": elevated}


def _order(item: dict[str, Any], name_key: str) -> tuple[Any, ...]:
    # Acima do usual primeiro, depois quem tem mais clientes; nome só desempata.
    return (not item["elevated"], -item["customers"], -item["contacts"], item[name_key])


def _build_tree(
    located: list[dict[str, Any]],
    baseline: dict[str, dict[tuple[str, ...], float]],
    alerts_enabled: bool,
) -> list[dict[str, Any]]:
    """Regionais com as cidades dentro e os bairros dentro de cada cidade, cada nível com a própria
    contagem de clientes distintos e a própria comparação com o habitual."""
    customers = {level: _count_customers(located, level) for level in LEVELS}
    contacts: dict[str, dict[tuple[str, ...], int]] = {level: defaultdict(int) for level in LEVELS}
    for row in located:
        for level in LEVELS:
            contacts[level][_group_key(row, level)] += row["contacts"]
    centroids = {level: _centroids(located, level) for level in ("city", "neighborhood")}

    def stats(level: str, key: tuple[str, ...]) -> dict[str, Any]:
        item = {"contacts": contacts[level][key], **_stat(len(customers[level][key]), baseline[level].get(key, 0.0), alerts_enabled)}
        if level in centroids:
            point = centroids[level].get(key)
            item["latitude"], item["longitude"] = (point if point else (None, None))
        return item

    neighborhoods_by_city: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for key in customers["neighborhood"]:
        neighborhoods_by_city[key[:2]].append({"neighborhood": key[2], **stats("neighborhood", key)})
    cities_by_regional: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for key in customers["city"]:
        neighborhoods = sorted(neighborhoods_by_city[key], key=lambda i: _order(i, "neighborhood"))
        cities_by_regional[key[:1]].append(
            {"city": key[1], **stats("city", key), "neighborhoods": neighborhoods[:TOP_NEIGHBORHOODS_PER_CITY]}
        )
    tree = [
        {"regional": key[0], **stats("regional", key), "cities": sorted(cities_by_regional[key], key=lambda i: _order(i, "city"))}
        for key in customers["regional"]
    ]
    return sorted(tree, key=lambda i: _order(i, "regional"))


def _period(
    *, window_minutes: int, date_from: date | None, date_to: date | None, now: datetime
) -> tuple[datetime, datetime]:
    if date_from is not None and date_to is not None:
        return period_bounds(date_from, date_to)
    return now - timedelta(minutes=window_minutes), now + timedelta(seconds=1)


def _tags_by_id(db: Session, tag_ids: set[str]) -> dict[str, dict[str, Any]]:
    """Nome e cor (a mesma do OPA: yellow, blue, red, gray, green, purple, orange) de cada etiqueta."""
    if not tag_ids:
        return {}
    rows = db.execute(
        select(SupportOpaDimension.source_id, SupportOpaDimension.name, SupportOpaDimension.payload_json).where(
            SupportOpaDimension.dimension_type == "tag", SupportOpaDimension.source_id.in_(tag_ids)
        )
    ).all()
    found: dict[str, dict[str, Any]] = {}
    for source_id, name, payload in rows:
        label = (name or (payload or {}).get("nome") or "").strip()
        if label:
            found[source_id] = {"id": source_id, "name": label, "color": ((payload or {}).get("cor") or None), "known": True}
    return found


def list_protocols(
    db: Session,
    *,
    regional: str,
    city: str,
    neighborhood: str | None = None,
    window_minutes: int = 60,
    date_from: date | None = None,
    date_to: date | None = None,
    channel: str | None = None,
    department_id: str | None = None,
    allowed_regionals: list[str],
    deny_all: bool,
    limit: int = 50,
    offset: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Protocolos do OPA de uma cidade (ou de um bairro dela, com `neighborhood`) no mesmo recorte do radar, com as
    etiquetas de cada um (nome e cor do OPA). A cidade só tem protocolos sob a regional em que o radar a mostra (a da maioria dos clientes dela);
    pedido de outra regional, ou fora do escopo do gestor, volta vazio. Não traz nome, CPF nem telefone."""
    empty = {"total": 0, "limit": limit, "offset": offset, "items": []}
    if deny_all:
        return empty
    now = _as_utc(now) if now else datetime.now(timezone.utc)
    city_regional = city_regionals(db)
    effective = city_regional.get(city)
    requested = None if regional == NO_REGIONAL_LABEL else normalize_regional_grouped(regional)
    if effective != requested:
        return empty
    if allowed_regionals and (effective is None or effective not in _grouped_scope(allowed_regionals)):
        return empty

    start, end = _period(window_minutes=window_minutes, date_from=date_from, date_to=date_to, now=now)
    conditions = [
        SupportContactGeo.status == "ok",
        SupportContactGeo.city == city,
        SupportOpaAttendance.opened_at >= start,
        SupportOpaAttendance.opened_at < end,
    ]
    if channel:
        conditions.append(SupportOpaAttendance.channel == channel)
    if department_ids := _selected_values(department_id):
        conditions.append(SupportOpaAttendance.department_id.in_(department_ids))
    if neighborhood:
        if neighborhood == NO_NEIGHBORHOOD_LABEL:
            # Cliente sem bairro no cadastro: é o grupo "Bairro não informado" do radar.
            conditions.append(or_(SupportContactGeo.neighborhood.is_(None), SupportContactGeo.neighborhood == ""))
        else:
            conditions.append(SupportContactGeo.neighborhood == neighborhood)
    joined = SupportContactGeo.opa_customer_id == SupportOpaAttendance.customer_id

    total = int(
        db.scalar(select(func.count(SupportOpaAttendance.id)).join(SupportContactGeo, joined).where(*conditions)) or 0
    )
    rows = db.execute(
        select(
            SupportOpaAttendance.source_id,
            SupportOpaAttendance.protocol,
            SupportOpaAttendance.opened_at,
            SupportOpaAttendance.status,
            SupportOpaAttendance.channel,
            SupportOpaAttendance.department_name,
            SupportOpaAttendance.attendant_name,
            SupportOpaAttendance.tag_ids_text,
            SupportContactGeo.neighborhood,
        )
        .join(SupportContactGeo, joined)
        .where(*conditions)
        .order_by(SupportOpaAttendance.opened_at.desc(), SupportOpaAttendance.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    ids_per_row = [[tag for tag in (row.tag_ids_text or "").split(TAG_SEPARATOR) if tag] for row in rows]
    tags = _tags_by_id(db, {tag for ids in ids_per_row for tag in ids})
    items = [
        {
            "source_id": row.source_id,
            "protocol": row.protocol,
            "opened_at": _as_utc(row.opened_at),
            "status": row.status,
            "channel": row.channel,
            "department_name": row.department_name,
            "attendant_name": row.attendant_name,
            "neighborhood": row.neighborhood,
            "tags": [tags.get(tag) or {"id": tag, "name": UNKNOWN_TAG_LABEL, "color": None, "known": False} for tag in ids],
        }
        for row, ids in zip(rows, ids_per_row)
    ]
    return {"total": total, "limit": limit, "offset": offset, "items": items}


def build_radar(
    db: Session,
    *,
    window_minutes: int = 60,
    date_from: date | None = None,
    date_to: date | None = None,
    channel: str | None = None,
    department_id: str | None = None,
    allowed_regionals: list[str],
    deny_all: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = _as_utc(now) if now else datetime.now(timezone.utc)
    by_range = date_from is not None and date_to is not None
    if by_range:
        start, end = period_bounds(date_from, date_to)
        range_days = (date_to - date_from).days + 1
        # Comparação: o período imediatamente anterior, do mesmo tamanho.
        baseline_periods = [(start - (end - start), start)]
    else:
        window = timedelta(minutes=window_minutes)
        range_days = 0
        start, end = now - window, now + timedelta(seconds=1)
        baseline_periods = [(now - window - timedelta(days=d), now - timedelta(days=d)) for d in range(1, BASELINE_DAYS + 1)]

    header = {
        "mode": "range" if by_range else "window",
        "window_minutes": None if by_range else window_minutes,
        "date_from": date_from if by_range else None,
        "date_to": date_to if by_range else None,
        "generated_at": now,
    }
    if deny_all:
        return {
            **header,
            "alerts_enabled": False,
            "totals": {"contacts": 0, "customers": 0, "located_contacts": 0, "unlocated_contacts": 0, "coverage_pct": None},
            "by_channel": [],
            "regionals": [],
            "series": {"bucket_minutes": 60, "points": []},
            "previous": {"contacts": 0.0, "customers": 0.0, "coverage_pct": None},
        }

    filters = {
        "channel": channel,
        "department_id": department_id,
        "allowed_regionals": allowed_regionals,
        "city_regional": city_regionals(db),
    }
    rows = _load_rows(db, start=start, end=end, **filters)
    scoped = bool(allowed_regionals)
    located = [r for r in rows if r["located"]]

    baseline, history_coverage, previous = _baseline(db, baseline_periods, **filters)
    # Gestor regional já recebe só o que está localizado (filtro na consulta), então a cobertura dele é 1.
    current_coverage = sum(r["contacts"] for r in located) / sum(r["contacts"] for r in rows) if rows else 0.0
    alerts_enabled = scoped or (history_coverage >= MIN_HISTORY_COVERAGE and history_coverage >= HISTORY_VS_CURRENT_MIN * current_coverage)

    by_channel: dict[str, int] = defaultdict(int)
    for row in rows:
        by_channel[row["channel"]] += row["contacts"]
    step_minutes = bucket_minutes(by_range=by_range, window_minutes=window_minutes, range_days=range_days)

    all_contacts = sum(r["contacts"] for r in rows)
    located_contacts = sum(r["contacts"] for r in located)
    unlocated = 0 if scoped else all_contacts - located_contacts
    coverage = None if scoped or not all_contacts else round(located_contacts * 100 / all_contacts, 1)
    return {
        **header,
        "alerts_enabled": alerts_enabled,
        "totals": {
            "contacts": located_contacts if scoped else all_contacts,
            "customers": len({r["customer_id"] for r in located}),
            "located_contacts": located_contacts,
            "unlocated_contacts": unlocated,
            "coverage_pct": coverage,
        },
        "by_channel": sorted(
            ({"channel": name, "contacts": count} for name, count in by_channel.items()),
            key=lambda i: -i["contacts"],
        ),
        "regionals": _build_tree(located, baseline, alerts_enabled),
        "series": {
            "bucket_minutes": step_minutes,
            "points": _series(db, start=start, end=end, step_minutes=step_minutes, aligned=not by_range, **filters),
        },
        "previous": previous,
    }
