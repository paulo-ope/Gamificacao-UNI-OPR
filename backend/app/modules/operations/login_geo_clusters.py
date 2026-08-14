from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from .models import OperationLoginCurrentStatus

EARTH_RADIUS_METERS = 6_371_000.0

# 'S' é o único valor que o IXC usa pra "conectado normalmente" (visto em amostra real de produção:
# 'S', 'SS' = sem sinal, 'N' = desconectado, '' = nunca reportou).
#
# Achado real comparando duas capturas ~2h30 apart em produção: 'SS' é praticamente permanente
# (99,6% dos logins que estavam 'SS' continuavam 'SS' 2h30 depois) - é uma característica crônica
# de equipamento/login, NÃO um evento de queda. Já 'N' tem movimento real (351 logins caíram
# S->N, 489 reconectaram N->S no mesmo intervalo). Por isso a detecção de cluster NÃO olha o status
# estático (isso só acharia "áreas com muito equipamento velho", visto na prática: um cluster de
# 1000+ logins numa única cidade) - ela olha quem TRANSICIONOU recentemente para 'N' vindo de um
# estado que não era 'N', que é o sinal real de "acabou de cair".
_DISCONNECTED_VALUE = "N"


@dataclass
class OfflineLoginPoint:
    login_id: int
    login: str
    online: str
    latitude: float
    longitude: float
    last_disconnected_at: datetime | None


@dataclass
class OfflineLoginCluster:
    center_latitude: float
    center_longitude: float
    radius_meters: float
    logins: list[OfflineLoginPoint]

    @property
    def size(self) -> int:
        return len(self.logins)


def _fetch_recent_disconnections(db: Session, *, window_minutes: int) -> list[OfflineLoginPoint]:
    """Logins que estão 'N' agora E cuja mudança pra 'N' aconteceu dentro de `window_minutes` -
    consulta direta em `operations_login_current_status` (1 linha por login, sempre em dia), não no
    histórico completo. `status_changed_at` já é mantido pelo upsert (`upsert_login_current_status`)
    pra só avançar quando `online` muda de valor, então este filtro por si só já é "transicionou
    recentemente" - não precisa comparar contra uma captura antiga (ver docstring do model, e o
    motivo de essa tabela existir: a versão anterior desta função escaneava o histórico inteiro e
    levava ~11s com poucas horas de dados de teste)."""
    window_start = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    rows = db.execute(
        select(OperationLoginCurrentStatus).where(
            OperationLoginCurrentStatus.online == _DISCONNECTED_VALUE,
            OperationLoginCurrentStatus.status_changed_at >= window_start,
            OperationLoginCurrentStatus.latitude.is_not(None),
            OperationLoginCurrentStatus.longitude.is_not(None),
        )
    ).scalars().all()
    return [
        OfflineLoginPoint(
            login_id=row.login_id,
            login=row.login,
            online=row.online,
            latitude=row.latitude,
            longitude=row.longitude,
            last_disconnected_at=row.last_disconnected_at,
        )
        for row in rows
    ]


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * math.asin(math.sqrt(a))


def _grid_cell(lat: float, lon: float, cell_size_degrees: float) -> tuple[int, int]:
    return (math.floor(lat / cell_size_degrees), math.floor(lon / cell_size_degrees))


class _UnionFind:
    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, item: int) -> int:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: int, b: int) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a


def _direct_neighbors(points: list[OfflineLoginPoint], *, radius_meters: float) -> list[list[int]]:
    """Vizinhos DIRETOS de cada ponto (distância real <= `radius_meters`), calculados uma única vez
    por par (`neighbor_index > index`, espelhado pros dois lados) - usa um grid espacial (células de
    ~`radius_meters`) pra só comparar cada ponto contra os vizinhos das 9 células ao redor, em vez de
    todos os outros pontos."""
    if not points:
        return []

    # 1 grau de latitude ~= 111.320 m (constante, não varia com latitude); usamos essa aproximação
    # também pra longitude porque o erro (célula um pouco maior/menor que o raio real perto do
    # equador vs longe dele) só faz o grid ser levemente conservador, nunca perde vizinhos de
    # verdade - a distância real entre os pontos ainda é calculada com haversine depois.
    cell_size_degrees = max(radius_meters / 111_320.0, 1e-6)

    grid: dict[tuple[int, int], list[int]] = {}
    for index, point in enumerate(points):
        cell = _grid_cell(point.latitude, point.longitude, cell_size_degrees)
        grid.setdefault(cell, []).append(index)

    neighbors: list[list[int]] = [[] for _ in points]
    for index, point in enumerate(points):
        cell_lat, cell_lon = _grid_cell(point.latitude, point.longitude, cell_size_degrees)
        for d_lat in (-1, 0, 1):
            for d_lon in (-1, 0, 1):
                for neighbor_index in grid.get((cell_lat + d_lat, cell_lon + d_lon), ()):
                    if neighbor_index <= index:
                        continue
                    neighbor = points[neighbor_index]
                    if _haversine_meters(point.latitude, point.longitude, neighbor.latitude, neighbor.longitude) <= radius_meters:
                        neighbors[index].append(neighbor_index)
                        neighbors[neighbor_index].append(index)
    return neighbors


