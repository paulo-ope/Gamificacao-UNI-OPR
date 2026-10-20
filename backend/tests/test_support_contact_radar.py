from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.modules.support import contact_geo_sync, contact_radar_service
from app.modules.support.models import SupportContactGeo, SupportOpaAttendance, SupportOpaDimension

NOW = datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)
CIDADES = {10: {"id": "10", "nome": "Ji-Parana"}, 20: {"id": "20", "nome": "Jaru"}}


# ---------------------------------------------------------------------------
# resolve_location (regra pura)
# ---------------------------------------------------------------------------
def test_resolve_location_uses_cliente_then_contract_and_normalizes():
    cliente = {"cidade": "10", "bairro": "  centro  "}
    contract = {"id_filial": "6", "cidade": "20", "bairro": "Outro"}
    location = contact_geo_sync.resolve_location(cliente, contract, CIDADES, {"latitude": "-10.88", "longitude": "-61.95"})
    assert location["city"] == "Ji-Parana"
    assert location["neighborhood"] == "Centro"
    assert location["regional"] == "UNI - JI PARANA"
    assert (location["latitude"], location["longitude"]) == (-10.88, -61.95)


def test_resolve_location_falls_back_to_contract_when_cliente_has_no_city_or_neighborhood():
    location = contact_geo_sync.resolve_location(
        {"cidade": "", "bairro": ""}, {"id_filial": "9", "cidade": "20", "bairro": "setor 3"}, CIDADES, {}
    )
    assert (location["city"], location["neighborhood"], location["regional"]) == ("Jaru", "Setor 3", "UNI - JARU")


def test_resolve_location_ignores_invalid_branch_and_uses_opa_branch():
    # Filial "5" é "geral de cadastro" (inválida); a filial do OPA vale como segunda opção.
    location = contact_geo_sync.resolve_location(
        {"cidade": "10", "bairro": "X"}, {"id_filial": "5"}, CIDADES, {"id_filial": "8"}
    )
    assert location["regional"] == "UNI - ROLIM DE MOURA"
    none = contact_geo_sync.resolve_location({"cidade": "10", "bairro": "X"}, {"id_filial": "5"}, CIDADES, {"id_filial": "5"})
    assert none["regional"] is None


def test_resolve_location_drops_coordinates_outside_brazil_or_zeroed():
    assert contact_geo_sync._coordinates({"latitude": "0", "longitude": "0"}) == (None, None)
    assert contact_geo_sync._coordinates({"latitude": "40.7", "longitude": "-74.0"}) == (None, None)
    assert contact_geo_sync._coordinates({"latitude": "-10,5", "longitude": "-62,1"}) == (-10.5, -62.1)
    assert contact_geo_sync._coordinates({"latitude": "-10.5"}) == (None, None)


# ---------------------------------------------------------------------------
# sync_contact_geo
# ---------------------------------------------------------------------------
def _customer(db, opa_id, ixc_id, **payload):
    db.add(
        SupportOpaDimension(
            dimension_type="customer",
            source_id=opa_id,
            name=f"Cliente {opa_id}",
            payload_json={"_id": opa_id, **({"id": ixc_id} if ixc_id is not None else {}), **payload},
        )
    )


def _attendance(db, source_id, customer_id, *, minutes_ago=5, days_ago=0, channel="whatsapp", now=NOW, department_id=None):
    db.add(
        SupportOpaAttendance(
            source_id=source_id,
            customer_id=customer_id,
            channel=channel,
            department_id=department_id,
            status="F",
            opened_at=now - timedelta(days=days_ago, minutes=minutes_ago),
        )
    )


class _FakeIxc:
    pass


def test_sync_resolves_customers_once_and_marks_missing_ones(db_session, monkeypatch):
    monkeypatch.setattr(contact_geo_sync, "_cidades_cache", None)
    _customer(db_session, "opa-a", 101, id_filial="6", latitude="-10.9", longitude="-61.9")
    _customer(db_session, "opa-b", 999)  # não existe no IXC
    _customer(db_session, "opa-c", None)  # prospect: sem id do IXC
    for index, customer in enumerate(("opa-a", "opa-b", "opa-c")):
        _attendance(db_session, f"s{index}", customer, minutes_ago=index + 1)
    db_session.commit()

    calls = {"clientes": 0}

    def fake_clientes(client, ids, **_):
        calls["clientes"] += 1
        return iter([{"id": "101", "cidade": "10", "bairro": "centro"}] if 101 in ids else [])

    monkeypatch.setattr(contact_geo_sync, "fetch_cidades", lambda client: iter(CIDADES.values()))
    monkeypatch.setattr(contact_geo_sync, "fetch_clientes_by_ids", fake_clientes)
    monkeypatch.setattr(contact_geo_sync, "fetch_customer_contracts_by_customer_ids", lambda client, ids, **_: iter([]))

    result = contact_geo_sync.sync_contact_geo(db_session, _FakeIxc(), now=NOW)
    db_session.commit()
    assert result == {"pending": 3, "resolved": 1, "not_found": 1, "no_ixc_id": 1}
    rows = {r.opa_customer_id: r for r in db_session.scalars(select(SupportContactGeo))}
    assert (rows["opa-a"].city, rows["opa-a"].neighborhood, rows["opa-a"].regional) == ("Ji-Parana", "Centro", "UNI - JI PARANA")
    assert rows["opa-a"].ixc_customer_id == "101"
    assert rows["opa-b"].status == "not_found"
    assert rows["opa-c"].status == "not_found" and rows["opa-c"].ixc_customer_id is None

    # Segunda rodada: ninguém pendente, nenhuma chamada nova ao IXC.
    again = contact_geo_sync.sync_contact_geo(db_session, _FakeIxc(), now=NOW)
    assert again["pending"] == 0
    assert calls["clientes"] == 1


