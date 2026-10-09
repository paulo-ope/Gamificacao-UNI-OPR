"""Testes da presença dos atendentes na TV (`opa_presence_service`)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.support import opa_presence_service as presence
from app.modules.support.models import SupportOpaAttendance

NOW = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)


class FakeOpa:
    def __init__(self, users):
        self.users = users
        self.calls = 0

    def list_user_presence(self):
        self.calls += 1
        return self.users


@pytest.fixture(autouse=True)
def _clean_cache():
    presence.reset_users_cache()
    yield
    presence.reset_users_cache()


def _user(user_id, online, *, name=None, tipo="user", status="A", minutes_ago=None, updated_at="__auto__"):
    user = {"_id": user_id, "nome": name or f"Pessoa {user_id}", "tipo": tipo, "status": status, "online": online}
    if minutes_ago is not None:
        user["updatedAt"] = (NOW - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")
    elif updated_at != "__auto__":
        user["updatedAt"] = updated_at
    return user


def _attended(db_session, attendant_id, *, department_id="D-INT", days_ago=1, source=None):
    db_session.add(
        SupportOpaAttendance(
            source_id=source or f"S-{attendant_id}-{department_id}-{days_ago}",
            attendant_id=attendant_id,
            department_id=department_id,
            opened_at=NOW - timedelta(days=days_ago),
            raw_payload={},
        )
    )


def _counts(result):
    return {state["code"]: state["total"] for state in result["states"]}


def test_counts_each_presence_state_and_computes_available_percentage(db_session):
    users = [_user("1", "on"), _user("2", "on"), _user("3", "call"), _user("4", "pause"), _user("5", "off"), _user("6", "oc"), _user("7", "au"), _user("8", "off")]
    for user in users:
        _attended(db_session, user["_id"])
    db_session.flush()

    result = presence.build_presence(db_session, FakeOpa(users), NOW)

    assert _counts(result) == {"on": 2, "call": 1, "au": 1, "pause": 1, "oc": 1, "off": 2}
    assert result["total"] == 8
    assert result["available_percentage"] == 25.0  # 2 online de 8: mesma conta do painel do OPA (6/48 = 12,5%)


def test_ringing_is_declared_unavailable_because_the_api_does_not_report_it(db_session):
    users = [_user("1", "call")]
    _attended(db_session, "1")
    db_session.flush()

    assert presence.build_presence(db_session, FakeOpa(users), NOW)["ringing_available"] is False


def test_agents_list_shows_status_and_time_in_status(db_session):
    users = [_user("1", "oc", name="Bruno", minutes_ago=30), _user("2", "pause", name="Carla", minutes_ago=5)]
    for user in users:
        _attended(db_session, user["_id"])
    db_session.flush()

    result = presence.build_presence(db_session, FakeOpa(users), NOW)

    by_name = {agent["name"]: agent for agent in result["agents"]}
    assert by_name["Bruno"]["state_label"] == "Ocupado" and by_name["Bruno"]["seconds_in_state"] == 30 * 60
    assert by_name["Carla"]["state_label"] == "Em pausa" and by_name["Carla"]["seconds_in_state"] == 5 * 60


def test_agents_list_only_has_states_that_need_attention_and_orders_by_priority_then_longest(db_session):
    users = [
        _user("1", "on", minutes_ago=2),  # online: fora da lista
        _user("2", "off", minutes_ago=999),  # offline: fora da lista
        _user("3", "au", name="Ausente curto", minutes_ago=3),
        _user("4", "pause", name="Pausa longa", minutes_ago=40),
        _user("5", "pause", name="Pausa curta", minutes_ago=4),
        _user("6", "call", name="Em ligação", minutes_ago=1),
        _user("7", "oc", name="Ocupado", minutes_ago=20),
    ]
    for user in users:
        _attended(db_session, user["_id"])
    db_session.flush()

    result = presence.build_presence(db_session, FakeOpa(users), NOW)

    # Só os 4 primeiros cabem na TV; o total real (5) vai junto para a tela mostrar "+1".
    assert [agent["name"] for agent in result["agents"]] == ["Em ligação", "Ocupado", "Pausa longa", "Pausa curta"]
    assert result["agents_total"] == 5


def test_agents_list_is_limited_but_reports_the_real_total(db_session):
    users = [_user(str(index), "pause", minutes_ago=index + 1) for index in range(presence.AGENT_LIST_LIMIT + 3)]
    for user in users:
        _attended(db_session, user["_id"])
    db_session.flush()

    result = presence.build_presence(db_session, FakeOpa(users), NOW)

    assert len(result["agents"]) == presence.AGENT_LIST_LIMIT
    assert result["agents_total"] == presence.AGENT_LIST_LIMIT + 3
    assert result["agents"][0]["seconds_in_state"] > result["agents"][-1]["seconds_in_state"]  # mais antigo primeiro


@pytest.mark.parametrize("value", [None, "", "isso-nao-e-data", 12345])
def test_time_in_status_is_none_when_the_date_is_missing_or_invalid(db_session, value):
    users = [_user("1", "oc", updated_at=value)]
    _attended(db_session, "1")
    db_session.flush()

    result = presence.build_presence(db_session, FakeOpa(users), NOW)

    assert result["agents"][0]["seconds_in_state"] is None  # nunca 0 nem um palpite


def test_time_in_status_never_goes_negative_when_the_opa_clock_is_ahead(db_session):
    users = [_user("1", "oc", updated_at=(NOW + timedelta(minutes=3)).isoformat())]
    _attended(db_session, "1")
    db_session.flush()

    assert presence.build_presence(db_session, FakeOpa(users), NOW)["agents"][0]["seconds_in_state"] == 0


def test_only_people_who_attended_recently_are_part_of_the_team(db_session):
    users = [_user("1", "on"), _user("2", "off"), _user("3", "off")]
    _attended(db_session, "1")
    _attended(db_session, "2", days_ago=presence.ACTIVITY_WINDOW_DAYS + 5)  # atendeu, mas há muito tempo
    db_session.flush()  # "3" nunca atendeu

    result = presence.build_presence(db_session, FakeOpa(users), NOW)

    assert result["total"] == 1
    assert _counts(result)["on"] == 1


def test_department_scope_limits_the_team_to_that_departments_attendants(db_session):
    users = [_user("1", "on"), _user("2", "on"), _user("3", "off")]
    _attended(db_session, "1", department_id="D-INT")
    _attended(db_session, "2", department_id="D-FIN")
    _attended(db_session, "3", department_id="D-INT")
    db_session.flush()

    scoped = presence.build_presence(db_session, FakeOpa(users), NOW, ["D-INT"])
    everyone = presence.build_presence(db_session, FakeOpa(users), NOW)

    assert scoped["total"] == 2 and scoped["scope"] == "departments"
    assert everyone["total"] == 3 and everyone["scope"] == "all"


def test_bots_and_inactive_users_never_count(db_session):
    users = [_user("1", "on"), _user("2", "on", tipo="bot"), _user("3", "on", status="I")]
    for user in users:
        _attended(db_session, user["_id"])
    db_session.flush()

    result = presence.build_presence(db_session, FakeOpa(users), NOW)

    assert result["total"] == 1


def test_unknown_presence_code_is_shown_as_other_and_reported(db_session):
    users = [_user("1", "on"), _user("2", "ring")]  # `ring` não é um código conhecido
    for user in users:
        _attended(db_session, user["_id"])
    db_session.flush()

    result = presence.build_presence(db_session, FakeOpa(users), NOW)

    assert _counts(result)["other"] == 1
    assert result["unmapped_codes"] == ["'ring'"]


def test_empty_team_has_no_percentage_instead_of_zero(db_session):
    result = presence.build_presence(db_session, FakeOpa([_user("1", "on")]), NOW)

    assert result["total"] == 0
    assert result["available_percentage"] is None


def test_users_are_cached_briefly_so_several_tvs_do_not_multiply_opa_calls(db_session):
    fake = FakeOpa([_user("1", "on")])
    _attended(db_session, "1")
    db_session.flush()

    presence.build_presence(db_session, fake, NOW)
    presence.build_presence(db_session, fake, NOW)

    assert fake.calls == 1
