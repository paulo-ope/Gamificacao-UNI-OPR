from datetime import date, datetime, timezone

import pytest

from app.models import User
from app.modules.ai import queries as ai_queries
from app.modules.operations.models import OperationOrder

DATE_FROM = date(2026, 7, 1)
DATE_TO = date(2026, 7, 31)

# Coordenadas reais de Rondônia (mesma amostra usada pra confirmar bairro/lat/long no banco).
JI_PARANA_LAT, JI_PARANA_LNG = -10.8835274, -61.9072124
# ~44m ao norte do ponto acima - deve cair dentro de um raio pequeno e no mesmo geo_cluster.
JI_PARANA_NEARBY_LAT = -10.8831274
# Rolim de Moura - outra cidade, ~190km de distância - deve ficar de fora de um raio pequeno.
ROLIM_DE_MOURA_LAT, ROLIM_DE_MOURA_LNG = -9.2306221, -61.9940897


@pytest.fixture()
def ai_user(db_session):
    user = User(name="IA", email="ia-geo@pytest.local", role="admin", active=True, password_hash="x")
    db_session.add(user)
    db_session.flush()
    return user


def _make_order(db_session, *, order_code, opened_at, latitude=None, longitude=None, **overrides):
    defaults = dict(
        source_order_id=order_code,
        order_code=order_code,
        os_type="Manutenção",
        os_subject="Suporte Externo",
        opened_at=opened_at,
        closed_at=opened_at,
        is_closed=True,
        latitude=latitude,
        longitude=longitude,
    )
    defaults.update(overrides)
    order = OperationOrder(**defaults)
    db_session.add(order)
    return order


def test_haversine_km_matches_known_distance():
    # 1 grau de latitude equivale a ~111.2km - referência simples pra validar a fórmula.
    distance = ai_queries._haversine_km(0.0, 0.0, 1.0, 0.0)
    assert distance == pytest.approx(111.19, abs=0.5)

    # Mesmo ponto - distância zero (achado real: sem o clamp em _haversine_km_expr, o cosseno
    # calculado pode passar levemente de 1.0 e travar acos() com erro de domínio).
    assert ai_queries._haversine_km(JI_PARANA_LAT, JI_PARANA_LNG, JI_PARANA_LAT, JI_PARANA_LNG) == pytest.approx(0.0, abs=1e-6)


def test_search_orders_filters_by_radius_around_a_point(db_session, ai_user):
    opened_at = datetime(2026, 7, 15, tzinfo=timezone.utc)
    _make_order(db_session, order_code="NEAR", opened_at=opened_at, latitude=JI_PARANA_NEARBY_LAT, longitude=JI_PARANA_LNG)
    _make_order(db_session, order_code="FAR", opened_at=opened_at, latitude=ROLIM_DE_MOURA_LAT, longitude=ROLIM_DE_MOURA_LNG)
    _make_order(db_session, order_code="NO-COORDS", opened_at=opened_at, latitude=None, longitude=None)
    db_session.flush()

    result = ai_queries.search_orders(
        db_session, ai_user, date_from=DATE_FROM, date_to=DATE_TO,
        near_latitude=JI_PARANA_LAT, near_longitude=JI_PARANA_LNG, radius_km=1.0,
    )

    assert [item["order_code"] for item in result["items"]] == ["NEAR"]
    assert result["items"][0]["distance_km"] < 1.0


def test_search_orders_sorts_by_distance_when_reference_point_is_given(db_session, ai_user):
    opened_at = datetime(2026, 7, 15, tzinfo=timezone.utc)
    _make_order(db_session, order_code="FARTHER", opened_at=opened_at, latitude=JI_PARANA_NEARBY_LAT - 0.001, longitude=JI_PARANA_LNG)
    _make_order(db_session, order_code="CLOSEST", opened_at=opened_at, latitude=JI_PARANA_LAT, longitude=JI_PARANA_LNG)
    _make_order(db_session, order_code="MIDDLE", opened_at=opened_at, latitude=JI_PARANA_NEARBY_LAT, longitude=JI_PARANA_LNG)
    db_session.flush()

    result = ai_queries.search_orders(
        db_session, ai_user, date_from=DATE_FROM, date_to=DATE_TO,
        near_latitude=JI_PARANA_LAT, near_longitude=JI_PARANA_LNG, radius_km=5.0,
    )

    assert [item["order_code"] for item in result["items"]] == ["CLOSEST", "MIDDLE", "FARTHER"]
    distances = [item["distance_km"] for item in result["items"]]
    assert distances == sorted(distances)


def test_search_orders_filters_by_has_coordinates(db_session, ai_user):
    opened_at = datetime(2026, 7, 15, tzinfo=timezone.utc)
    _make_order(db_session, order_code="WITH-COORDS", opened_at=opened_at, latitude=JI_PARANA_LAT, longitude=JI_PARANA_LNG)
    _make_order(db_session, order_code="WITHOUT-COORDS", opened_at=opened_at, latitude=None, longitude=None)
    db_session.flush()

    with_coords = ai_queries.search_orders(db_session, ai_user, date_from=DATE_FROM, date_to=DATE_TO, has_coordinates=True)
    assert [item["order_code"] for item in with_coords["items"]] == ["WITH-COORDS"]

    without_coords = ai_queries.search_orders(db_session, ai_user, date_from=DATE_FROM, date_to=DATE_TO, has_coordinates=False)
    assert [item["order_code"] for item in without_coords["items"]] == ["WITHOUT-COORDS"]


def test_aggregate_orders_groups_by_geo_cluster(db_session, ai_user):
    """Item pedido: "agrupamento por proximidade geográfica"/"contagem de O.S. por coordenada" -
    duas O.S. a ~22m uma da outra (dentro da célula de ~111m de geo_cluster, e longe o bastante de
    uma borda de arredondamento em x.xxx5 pra não cair em células vizinhas por acaso - limitação
    conhecida de clustering por grade, ver _group_label) devem cair no mesmo grupo; uma O.S. em
    outra cidade cai num grupo diferente; sem coordenadas vira "Sem coordenadas"."""
    cluster_lat, cluster_lng = -10.8810000, -61.9072124
    opened_at = datetime(2026, 7, 15, tzinfo=timezone.utc)
    _make_order(db_session, order_code="CLUSTER-A-1", opened_at=opened_at, latitude=cluster_lat, longitude=cluster_lng)
    _make_order(db_session, order_code="CLUSTER-A-2", opened_at=opened_at, latitude=cluster_lat - 0.0002, longitude=cluster_lng)
    _make_order(db_session, order_code="CLUSTER-B", opened_at=opened_at, latitude=ROLIM_DE_MOURA_LAT, longitude=ROLIM_DE_MOURA_LNG)
    _make_order(db_session, order_code="NO-COORDS", opened_at=opened_at, latitude=None, longitude=None)
    db_session.flush()

    result = ai_queries.aggregate_orders(
        db_session, ai_user, group_by="geo_cluster", metric="quantidade_fechada", date_from=DATE_FROM, date_to=DATE_TO,
    )
    by_label = {item["label"]: item["quantity"] for item in result}

    assert by_label.get("Sem coordenadas") == 1
    non_missing = {label: qty for label, qty in by_label.items() if label != "Sem coordenadas"}
    assert sorted(non_missing.values()) == [1, 2]


def test_ai_fields_marks_latitude_and_longitude_as_exposed():
    result = ai_queries.available_fields()
    assert "latitude" in result["exposed_to_ai"]
    assert "longitude" in result["exposed_to_ai"]