def test_sync_retries_not_found_only_after_a_week(db_session, monkeypatch):
    _customer(db_session, "opa-b", 999)
    _attendance(db_session, "s1", "opa-b")
    db_session.add(SupportContactGeo(opa_customer_id="opa-b", ixc_customer_id="999", status="not_found", resolved_at=NOW - timedelta(days=2)))
    db_session.commit()
    assert contact_geo_sync._pending_customers(db_session, NOW, 10) == []
    assert [c for c, _ in contact_geo_sync._pending_customers(db_session, NOW + timedelta(days=6), 10)] == ["opa-b"]


def test_sync_ignores_customers_without_recent_attendance(db_session):
    _customer(db_session, "opa-old", 1)
    _attendance(db_session, "old", "opa-old", days_ago=contact_geo_sync.LOOKBACK_DAYS + 3)
    db_session.commit()
    assert contact_geo_sync._pending_customers(db_session, NOW, 10) == []


# ---------------------------------------------------------------------------
# build_radar
# ---------------------------------------------------------------------------
def _cities(radar):
    return [city for regional in radar["regionals"] for city in regional["cities"]]


def _hoods(radar):
    return [hood for city in _cities(radar) for hood in city["neighborhoods"]]


def _geo(db, opa_id, city, neighborhood, regional="UNI - JI PARANA", status="ok", lat=None, lon=None):
    db.add(
        SupportContactGeo(
            opa_customer_id=opa_id, ixc_customer_id=opa_id, status=status, regional=regional, city=city,
            neighborhood=neighborhood, latitude=lat, longitude=lon, resolved_at=NOW,
        )
    )


def test_radar_counts_distinct_customers_and_reports_unlocated(db_session):
    _geo(db_session, "c1", "Ji-Parana", "Centro", lat=-10.0, lon=-61.0)
    _geo(db_session, "c2", "Ji-Parana", "Centro", lat=-10.2, lon=-61.2)
    _geo(db_session, "c3", "Jaru", "Setor 1")
    _attendance(db_session, "a1", "c1")
    _attendance(db_session, "a2", "c1", minutes_ago=6)  # mesmo cliente insistindo
    _attendance(db_session, "a3", "c2", channel="pabx")
    _attendance(db_session, "a4", "c3")
    _attendance(db_session, "a5", None)  # sem cliente identificado
    _attendance(db_session, "a6", "c1", minutes_ago=90)  # fora da janela de 60 min
    db_session.commit()

    radar = contact_radar_service.build_radar(
        db_session, window_minutes=60, channel=None, allowed_regionals=[], deny_all=False, now=NOW
    )
    assert radar["totals"] == {
        "contacts": 5, "customers": 3, "located_contacts": 4, "unlocated_contacts": 1, "coverage_pct": 80.0,
    }
    centro = next(n for n in _hoods(radar) if n["neighborhood"] == "Centro")
    assert (centro["contacts"], centro["customers"]) == (3, 2)
    assert round(centro["latitude"], 3) == -10.1 and round(centro["longitude"], 3) == -61.1
    assert [c["city"] for c in _cities(radar)] == ["Ji-Parana", "Jaru"]
    assert {c["channel"]: c["contacts"] for c in radar["by_channel"]} == {"whatsapp": 4, "pabx": 1}
    first = radar["regionals"][0]
    assert (first["regional"], first["contacts"], first["customers"]) == ("UNI - JI PARANA", 4, 3)
    assert [c["city"] for c in first["cities"]] == ["Ji-Parana", "Jaru"]


def test_radar_flags_volume_above_the_usual_and_not_the_usual_one(db_session):
    # Hoje: 6 clientes de Jaru + 6 de Ji-Parana na janela. Nos 7 dias anteriores Ji-Parana tinha 6
    # por dia (normal) e Jaru 1 por dia (volume de hoje é anormal).
    for n in range(6):
        _geo(db_session, f"j{n}", "Jaru", "Centro")
        _geo(db_session, f"p{n}", "Ji-Parana", "Centro")
        _attendance(db_session, f"hj{n}", f"j{n}", minutes_ago=3 + n)
        _attendance(db_session, f"hp{n}", f"p{n}", minutes_ago=3 + n)
    for day in range(1, 8):
        _attendance(db_session, f"bj{day}", "j0", days_ago=day, minutes_ago=10)
        for n in range(6):
            _attendance(db_session, f"bp{day}-{n}", f"p{n}", days_ago=day, minutes_ago=3 + n)
    db_session.commit()

    radar = contact_radar_service.build_radar(
        db_session, window_minutes=60, channel=None, allowed_regionals=[], deny_all=False, now=NOW
    )
    by_city = {c["city"]: c for c in _cities(radar)}
    assert by_city["Jaru"]["elevated"] is True and by_city["Jaru"]["baseline"] == 1.0
    assert by_city["Ji-Parana"]["elevated"] is False and by_city["Ji-Parana"]["baseline"] == 6.0
    assert _cities(radar)[0]["city"] == "Jaru"  # elevado vem primeiro