def _cluster_points(
    points: list[OfflineLoginPoint], *, radius_meters: float, min_samples: int
) -> list[list[OfflineLoginPoint]]:
    """DBSCAN: só forma cluster ao redor de um ponto "núcleo" - quem tem pelo menos `min_samples`
    vizinhos diretos (incluindo ele mesmo) dentro de `radius_meters`. Pontos de borda (perto de um
    núcleo, mas sem densidade própria) entram no cluster do núcleo; pontos isolados (sem nenhum
    núcleo por perto) ficam de fora como ruído.

    Achado real testando com dados de produção: sem essa exigência de densidade, encadeamento puro
    (união transitiva A-B-B-C-C-D...) juntava mais de mil logins numa área urbana densa num único
    "cluster", mesmo quando a maioria não tinha relação nenhuma entre si - só coincidência de estar
    perto na cadeia. Exigir vizinhos diretos suficientes evita esse efeito bola de neve e ainda
    detecta corretamente uma área realmente densa de quedas (aí sim os núcleos aparecem em cadeia
    de verdade, um do lado do outro)."""
    if not points:
        return []

    neighbors = _direct_neighbors(points, radius_meters=radius_meters)
    is_core = [len(neighbors[index]) + 1 >= min_samples for index in range(len(points))]

    union_find = _UnionFind(len(points))
    for index, neighbor_indexes in enumerate(neighbors):
        if not is_core[index]:
            continue
        for neighbor_index in neighbor_indexes:
            union_find.union(index, neighbor_index)

    groups: dict[int, list[tuple[OfflineLoginPoint, bool]]] = {}
    for index, point in enumerate(points):
        groups.setdefault(union_find.find(index), []).append((point, is_core[index]))

    return [
        [point for point, _ in group]
        for group in groups.values()
        if any(is_core_point for _, is_core_point in group)
    ]


def _geo_radius_condition(lat_column, lng_column, near_latitude: float, near_longitude: float, radius_km: float):
    """Mesma fórmula de Haversine de `operations.queries.geo_radius_condition`, parametrizada por
    coluna - duplicada aqui (em vez de importada) porque é curta e evita acoplar este módulo
    (import de `OperationLoginCurrentStatus`, não `OperationOrder`) a `operations.queries`."""
    ref_lat_rad = func.radians(near_latitude)
    ref_lng_rad = func.radians(near_longitude)
    lat_rad = func.radians(lat_column)
    lng_rad = func.radians(lng_column)
    cos_angle = (
        func.sin(lat_rad) * func.sin(ref_lat_rad) + func.cos(lat_rad) * func.cos(ref_lat_rad) * func.cos(lng_rad - ref_lng_rad)
    )
    clamped_cos_angle = case((cos_angle > 1.0, 1.0), (cos_angle < -1.0, -1.0), else_=cos_angle)
    distance_km = EARTH_RADIUS_METERS / 1000.0 * func.acos(clamped_cos_angle)
    return and_(lat_column.is_not(None), lng_column.is_not(None), distance_km <= radius_km)


# Limite defensivo pra consulta individual de status de login (item novo do inventário: as tabelas
# de status/geo de login só eram acessíveis via o agregado de cluster) - mesmo espírito de
# `MAX_ORDER_IDENTIFIERS_PER_REQUEST` em operations/queries.py.
MAX_LOGIN_STATUS_RESULTS = 500


def query_login_status(
    db: Session,
    *,
    logins: list[str] | None = None,
    online_statuses: list[str] | None = None,
    near_latitude: float | None = None,
    near_longitude: float | None = None,
    radius_km: float | None = None,
    limit: int = 200,
) -> list[OperationLoginCurrentStatus]:
    """Consulta individual de status de conectividade por login/regional geográfica - sem filtro
    nenhum, limita a `limit` (até `MAX_LOGIN_STATUS_RESULTS`) para nunca devolver a base inteira de
    logins de uma vez só."""
    conditions = []
    if logins:
        conditions.append(OperationLoginCurrentStatus.login.in_(logins))
    if online_statuses:
        conditions.append(OperationLoginCurrentStatus.online.in_(online_statuses))
    if near_latitude is not None and near_longitude is not None and radius_km is not None:
        conditions.append(
            _geo_radius_condition(
                OperationLoginCurrentStatus.latitude, OperationLoginCurrentStatus.longitude, near_latitude, near_longitude, radius_km
            )
        )
    stmt = (
        select(OperationLoginCurrentStatus)
        .where(*conditions)
        .order_by(OperationLoginCurrentStatus.status_changed_at.desc())
        .limit(min(limit, MAX_LOGIN_STATUS_RESULTS))
    )
    return list(db.scalars(stmt))


def find_offline_login_clusters(
    db: Session,
    *,
    radius_meters: float = 300.0,
    min_cluster_size: int = 3,
    window_minutes: int = 30,
) -> list[OfflineLoginCluster]:
    """Detecta clusters geográficos de logins que caíram (transicionaram pra 'N') nos últimos
    `window_minutes` - candidatos a rompimento de fibra num trecho (vários vizinhos caindo juntos
    ao mesmo tempo), não uma queda isolada de um único cliente nem um equipamento cronicamente sem
    sinal (ver `_DISCONNECTED_VALUE`, motivo de não usar o status estático). `min_cluster_size`
    também é usado como limiar de densidade do DBSCAN (mínimo de vizinhos diretos pra um ponto
    "puxar" um cluster). Retorna só os grupos com `min_cluster_size` ou mais logins, ordenados do
    maior pro menor."""
    points = _fetch_recent_disconnections(db, window_minutes=window_minutes)
    groups = _cluster_points(points, radius_meters=radius_meters, min_samples=min_cluster_size)

    clusters = [
        OfflineLoginCluster(
            center_latitude=sum(p.latitude for p in group) / len(group),
            center_longitude=sum(p.longitude for p in group) / len(group),
            radius_meters=radius_meters,
            logins=group,
        )
        for group in groups
        if len(group) >= min_cluster_size
    ]
    clusters.sort(key=lambda cluster: cluster.size, reverse=True)
    return clusters
