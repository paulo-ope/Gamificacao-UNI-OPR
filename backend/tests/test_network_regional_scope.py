"""P0-2 da auditoria técnica de 2026-09-15 (`docs/auditoria-tecnica-geral-2026-09-15.md`):
os endpoints/funções de rede (login/ONU/geolocalização - `/operations/network/*`,
`/ai/infra/*` e as tools MCP correspondentes) não aplicavam o escopo regional do usuário -
um gestor restrito a uma filial conseguia consultar dado de QUALQUER regional.

`regional_scope_or_deny` (app/services/regional.py) e cada função de
`operations/{login_geo_clusters,onu_signal_snapshot,login_search,login_aggregate,
coordinate_quality}.py` agora exigem `user` e aplicam o mesmo critério já usado em
`operations.queries._dimension_conditions`: `user=None` é acesso irrestrito deliberado (só
para chamador de sistema, ex. monitor de background); um usuário com `managed_regional`/
`managed_regionals` só enxerga essas regionais; `regional_manager_viewer` sem nenhuma
configurada não enxerga nada (nunca "tudo" por omissão).

Estes testes usam objetos `SimpleNamespace` como usuário fake (as funções só leem
`.managed_regional`/`.managed_regionals`/`.role` - não precisam de um `User` ORM completo),
o mesmo padrão já usado em outros testes deste módulo para simular perfis restritos sem
precisar montar o fluxo HTTP inteiro.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.modules.operations.coordinate_quality import coordinate_quality_audit
from app.modules.operations.login_aggregate import login_aggregate, login_outages, login_timeseries
from app.modules.operations.login_geo_clusters import find_offline_login_clusters, query_login_status
from app.modules.operations.login_search import get_login_detail, search_logins
from app.modules.operations.models import OperationLoginCurrentStatus, OperationLoginStatusSnapshot


def _user(*, managed_regional=None, managed_regionals=None, role="regional_manager_viewer"):
    return SimpleNamespace(managed_regional=managed_regional, managed_regionals=managed_regionals or [], role=role)


def _login(db_session, login_id: int, login: str, regional: str, *, online: str = "S", **overrides):
    now = datetime.now(timezone.utc)
    defaults = dict(
        login_id=login_id,
        login=login,
        regional=regional,
        online=online,
        status_changed_at=now,
        captured_at=now,
        latitude=-10.7 + login_id * 0.001,
        longitude=-62.2 + login_id * 0.001,
    )
    defaults.update(overrides)
    db_session.add(OperationLoginCurrentStatus(**defaults))


ROLIM = "UNI - ROLIM DE MOURA"
JI_PARANA = "UNI - JI PARANA"


def test_query_login_status_only_returns_the_scoped_regional(db_session):
    _login(db_session, 1, "login-rolim", ROLIM)
    _login(db_session, 2, "login-ji-parana", JI_PARANA)
    db_session.commit()

    scoped = query_login_status(db_session, user=_user(managed_regionals=[ROLIM]))
    assert [row.login for row in scoped] == ["login-rolim"]

    unrestricted = query_login_status(db_session, user=None)
    assert {row.login for row in unrestricted} == {"login-rolim", "login-ji-parana"}


def test_query_login_status_explicit_filter_cannot_widen_the_scope(db_session):
    """O `regionals` que o cliente manda só recorta DENTRO do escopo - não pode ser usado pra
    pedir uma regional fora do que o usuário tem direito."""
    _login(db_session, 1, "login-rolim", ROLIM)
    _login(db_session, 2, "login-ji-parana", JI_PARANA)
    db_session.commit()

    result = query_login_status(db_session, user=_user(managed_regionals=[ROLIM]), regionals=[JI_PARANA])
    assert result == []


def test_regional_manager_viewer_without_scope_sees_nothing_not_everything(db_session):
    _login(db_session, 1, "login-rolim", ROLIM)
    db_session.commit()

    result = query_login_status(db_session, user=_user(managed_regionals=[]))
    assert result == []


def test_base_manager_without_scope_is_not_denied_like_regional_manager_viewer(db_session):
    """Mesmo critério de `operations.queries._dimension_conditions`: só `regional_manager_viewer`
    sem regional configurada nega tudo - `base_manager` não tem esse fallback (convenção já
    existente no resto do sistema, não uma decisão nova desta correção)."""
    _login(db_session, 1, "login-rolim", ROLIM)
    db_session.commit()

    result = query_login_status(db_session, user=_user(managed_regionals=[], role="base_manager"))
    assert [row.login for row in result] == ["login-rolim"]


def test_search_logins_applies_the_same_scope(db_session):
    _login(db_session, 1, "login-rolim", ROLIM)
    _login(db_session, 2, "login-ji-parana", JI_PARANA)
    db_session.commit()

    result = search_logins(db_session, user=_user(managed_regionals=[ROLIM]))
    assert [item["login"] for item in result["items"]] == ["login-rolim"]
    assert result["total_encontrado"] == 1


def test_get_login_detail_returns_none_for_a_login_outside_scope(db_session):
    """404, não 403: o chamador (rota REST) transforma `None` em 404 - não revela que o login
    existe em outra regional."""
    _login(db_session, 1, "login-ji-parana", JI_PARANA)
    db_session.commit()

    detail = get_login_detail(db_session, user=_user(managed_regionals=[ROLIM]), login="login-ji-parana")
    assert detail is None

    own_detail = get_login_detail(db_session, user=_user(managed_regionals=[JI_PARANA]), login="login-ji-parana")
    assert own_detail is not None
    assert own_detail["login"] == "login-ji-parana"


def test_login_aggregate_counts_only_the_scoped_regional(db_session):
    _login(db_session, 1, "a", ROLIM, online="N")
    _login(db_session, 2, "b", ROLIM, online="N")
    _login(db_session, 3, "c", JI_PARANA, online="N")
    db_session.commit()

    result = login_aggregate(db_session, user=_user(managed_regionals=[ROLIM]), group_by="regional")
    assert result["data"] == [{"label": ROLIM, "quantity": 2, "percentage": 100.0}]


def test_login_outages_applies_the_scope(db_session):
    since = datetime.now(timezone.utc) - timedelta(minutes=10)
    _login(db_session, 1, "a", ROLIM, online="N", status_changed_at=since + timedelta(minutes=1))
    _login(db_session, 2, "b", JI_PARANA, online="N", status_changed_at=since + timedelta(minutes=1))
    db_session.commit()

    result = login_outages(db_session, user=_user(managed_regionals=[ROLIM]), since=since)
    assert [item["login"] for item in result["data"]] == ["a"]


def test_coordinate_quality_audit_only_reports_the_scoped_regional(db_session):
    _login(db_session, 1, "a", ROLIM)
    _login(db_session, 2, "b", JI_PARANA)
    db_session.commit()

    result = coordinate_quality_audit(db_session, user=_user(managed_regionals=[ROLIM]), entity="operations_login_current_status")
    assert [item["regional"] for item in result["data"]] == [ROLIM]


def test_offline_login_clusters_only_see_the_scoped_regional(db_session):
    now = datetime.now(timezone.utc)
    # 3 logins próximos em Rolim (formam cluster) + 3 próximos em Ji-Paraná (formariam outro
    # cluster, bem longe geograficamente do primeiro grupo).
    for index in range(3):
        _login(
            db_session, index + 1, f"rolim-{index}", ROLIM, online="N",
            status_changed_at=now, latitude=-11.7 + index * 0.0001, longitude=-61.5 + index * 0.0001,
        )
    for index in range(3):
        _login(
            db_session, index + 10, f"ji-{index}", JI_PARANA, online="N",
            status_changed_at=now, latitude=-10.8 + index * 0.0001, longitude=-61.9 + index * 0.0001,
        )
    db_session.commit()

    scoped = find_offline_login_clusters(db_session, user=_user(managed_regionals=[ROLIM]), min_cluster_size=3)
    assert len(scoped) == 1
    assert {point.login for point in scoped[0].logins} == {"rolim-0", "rolim-1", "rolim-2"}

    unrestricted = find_offline_login_clusters(db_session, user=None, min_cluster_size=3)
    assert len(unrestricted) == 2


def test_login_timeseries_counts_only_the_scoped_regional_via_join(db_session):
    """O caso mais delicado do P0-2: `operations_login_status_snapshots` não tem coluna própria
    de regional - o escopo só é possível fazendo JOIN com `operations_login_current_status`."""
    _login(db_session, 1, "a", ROLIM)
    _login(db_session, 2, "b", JI_PARANA)
    since = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)
    db_session.add(OperationLoginStatusSnapshot(login_id=1, online="N", captured_at=since))
    db_session.add(OperationLoginStatusSnapshot(login_id=2, online="N", captured_at=since))
    db_session.commit()

    scoped = login_timeseries(db_session, user=_user(managed_regionals=[ROLIM]), since=since, until=since + timedelta(minutes=1))
    assert scoped["data"][0]["disconnected"] == 1

    unrestricted = login_timeseries(db_session, user=None, since=since, until=since + timedelta(minutes=1))
    assert unrestricted["data"][0]["disconnected"] == 2