def test_radar_small_volume_is_never_flagged(db_session):
    _geo(db_session, "c1", "Jaru", "Centro")
    _attendance(db_session, "a1", "c1")
    db_session.commit()
    radar = contact_radar_service.build_radar(
        db_session, window_minutes=15, channel=None, allowed_regionals=[], deny_all=False, now=NOW
    )
    assert _cities(radar)[0]["elevated"] is False


def test_radar_respects_regional_scope_and_hides_global_volume(db_session):
    _geo(db_session, "c1", "Jaru", "Centro", regional="UNI - JARU")
    _geo(db_session, "c2", "Ji-Parana", "Centro", regional="UNI - JI PARANA")
    _attendance(db_session, "a1", "c1")
    _attendance(db_session, "a2", "c2")
    _attendance(db_session, "a3", None)
    db_session.commit()

    scoped = contact_radar_service.build_radar(
        db_session, window_minutes=60, channel=None, allowed_regionals=["UNI - JARU"], deny_all=False, now=NOW
    )
    assert [c["city"] for c in _cities(scoped)] == ["Jaru"]
    assert scoped["totals"]["contacts"] == 1
    assert scoped["totals"]["unlocated_contacts"] == 0 and scoped["totals"]["coverage_pct"] is None

    denied = contact_radar_service.build_radar(
        db_session, window_minutes=60, channel=None, allowed_regionals=[], deny_all=True, now=NOW
    )
    assert denied["totals"]["contacts"] == 0 and denied["regionals"] == []


def test_radar_channel_filter(db_session):
    _geo(db_session, "c1", "Jaru", "Centro")
    _attendance(db_session, "a1", "c1", channel="pabx")
    _attendance(db_session, "a2", "c1", channel="whatsapp", minutes_ago=7)
    db_session.commit()
    radar = contact_radar_service.build_radar(
        db_session, window_minutes=60, channel="pabx", allowed_regionals=[], deny_all=False, now=NOW
    )
    assert radar["totals"]["contacts"] == 1


def test_radar_does_not_flag_while_history_is_mostly_unlocated(db_session):
    # Hoje: 6 clientes localizados de Jaru. Nos 7 dias anteriores quase ninguém estava localizado
    # (carga inicial): sem a trava tudo pareceria "acima do usual".
    for n in range(6):
        _geo(db_session, f"j{n}", "Jaru", "Centro")
        _attendance(db_session, f"h{n}", f"j{n}", minutes_ago=3 + n)
    for day in range(1, 8):
        for n in range(10):
            _attendance(db_session, f"x{day}-{n}", f"nao-resolvido-{n}", days_ago=day, minutes_ago=5)
    db_session.commit()
    radar = contact_radar_service.build_radar(
        db_session, window_minutes=60, channel=None, allowed_regionals=[], deny_all=False, now=NOW
    )
    assert radar["alerts_enabled"] is False
    assert not any(n["elevated"] for n in radar["regionals"] + _cities(radar) + _hoods(radar))


def test_radar_by_date_range_uses_porto_velho_days_and_compares_with_previous_period(db_session):
    # 20/10 em Porto Velho (UTC-4) vai de 04:00Z do dia 20 até 04:00Z do dia 21.
    for n in range(6):
        _geo(db_session, f"c{n}", "Jaru", "Centro")
    # Dia 20: 6 clientes (um deles às 23h30 local = 03:30Z do dia 21, ainda dentro do dia 20).
    for n in range(5):
        _attendance(db_session, f"d{n}", f"c{n}", now=datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc), minutes_ago=n)
    _attendance(db_session, "late", "c5", now=datetime(2026, 10, 21, 3, 30, tzinfo=timezone.utc), minutes_ago=0)
    # 00:30 local do dia 21 (04:30Z) já é outro dia: não conta.
    _attendance(db_session, "next", "c0", now=datetime(2026, 10, 21, 4, 30, tzinfo=timezone.utc), minutes_ago=0)
    # Dia anterior (19): 2 clientes.
    for n in range(2):
        _attendance(db_session, f"p{n}", f"c{n}", now=datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc), minutes_ago=n)
    db_session.commit()

    radar = contact_radar_service.build_radar(
        db_session, date_from=date(2026, 10, 20), date_to=date(2026, 10, 20),
        allowed_regionals=[], deny_all=False, now=NOW,
    )
    assert radar["mode"] == "range" and radar["window_minutes"] is None
    assert radar["totals"]["contacts"] == 6 and radar["totals"]["customers"] == 6
    jaru = _cities(radar)[0]
    assert (jaru["customers"], jaru["baseline"], jaru["ratio"], jaru["elevated"]) == (6, 2.0, 3.0, True)


