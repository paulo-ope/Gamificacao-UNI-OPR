from __future__ import annotations

from datetime import date

from app.modules.support import ixc_new_login


class FakeClient:
    """Simula `su_oss_chamado` (O.S. finalizadas do assunto 74) e `funcionarios` do IXC."""

    def __init__(self):
        self.calls = []

    def list_all(self, table, *, grid_param=None, **kwargs):
        self.calls.append((table, grid_param))
        if table == "su_oss_chamado":
            yield {"id": "1", "id_tecnico": "138"}
            yield {"id": "2", "id_tecnico": "138"}
            yield {"id": "3", "id_tecnico": "835"}
            yield {"id": "4", "id_tecnico": "0"}  # sem técnico
        elif table == "funcionarios":
            yield {"id": "138", "funcionario": "ALESSANDRO DINIZ LOSS"}
            yield {"id": "835", "funcionario": "YURI CARVALHO GADELHA"}


def test_fetch_period_counts_by_technician_and_filters_subject_status_and_dates():
    client = FakeClient()

    result = ixc_new_login._fetch_period(client, date(2026, 10, 1), date(2026, 10, 14))

    assert result == {
        "finalized": 4,
        "by_name": {"ALESSANDRO DINIZ LOSS": 2, "YURI CARVALHO GADELHA": 1, "": 1},
    }
    filters = {(item["TB"], item["OP"]): item["P"] for item in client.calls[0][1]}
    assert filters[("su_oss_chamado.id_assunto", "=")] == "74"
    assert filters[("su_oss_chamado.status", "=")] == "F"
    assert filters[("su_oss_chamado.data_fechamento", ">=")] == "2026-10-01 00:00:00"
    assert filters[("su_oss_chamado.data_fechamento", "<=")] == "2026-10-14 23:59:59"


def test_finalized_in_period_uses_short_cache():
    ixc_new_login.clear_cache()
    client = FakeClient()

    first = ixc_new_login.finalized_in_period(date(2026, 10, 1), date(2026, 10, 14), client=client)
    second = ixc_new_login.finalized_in_period(date(2026, 10, 1), date(2026, 10, 14), client=client)

    assert first == second
    assert sum(1 for table, _ in client.calls if table == "su_oss_chamado") == 1  # a segunda saiu do cache
    ixc_new_login.clear_cache()


def test_fetch_period_gives_up_after_deadline(monkeypatch):
    monkeypatch.setattr(ixc_new_login, "DEADLINE_SECONDS", -1.0)

    try:
        ixc_new_login._fetch_period(FakeClient(), date(2026, 10, 1), date(2026, 10, 14))
    except TimeoutError:
        return
    raise AssertionError("deveria ter estourado o tempo limite do IXC")
