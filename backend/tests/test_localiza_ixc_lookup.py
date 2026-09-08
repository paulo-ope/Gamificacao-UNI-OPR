"""Busca de cliente no IXC (login ou CPF) para autopreencher o formulário do UNI Localiza.

Campos confirmados por sondagem manual contra a API real em 2026-09-08 (ver
`app/modules/localiza/ixc_lookup.py`) - os testes aqui usam um cliente IXC falso em memória,
nunca a API real (mesmo padrão de `test_ixc_collaborator_lookup.py`).
"""

from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.db.session import get_db
from app.main import app
from app.modules.localiza import router as localiza_router_module
from app.services.ixc_client import IxcApiError, IxcPage

VALID_CPF_DIGITS = "52998224725"
VALID_CPF_MASKED = "529.982.247-25"


class FakeIxcClient:
    """Só o suficiente para `radusuarios`/`cliente` com filtro `=` num único campo por chamada -
    mesmo espírito do `FakeFuncionariosClient` de test_ixc_collaborator_lookup.py."""

    def __init__(self, radusuarios: list[dict], clientes: list[dict]):
        self.radusuarios = radusuarios
        self.clientes = clientes
        self.calls: list[dict] = []

    def list(self, table, *, grid_param=None, page=1, rp=100, sortname=None, sortorder="asc"):
        self.calls.append({"table": table, "grid_param": grid_param})
        field, op, value = grid_param[0]["TB"], grid_param[0]["OP"], grid_param[0]["P"]
        assert op == "="
        rows = self.radusuarios if table == "radusuarios" else self.clientes
        key = field.split(".", 1)[1]
        matches = [r for r in rows if str(r.get(key)) == str(value)]
        return IxcPage(records=matches, total=len(matches), page=page)


class ErroringClient:
    def list(self, *args, **kwargs):
        raise IxcApiError("timeout simulado")


def _login(login_id=72928, login="paulo.soares_1", id_cliente=112781, lat=-9.42, lon=-61.99):
    return {"id": str(login_id), "login": login, "id_cliente": str(id_cliente), "latitude": lat, "longitude": lon}


def _cliente(cliente_id=112781, razao="Paulo Soares", cpf=VALID_CPF_MASKED, lat=-9.42, lon=-61.99):
    return {"id": str(cliente_id), "razao": razao, "cnpj_cpf": cpf, "latitude": lat, "longitude": lon}


def _admin_client(db_session, admin_user) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    return TestClient(app)


def test_search_by_numeric_login_id(db_session, admin_user, monkeypatch):
    fake = FakeIxcClient(radusuarios=[_login()], clientes=[_cliente()])
    monkeypatch.setattr(localiza_router_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.get("/api/localiza/ixc/search", params={"login": "72928"})
        assert response.status_code == 200
        matches = response.json()["matches"]
        assert len(matches) == 1
        assert matches[0]["login"] == "paulo.soares_1"
        assert matches[0]["name"] == "Paulo Soares"
        assert matches[0]["cpf_masked"] == "***.***.***-25"
        assert matches[0]["latitude"] == -9.42
    app.dependency_overrides.clear()


def test_search_by_login_string(db_session, admin_user, monkeypatch):
    fake = FakeIxcClient(radusuarios=[_login()], clientes=[_cliente()])
    monkeypatch.setattr(localiza_router_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.get("/api/localiza/ixc/search", params={"login": "paulo.soares_1"})
        assert response.status_code == 200
        assert len(response.json()["matches"]) == 1
    app.dependency_overrides.clear()


def test_search_by_login_never_exposes_full_cpf(db_session, admin_user, monkeypatch):
    fake = FakeIxcClient(radusuarios=[_login()], clientes=[_cliente()])
    monkeypatch.setattr(localiza_router_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.get("/api/localiza/ixc/search", params={"login": "72928"})
        assert VALID_CPF_DIGITS not in response.text
        assert "529.982.247-25" not in response.text
    app.dependency_overrides.clear()


def test_search_by_cpf_returns_one_row_per_login(db_session, admin_user, monkeypatch):
    fake = FakeIxcClient(
        radusuarios=[_login(login_id=1, login="cliente_casa"), _login(login_id=2, login="cliente_trabalho", id_cliente=112781)],
        clientes=[_cliente()],
    )
    monkeypatch.setattr(localiza_router_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.get("/api/localiza/ixc/search", params={"cpf": VALID_CPF_DIGITS})
        assert response.status_code == 200
        matches = response.json()["matches"]
        assert len(matches) == 2
        assert {m["login"] for m in matches} == {"cliente_casa", "cliente_trabalho"}
    app.dependency_overrides.clear()


def test_search_by_cpf_with_no_login_still_returns_customer(db_session, admin_user, monkeypatch):
    """Contrato assinado mas ainda não instalado - sem login, mas o atendente ainda precisa achar
    o cliente pelo nome pra gerar o link."""
    fake = FakeIxcClient(radusuarios=[], clientes=[_cliente()])
    monkeypatch.setattr(localiza_router_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.get("/api/localiza/ixc/search", params={"cpf": VALID_CPF_DIGITS})
        assert response.status_code == 200
        matches = response.json()["matches"]
        assert len(matches) == 1
        assert matches[0]["login"] is None
        assert matches[0]["cliente_id"] == 112781
    app.dependency_overrides.clear()


def test_invalid_cpf_never_reaches_ixc(db_session, admin_user, monkeypatch):
    fake = FakeIxcClient(radusuarios=[], clientes=[])
    monkeypatch.setattr(localiza_router_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.get("/api/localiza/ixc/search", params={"cpf": "111.111.111-11"})
        assert response.status_code == 422
    app.dependency_overrides.clear()

    assert fake.calls == []


def test_rejects_both_login_and_cpf_together(db_session, admin_user, monkeypatch):
    fake = FakeIxcClient(radusuarios=[], clientes=[])
    monkeypatch.setattr(localiza_router_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.get("/api/localiza/ixc/search", params={"login": "72928", "cpf": VALID_CPF_DIGITS})
        assert response.status_code == 422
        response2 = client.get("/api/localiza/ixc/search")
        assert response2.status_code == 422
    app.dependency_overrides.clear()


def test_non_authorized_role_cannot_search(db_session):
    from app.core.security import hash_password
    from app.models import User

    viewer = User(name="Sem Permissao", email="sem.permissao.ixc.localiza@pytest.local", role="collaborator", active=True, password_hash=hash_password("Qualquer123"))
    db_session.add(viewer)
    db_session.commit()

    with _admin_client(db_session, viewer) as client:
        response = client.get("/api/localiza/ixc/search", params={"login": "72928"})
        assert response.status_code == 403
    app.dependency_overrides.clear()


def test_ixc_unavailable_returns_friendly_error(db_session, admin_user, monkeypatch):
    monkeypatch.setattr(localiza_router_module, "get_ixc_client", lambda: ErroringClient())

    with _admin_client(db_session, admin_user) as client:
        response = client.get("/api/localiza/ixc/search", params={"login": "72928"})
        assert response.status_code == 502
        assert "IXC" in response.json()["detail"]
    app.dependency_overrides.clear()