def test_radar_department_filter(db_session):
    _geo(db_session, "c1", "Jaru", "Centro")
    _geo(db_session, "c2", "Jaru", "Centro")
    _attendance(db_session, "a1", "c1", department_id="10")
    _attendance(db_session, "a2", "c2", department_id="20")
    db_session.commit()
    radar = contact_radar_service.build_radar(
        db_session, window_minutes=60, department_id="10", allowed_regionals=[], deny_all=False, now=NOW
    )
    assert radar["totals"]["contacts"] == 1 and _cities(radar)[0]["customers"] == 1


def test_radar_accepts_several_departments(db_session):
    for n in range(3):
        _geo(db_session, f"c{n}", "Jaru", "Centro")
        _attendance(db_session, f"a{n}", f"c{n}", department_id=str(10 * (n + 1)))
    db_session.commit()
    radar = contact_radar_service.build_radar(
        db_session, window_minutes=60, department_id="10,20", allowed_regionals=[], deny_all=False, now=NOW
    )
    assert radar["totals"]["contacts"] == 2
    todos = contact_radar_service.build_radar(
        db_session, window_minutes=60, department_id=None, allowed_regionals=[], deny_all=False, now=NOW
    )
    assert todos["totals"]["contacts"] == 3


def test_radar_nests_regional_city_neighborhood_with_own_counts_and_baseline(db_session):
    for n in range(6):
        _geo(db_session, f"a{n}", "Jaru", "Centro", regional="UNI - JARU")
        _attendance(db_session, f"ta{n}", f"a{n}", minutes_ago=2 + n)
    _geo(db_session, "b0", "Jaru", "Setor 1", regional="UNI - OURO PRETO DOESTE")  # contrato em outra filial
    _geo(db_session, "b1", "Ouro Preto do Oeste", "Centro", regional="UNI - OURO PRETO DOESTE")
    _attendance(db_session, "tb0", "b0")
    _attendance(db_session, "tb1", "b1")
    _attendance(db_session, "tb2", "b1", minutes_ago=9)  # mesmo cliente insistindo
    # Histórico: Jaru normal (6 por dia), para o alerta valer.
    for day in range(1, 8):
        for n in range(6):
            _attendance(db_session, f"h{day}-{n}", f"a{n}", days_ago=day, minutes_ago=2 + n)
    db_session.commit()

    radar = contact_radar_service.build_radar(
        db_session, window_minutes=60, channel=None, allowed_regionals=[], deny_all=False, now=NOW
    )
    jaru_reg, opo_reg = radar["regionals"]
    # O cliente de Jaru com contrato em outra filial entra em Jaru (a regional é a da cidade).
    assert (jaru_reg["regional"], jaru_reg["customers"], jaru_reg["contacts"]) == ("UNI - JARU", 7, 7)
    assert (opo_reg["regional"], opo_reg["customers"], opo_reg["contacts"]) == ("UNI - OURO PRETO DOESTE", 1, 2)
    assert [(c["city"], c["customers"]) for c in jaru_reg["cities"]] == [("Jaru", 7)]
    assert [(c["city"], c["contacts"], c["customers"]) for c in opo_reg["cities"]] == [("Ouro Preto do Oeste", 2, 1)]  # 2 contatos, 1 cliente
    assert sorted((h["neighborhood"], h["customers"]) for h in jaru_reg["cities"][0]["neighborhoods"]) == [("Centro", 6), ("Setor 1", 1)]
    # Comparação em cada nível: habitual 6/dia, hoje 7 = ainda normal.
    assert jaru_reg["baseline"] == 6.0 and jaru_reg["elevated"] is False
    assert jaru_reg["cities"][0]["baseline"] == 6.0


def test_city_regionals_picks_the_regional_with_most_customers_and_ties_alphabetically(db_session):
    for n in range(5):
        _geo(db_session, f"m{n}", "Presidente Médici", "Centro", regional="UNI - PRESIDENTE MEDICI")
    _geo(db_session, "m9", "Presidente Médici", "Centro", regional="UNI - JI PARANA")
    _geo(db_session, "t1", "Cidade Empatada", "Centro", regional="UNI - JARU")
    _geo(db_session, "t2", "Cidade Empatada", "Centro", regional="UNI - ALVORADA DOESTE")
    _geo(db_session, "n1", "Sem Regional", "Centro", regional=None)
    _geo(db_session, "nf", "Nao Achado", "Centro", regional="UNI - JARU", status="not_found")
    db_session.commit()
    result = contact_radar_service.city_regionals(db_session)
    assert result["Presidente Médici"] == "UNI - PRESIDENTE MEDICI"
    assert result["Cidade Empatada"] == "UNI - ALVORADA DOESTE"
    assert "Sem Regional" not in result and "Nao Achado" not in result


def test_radar_puts_a_customer_under_the_regional_of_their_city_not_of_their_contract(db_session):
    for n in range(5):
        _geo(db_session, f"m{n}", "Presidente Médici", "Centro", regional="UNI - PRESIDENTE MEDICI")
        _attendance(db_session, f"am{n}", f"m{n}", minutes_ago=2 + n)
    # Mora em Presidente Médici, mas o contrato foi cadastrado na filial de Ji-Paraná.
    _geo(db_session, "x", "Presidente Médici", "Centro", regional="UNI - JI PARANA")
    _attendance(db_session, "ax", "x")
    for n in range(3):
        _geo(db_session, f"j{n}", "Ji-Parana", "Centro", regional="UNI - JI PARANA")
        _attendance(db_session, f"aj{n}", f"j{n}", minutes_ago=2 + n)
    db_session.commit()

    radar = contact_radar_service.build_radar(
        db_session, window_minutes=60, channel=None, allowed_regionals=[], deny_all=False, now=NOW
    )
    by_regional = {r["regional"]: r for r in radar["regionals"]}
    assert set(by_regional) == {"UNI - PRESIDENTE MEDICI", "UNI - JI PARANA"}
    assert by_regional["UNI - PRESIDENTE MEDICI"]["customers"] == 6
    assert [c["city"] for c in by_regional["UNI - JI PARANA"]["cities"]] == ["Ji-Parana"]
    assert by_regional["UNI - JI PARANA"]["customers"] == 3

    # Gestor de Ji-Paraná não vê o cliente de Presidente Médici que só tem contrato lá; o de Médici vê.
    ji = contact_radar_service.build_radar(
        db_session, window_minutes=60, channel=None, allowed_regionals=["UNI - JI PARANA"], deny_all=False, now=NOW
    )
    assert [c["city"] for c in _cities(ji)] == ["Ji-Parana"]
    assert ji["totals"]["contacts"] == 3
    medici = contact_radar_service.build_radar(
        db_session, window_minutes=60, channel=None, allowed_regionals=["UNI - PRESIDENTE MEDICI"], deny_all=False, now=NOW
    )
    assert medici["totals"]["customers"] == 6


def test_radar_series_is_zero_filled_and_adds_up_to_the_totals(db_session):
    _geo(db_session, "c1", "Jaru", "Centro")
    _geo(db_session, "c2", "Jaru", "Centro")
    _attendance(db_session, "a1", "c1", minutes_ago=2)
    _attendance(db_session, "a2", "c1", minutes_ago=3, channel="pabx")
    _attendance(db_session, "a3", "c2", minutes_ago=31)
    _attendance(db_session, "a4", None, minutes_ago=31)  # sem cliente identificado
    db_session.commit()
    radar = contact_radar_service.build_radar(
        db_session, window_minutes=60, allowed_regionals=[], deny_all=False, now=NOW
    )
    series = radar["series"]
    points = series["points"]
    assert series["bucket_minutes"] == 5 and len(points) == 13
    assert all(point["start"].minute % 5 == 0 for point in points)
    assert sum(p["contacts"] for p in points) == radar["totals"]["contacts"] == 4
    assert sum(p["located_contacts"] for p in points) == radar["totals"]["located_contacts"] == 3
    assert sum(1 for p in points if p["contacts"] == 0) == 11  # intervalos vazios entram com zero
    last = next(p for p in points if p["by_channel"].get("pabx"))
    assert last["by_channel"] == {"pabx": 1, "whatsapp": 1} and last["customers"] == 1


def test_radar_series_bucket_size_and_range_alignment(db_session):
    assert contact_radar_service.bucket_minutes(by_range=False, window_minutes=15, range_days=0) == 5
    assert contact_radar_service.bucket_minutes(by_range=False, window_minutes=180, range_days=0) == 15
    assert contact_radar_service.bucket_minutes(by_range=False, window_minutes=1440, range_days=0) == 60
    assert contact_radar_service.bucket_minutes(by_range=True, window_minutes=60, range_days=2) == 60
    assert contact_radar_service.bucket_minutes(by_range=True, window_minutes=60, range_days=7) == 1440
    one_day = contact_radar_service.build_radar(
        db_session, date_from=date(2026, 10, 20), date_to=date(2026, 10, 20), allowed_regionals=[], deny_all=False, now=NOW
    )
    assert len(one_day["series"]["points"]) == 24
    # O primeiro ponto é a meia-noite de Porto Velho (04:00Z).
    assert one_day["series"]["points"][0]["start"] == datetime(2026, 10, 20, 4, 0, tzinfo=timezone.utc)
    week = contact_radar_service.build_radar(
        db_session, date_from=date(2026, 10, 14), date_to=date(2026, 10, 20), allowed_regionals=[], deny_all=False, now=NOW
    )
    assert len(week["series"]["points"]) == 7 and week["series"]["bucket_minutes"] == 1440


def test_radar_reports_previous_totals_for_the_card_variation(db_session):
    for n in range(4):
        _geo(db_session, f"c{n}", "Jaru", "Centro")
    for n in range(4):
        _attendance(db_session, f"h{n}", f"c{n}", now=datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc), minutes_ago=n)
    for n in range(2):  # dia anterior: 2 clientes, 3 contatos
        _attendance(db_session, f"p{n}", f"c{n}", now=datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc), minutes_ago=n)
    _attendance(db_session, "p9", "c0", now=datetime(2026, 10, 19, 16, 0, tzinfo=timezone.utc))
    db_session.commit()
    radar = contact_radar_service.build_radar(
        db_session, date_from=date(2026, 10, 20), date_to=date(2026, 10, 20), allowed_regionals=[], deny_all=False, now=NOW
    )
    assert radar["previous"] == {"contacts": 3.0, "customers": 2.0, "coverage_pct": 100.0}


def test_radar_series_respects_regional_scope(db_session):
    _geo(db_session, "c1", "Jaru", "Centro", regional="UNI - JARU")
    _geo(db_session, "c2", "Ji-Parana", "Centro", regional="UNI - JI PARANA")
    _attendance(db_session, "a1", "c1")
    _attendance(db_session, "a2", "c2")
    _attendance(db_session, "a3", None)
    db_session.commit()
    radar = contact_radar_service.build_radar(
        db_session, window_minutes=60, allowed_regionals=["UNI - JARU"], deny_all=False, now=NOW
    )
    assert sum(p["contacts"] for p in radar["series"]["points"]) == 1


def test_radar_alerts_off_when_history_coverage_is_well_below_the_current_one(db_session):
    # Hoje: 6 clientes localizados (cobertura 100%). Histórico: 3 de 4 contatos localizados por dia (75%),
    # acima do mínimo absoluto de 70% mas bem abaixo do atual - a variação ficaria inflada.
    for n in range(6):
        _geo(db_session, f"j{n}", "Jaru", "Centro")
        _attendance(db_session, f"h{n}", f"j{n}", minutes_ago=3 + n)
    for day in range(1, 8):
        for n in range(3):
            _attendance(db_session, f"b{day}-{n}", f"j{n}", days_ago=day, minutes_ago=5 + n)
        _attendance(db_session, f"u{day}", f"nao-resolvido-{day}", days_ago=day, minutes_ago=9)
    db_session.commit()
    radar = contact_radar_service.build_radar(
        db_session, window_minutes=60, allowed_regionals=[], deny_all=False, now=NOW
    )
    assert radar["alerts_enabled"] is False
    assert not any(n["elevated"] for n in radar["regionals"] + _cities(radar) + _hoods(radar))


def test_radar_groups_sao_francisco_branches_and_sao_felipe_into_rolim(db_session):
    _geo(db_session, "m1", "São Miguel do Guaporé", "Centro", regional="UNI - SAO MIGUEL DO GUAPORE")
    _geo(db_session, "s1", "Seringueiras", "Centro", regional="UNI - SERINGUEIRAS")
    _geo(db_session, "f1", "São Francisco do Guaporé", "Centro", regional="UNI - SAO FRANCISCO DO GUAPORE")
    _geo(db_session, "r1", "Rolim de Moura", "Centro", regional="UNI - ROLIM DE MOURA")
    _geo(db_session, "p1", "Primavera de Rondônia", "Centro", regional="UNI - SAO FELIPE DOESTE")
    _geo(db_session, "d1", "São Felipe D'Oeste", "Centro", regional="UNI - SAO FELIPE DOESTE")
    for customer in ("m1", "s1", "f1", "r1", "p1", "d1"):
        _attendance(db_session, f"a-{customer}", customer)
    db_session.commit()

    radar = contact_radar_service.build_radar(
        db_session, window_minutes=60, allowed_regionals=[], deny_all=False, now=NOW
    )
    by_regional = {r["regional"]: r for r in radar["regionals"]}
    assert set(by_regional) == {"UNI - SAO FRANCISCO DO GUAPORE", "UNI - ROLIM DE MOURA"}
    sao_francisco = by_regional["UNI - SAO FRANCISCO DO GUAPORE"]
    assert sao_francisco["customers"] == 3
    assert sorted(c["city"] for c in sao_francisco["cities"]) == ["Seringueiras", "São Francisco do Guaporé", "São Miguel do Guaporé"]
    rolim = by_regional["UNI - ROLIM DE MOURA"]
    assert rolim["customers"] == 3
    assert sorted(c["city"] for c in rolim["cities"]) == ["Primavera de Rondônia", "Rolim de Moura", "São Felipe D'Oeste"]


def test_city_regionals_sums_the_grouped_branches_before_picking_the_majority(db_session):
    # Sozinhas, as três filiais perdem para Jaru (4 contra 3, 3 e 3); somadas, vencem (9 contra 4).
    for n in range(3):
        _geo(db_session, f"m{n}", "Cidade Dividida", "Centro", regional="UNI - SAO MIGUEL DO GUAPORE")
        _geo(db_session, f"s{n}", "Cidade Dividida", "Centro", regional="UNI - SERINGUEIRAS")
        _geo(db_session, f"f{n}", "Cidade Dividida", "Centro", regional="UNI - SAO FRANCISCO DO GUAPORE")
    for n in range(4):
        _geo(db_session, f"j{n}", "Cidade Dividida", "Centro", regional="UNI - JARU")
    db_session.commit()
    assert contact_radar_service.city_regionals(db_session)["Cidade Dividida"] == "UNI - SAO FRANCISCO DO GUAPORE"


def test_radar_scope_of_a_sao_miguel_manager_covers_the_whole_sao_francisco_group(db_session):
    _geo(db_session, "s1", "Seringueiras", "Centro", regional="UNI - SERINGUEIRAS")
    _geo(db_session, "f1", "São Francisco do Guaporé", "Centro", regional="UNI - SAO FRANCISCO DO GUAPORE")
    _geo(db_session, "r1", "Rolim de Moura", "Centro", regional="UNI - ROLIM DE MOURA")
    for customer in ("s1", "f1", "r1"):
        _attendance(db_session, f"a-{customer}", customer)
    db_session.commit()
    radar = contact_radar_service.build_radar(
        db_session, window_minutes=60, allowed_regionals=["UNI - SAO MIGUEL DO GUAPORE"], deny_all=False, now=NOW
    )
    assert [r["regional"] for r in radar["regionals"]] == ["UNI - SAO FRANCISCO DO GUAPORE"]
    assert radar["totals"]["customers"] == 2
    assert sum(p["contacts"] for p in radar["series"]["points"]) == 2


def _tag(db, source_id, name, color):
    db.add(SupportOpaDimension(dimension_type="tag", source_id=source_id, name=name, payload_json={"_id": source_id, "nome": name, "cor": color}))


def _protocol_attendance(db, source_id, customer_id, protocol, *, tags="", minutes_ago=5, channel="whatsapp", department="Financeiro", department_id="20"):
    db.add(
        SupportOpaAttendance(
            source_id=source_id, protocol=protocol, customer_id=customer_id, channel=channel, status="F",
            department_id=department_id, department_name=department, attendant_name="Atendente Um",
            tag_ids_text=f",{tags}," if tags else ",", opened_at=NOW - timedelta(minutes=minutes_ago),
        )
    )


def test_list_protocols_returns_city_protocols_with_opa_tags_and_colors(db_session):
    _geo(db_session, "c1", "Jaru", "Centro", regional="UNI - JARU")
    _geo(db_session, "c2", "Jaru", "Setor 1", regional="UNI - JARU")
    _geo(db_session, "c3", "Ji-Parana", "Centro", regional="UNI - JI PARANA")
    _tag(db_session, "t1", "Sem conexão", "red")
    _tag(db_session, "t2", "IA Financeiro", "blue")
    _protocol_attendance(db_session, "a1", "c1", "UNI1", tags="t1,t2", minutes_ago=2)
    _protocol_attendance(db_session, "a2", "c2", "UNI2", tags="t2,tdesconhecida", minutes_ago=4, channel="pabx")
    _protocol_attendance(db_session, "a3", "c3", "UNI3", tags="t1")  # outra cidade
    _protocol_attendance(db_session, "a4", "c1", "UNI4", tags="t1", minutes_ago=90)  # fora da janela
    db_session.commit()

    page = contact_radar_service.list_protocols(
        db_session, regional="UNI - JARU", city="Jaru", window_minutes=60, allowed_regionals=[], deny_all=False, now=NOW
    )
    assert page["total"] == 2
    assert [item["protocol"] for item in page["items"]] == ["UNI1", "UNI2"]  # mais recente primeiro
    first, second = page["items"]
    assert [(tag["name"], tag["color"]) for tag in first["tags"]] == [("Sem conexão", "red"), ("IA Financeiro", "blue")]
    assert (first["neighborhood"], first["department_name"], first["channel"]) == ("Centro", "Financeiro", "whatsapp")
    # Etiqueta que não está no cadastro aparece neutra e identificada, em vez de sumir.
    assert [(tag["name"], tag["known"]) for tag in second["tags"]] == [("IA Financeiro", True), ("Etiqueta sem cadastro", False)]
    assert second["tags"][1]["id"] == "tdesconhecida" and second["tags"][1]["color"] is None
    assert all(tag["known"] for tag in first["tags"])
    assert second["channel"] == "pabx" and second["neighborhood"] == "Setor 1"


def test_list_protocols_paginates_and_applies_channel_and_department_filters(db_session):
    _geo(db_session, "c1", "Jaru", "Centro", regional="UNI - JARU")
    for n in range(5):
        _protocol_attendance(db_session, f"a{n}", "c1", f"UNI{n}", minutes_ago=n + 1)
    _protocol_attendance(db_session, "b1", "c1", "UNIX", minutes_ago=1, channel="pabx", department="Suporte Técnico", department_id="10")
    db_session.commit()
    args = dict(regional="UNI - JARU", city="Jaru", window_minutes=60, allowed_regionals=[], deny_all=False, now=NOW)
    first = contact_radar_service.list_protocols(db_session, limit=4, offset=0, **args)
    second = contact_radar_service.list_protocols(db_session, limit=4, offset=4, **args)
    assert first["total"] == 6 and len(first["items"]) == 4 and len(second["items"]) == 2
    assert not {i["protocol"] for i in first["items"]} & {i["protocol"] for i in second["items"]}
    assert contact_radar_service.list_protocols(db_session, channel="pabx", **args)["total"] == 1
    assert contact_radar_service.list_protocols(db_session, department_id="10", **args)["items"][0]["protocol"] == "UNIX"


def test_list_protocols_follows_the_cities_regional_and_the_user_scope(db_session):
    for n in range(3):
        _geo(db_session, f"m{n}", "Presidente Médici", "Centro", regional="UNI - PRESIDENTE MEDICI")
    _geo(db_session, "x", "Presidente Médici", "Centro", regional="UNI - JI PARANA")  # contrato em outra filial
    for customer in ("m0", "x"):
        _protocol_attendance(db_session, f"a-{customer}", customer, f"P-{customer}")
    db_session.commit()
    args = dict(city="Presidente Médici", window_minutes=60, deny_all=False, now=NOW)
    # A cidade é de Presidente Médici: os dois protocolos entram nela, nenhum em Ji-Paraná.
    right = contact_radar_service.list_protocols(db_session, regional="UNI - PRESIDENTE MEDICI", allowed_regionals=[], **args)
    assert right["total"] == 2
    wrong = contact_radar_service.list_protocols(db_session, regional="UNI - JI PARANA", allowed_regionals=[], **args)
    assert wrong["total"] == 0
    # Gestor de Ji-Paraná não vê; o de Presidente Médici vê. Quem não tem escopo nenhum (deny_all) não vê.
    assert contact_radar_service.list_protocols(db_session, regional="UNI - PRESIDENTE MEDICI", allowed_regionals=["UNI - JI PARANA"], **args)["total"] == 0
    assert contact_radar_service.list_protocols(db_session, regional="UNI - PRESIDENTE MEDICI", allowed_regionals=["UNI - PRESIDENTE MEDICI"], **args)["total"] == 2
    assert contact_radar_service.list_protocols(db_session, regional="UNI - PRESIDENTE MEDICI", allowed_regionals=[], **{**args, "deny_all": True})["total"] == 0


def test_list_protocols_by_neighborhood_keeps_each_protocol_in_the_neighborhood_where_it_was_opened(db_session):
    _geo(db_session, "c1", "Jaru", "Centro", regional="UNI - JARU")
    _geo(db_session, "c2", "Jaru", "Setor 1", regional="UNI - JARU")
    _geo(db_session, "c3", "Jaru", None, regional="UNI - JARU")
    _protocol_attendance(db_session, "a1", "c1", "CENTRO-1", minutes_ago=1)
    _protocol_attendance(db_session, "a2", "c1", "CENTRO-2", minutes_ago=2)
    _protocol_attendance(db_session, "a3", "c2", "SETOR-1", minutes_ago=3)
    _protocol_attendance(db_session, "a4", "c3", "SEM-BAIRRO", minutes_ago=4)
    db_session.commit()
    args = dict(regional="UNI - JARU", city="Jaru", window_minutes=60, allowed_regionals=[], deny_all=False, now=NOW)
    centro = contact_radar_service.list_protocols(db_session, neighborhood="Centro", **args)
    assert [i["protocol"] for i in centro["items"]] == ["CENTRO-1", "CENTRO-2"] and centro["total"] == 2
    assert all(i["neighborhood"] == "Centro" for i in centro["items"])
    setor = contact_radar_service.list_protocols(db_session, neighborhood="Setor 1", **args)
    assert [i["protocol"] for i in setor["items"]] == ["SETOR-1"]
    # "Bairro não informado" é o grupo dos clientes sem bairro no cadastro.
    sem = contact_radar_service.list_protocols(db_session, neighborhood=contact_radar_service.NO_NEIGHBORHOOD_LABEL, **args)
    assert [i["protocol"] for i in sem["items"]] == ["SEM-BAIRRO"]
    # Sem bairro, a cidade inteira.
    assert contact_radar_service.list_protocols(db_session, **args)["total"] == 4
    assert contact_radar_service.list_protocols(db_session, neighborhood="Bairro Que Nao Existe", **args)["total"] == 0


def test_list_protocols_by_date_range_uses_porto_velho_days(db_session):
    _geo(db_session, "c1", "Jaru", "Centro", regional="UNI - JARU")
    _protocol_attendance(db_session, "in", "c1", "DENTRO")
    db_session.add(
        SupportOpaAttendance(
            source_id="out", protocol="FORA", customer_id="c1", channel="whatsapp", status="F",
            tag_ids_text=",", opened_at=datetime(2026, 10, 21, 4, 30, tzinfo=timezone.utc),  # 00:30 do dia 21 em Porto Velho
        )
    )
    db_session.commit()
    page = contact_radar_service.list_protocols(
        db_session, regional="UNI - JARU", city="Jaru", date_from=date(2026, 10, 20), date_to=date(2026, 10, 20),
        allowed_regionals=[], deny_all=False, now=NOW,
    )
    assert [item["protocol"] for item in page["items"]] == ["DENTRO"]
