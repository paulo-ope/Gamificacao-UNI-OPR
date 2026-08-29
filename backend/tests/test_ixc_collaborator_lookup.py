"""Fase 2C do Portal - convite inteligente por CPF integrado ao IXC (pedido do usuário em
2026-08-29, ver docs/portal-ciclo-vida-conta-colaborador.md). `funcionarios` é a tabela correta de
colaboradores no IXC (RH/técnico de campo, ~864 registros na instalação real) - `cliente` NUNCA é
usada como fonte aqui, é uma entidade completamente diferente (assinante/contrato).

`52998224725`/`11144477735` são CPFs de teste com dígito verificador válido (mesmos usados em
test_portal_first_access.py).
"""

from fastapi.testclient import TestClient

from app.api.routes import invites as invites_module
from app.core.security import get_current_user, hash_password
from app.db.session import get_db
from app.main import app
from app.models import AccountActionToken, AuditLog, Collaborator, User
from app.services.ixc_client import IxcApiError, IxcPage

VALID_CPF = "529.982.247-25"
VALID_CPF_DIGITS = "52998224725"
OTHER_VALID_CPF_DIGITS = "11144477735"


class FakeFuncionariosClient:
    """Cliente IXC em memória, só para a tabela `funcionarios` - mesmo espírito do `FakeIxcClient`
    de test_ixc_client_partitioning.py, reduzido ao que a busca por CPF precisa (filtro `=` num
    único campo)."""

    def __init__(self, records: list[dict]):
        self.records = records
        self.calls: list[dict] = []

    def list(self, table, *, grid_param=None, page=1, rp=100, sortname=None, sortorder="asc"):
        self.calls.append({"table": table, "grid_param": grid_param})
        assert table == "funcionarios"
        cpf_filter = next((item["P"] for item in (grid_param or []) if item["TB"] == "funcionarios.cpf_cnpj"), None)
        matches = [r for r in self.records if r.get("cpf_cnpj") == cpf_filter]
        return IxcPage(records=matches, total=len(matches), page=page)


class ErroringClient:
    def list(self, *args, **kwargs):
        raise IxcApiError("timeout simulado")


def _funcionario(ixc_id=901, cpf=VALID_CPF_DIGITS, name="Fulano Funcionario", email="fulano@uni.com.br", phone="69999990000", ativo="S", departamento=3, setor=9):
    return {
        "id": str(ixc_id),
        "funcionario": name,
        "cpf_cnpj": cpf,
        "email": email,
        "fone_celular": phone,
        "ativo": ativo,
        "id_departamento": str(departamento),
        "id_setor_padrao": str(setor),
    }


def _admin_client(db_session, admin_user) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    return TestClient(app)


def test_invalid_cpf_never_reaches_ixc(db_session, admin_user, monkeypatch):
    fake = FakeFuncionariosClient([])
    monkeypatch.setattr(invites_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.post("/api/invites/lookup-ixc-cpf", json={"cpf": "111.111.111-11"})
        assert response.status_code == 422
    app.dependency_overrides.clear()

    assert fake.calls == []  # nunca chegou a consultar o IXC


def test_non_admin_cannot_lookup(db_session):
    non_admin = User(name="Sem Permissao", email="sem.permissao.ixc@pytest.local", role="viewer", active=True, password_hash=hash_password("Qualquer123"))
    db_session.add(non_admin)
    db_session.commit()

    with _admin_client(db_session, non_admin) as client:
        response = client.post("/api/invites/lookup-ixc-cpf", json={"cpf": VALID_CPF})
        assert response.status_code == 403
    app.dependency_overrides.clear()


def test_cpf_not_found_returns_controlled_404(db_session, admin_user, monkeypatch):
    fake = FakeFuncionariosClient([_funcionario(cpf=OTHER_VALID_CPF_DIGITS)])
    monkeypatch.setattr(invites_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.post("/api/invites/lookup-ixc-cpf", json={"cpf": VALID_CPF})
        assert response.status_code == 404
        assert "Traceback" not in response.text
    app.dependency_overrides.clear()

    entry = db_session.query(AuditLog).filter(AuditLog.action == "ixc_collaborator.lookup_not_found").one()
    assert VALID_CPF_DIGITS not in str(entry.after_data)
    assert "25" in str(entry.after_data)  # mascarado, últimos dígitos visíveis


def test_ixc_api_error_returns_controlled_502(db_session, admin_user, monkeypatch):
    monkeypatch.setattr(invites_module, "get_ixc_client", lambda: ErroringClient())

    with _admin_client(db_session, admin_user) as client:
        response = client.post("/api/invites/lookup-ixc-cpf", json={"cpf": VALID_CPF})
        assert response.status_code == 502
        assert "Traceback" not in response.text
    app.dependency_overrides.clear()


def test_multiple_matches_requires_manual_review(db_session, admin_user, monkeypatch):
    fake = FakeFuncionariosClient([_funcionario(ixc_id=1, cpf=VALID_CPF_DIGITS), _funcionario(ixc_id=2, cpf=VALID_CPF_DIGITS)])
    monkeypatch.setattr(invites_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.post("/api/invites/lookup-ixc-cpf", json={"cpf": VALID_CPF})
        assert response.status_code == 409
    app.dependency_overrides.clear()


def test_cpf_found_returns_masked_safe_data(db_session, admin_user, monkeypatch):
    fake = FakeFuncionariosClient([_funcionario()])
    monkeypatch.setattr(invites_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.post("/api/invites/lookup-ixc-cpf", json={"cpf": VALID_CPF})
        assert response.status_code == 200
        body = response.json()
        assert body["ixc_employee_id"] == 901
        assert body["name"] == "Fulano Funcionario"
        assert body["email"] == "fulano@uni.com.br"
        assert body["phone"] == "69999990000"
        assert body["active"] is True
        assert body["department_id"] == 3
        assert body["sector_id"] == 9
        assert body["cpf_masked"] == "***.***.***-25"
        assert VALID_CPF_DIGITS not in response.text
        assert body["local_collaborator_id"] is None
        assert body["local_match_kind"] is None
    app.dependency_overrides.clear()

    entry = db_session.query(AuditLog).filter(AuditLog.action == "ixc_collaborator.lookup_found").one()
    assert VALID_CPF_DIGITS not in str(entry.before_data) + str(entry.after_data)


def test_lookup_finds_cpf_stored_with_mask_in_ixc(db_session, admin_user, monkeypatch):
    """Achado real em 2026-08-29: `funcionarios.cpf_cnpj` nesta instalação do IXC guarda o CPF COM
    MÁSCARA (`702.401.102-50`), não só dígitos - um CPF de teste com dígito verificador válido
    (`70240110250`) não era encontrado apesar de existir, porque o filtro `=` enviava só dígitos.
    Este teste fixa esse comportamento: a busca precisa achar o registro mesmo guardado com
    máscara, tentando esse formato primeiro (é o confirmado contra a API real)."""
    fake = FakeFuncionariosClient([_funcionario(ixc_id=378, cpf="702.401.102-50", name="Paulo Henrique Alves Peixoto Soares")])
    monkeypatch.setattr(invites_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.post("/api/invites/lookup-ixc-cpf", json={"cpf": "702.401.102-50"})
        assert response.status_code == 200
        body = response.json()
        assert body["ixc_employee_id"] == 378
        assert body["name"] == "Paulo Henrique Alves Peixoto Soares"
    app.dependency_overrides.clear()

    # Achou de primeira, com o formato mascarado - não precisou do fallback de dígitos puros.
    assert len(fake.calls) == 1


def test_lookup_falls_back_to_digits_only_when_not_stored_with_mask(db_session, admin_user, monkeypatch):
    """Resguardo pro caso contrário (registro legado gravado só com dígitos) - a segunda tentativa
    só acontece quando a primeira (mascarada) não encontra nada."""
    fake = FakeFuncionariosClient([_funcionario(cpf=VALID_CPF_DIGITS)])
    monkeypatch.setattr(invites_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.post("/api/invites/lookup-ixc-cpf", json={"cpf": VALID_CPF})
        assert response.status_code == 200
    app.dependency_overrides.clear()

    assert len(fake.calls) == 2
    assert fake.calls[0]["grid_param"][0]["P"] == "529.982.247-25"  # tentativa 1: mascarado
    assert fake.calls[1]["grid_param"][0]["P"] == VALID_CPF_DIGITS  # tentativa 2: só dígitos


def test_lookup_suggests_existing_collaborator_by_ixc_employee_id(db_session, admin_user, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Ja Vinculado Por Id")
    collaborator.ixc_employee_id = 901
    db_session.commit()

    fake = FakeFuncionariosClient([_funcionario(name="Nome Diferente No Ixc")])
    monkeypatch.setattr(invites_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.post("/api/invites/lookup-ixc-cpf", json={"cpf": VALID_CPF})
        assert response.status_code == 200
        body = response.json()
        assert body["local_collaborator_id"] == collaborator.id
        assert body["local_match_kind"] == "ixc_employee_id"
    app.dependency_overrides.clear()


def test_invite_from_ixc_uses_ixc_employee_id_link_and_enriches_blank_fields(db_session, admin_user, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Enriquecer Cadastro")
    collaborator.ixc_employee_id = 901
    db_session.commit()
    assert collaborator.cpf is None
    assert collaborator.email is None

    fake = FakeFuncionariosClient([_funcionario()])
    monkeypatch.setattr(invites_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.post(
            "/api/invites/from-ixc",
            json={"cpf": VALID_CPF, "collaborator_id": collaborator.id, "email": "fulano@uni.com.br"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["collaborator_id"] == collaborator.id
        assert len(body["token"]) > 20
    app.dependency_overrides.clear()

    db_session.refresh(collaborator)
    assert collaborator.cpf == VALID_CPF_DIGITS
    assert collaborator.email == "fulano@uni.com.br"
    assert collaborator.phone == "69999990000"

    invite = db_session.query(AccountActionToken).filter(AccountActionToken.collaborator_id == collaborator.id).one()
    assert invite.status == "pending"

    enrich_entry = db_session.query(AuditLog).filter(AuditLog.action == "collaborator.enriched_from_ixc").one()
    payload = str(enrich_entry.before_data) + str(enrich_entry.after_data)
    assert VALID_CPF_DIGITS not in payload


def test_invite_from_ixc_does_not_duplicate_collaborator_when_already_linked(db_session, admin_user, make_collaborator, monkeypatch):
    """Vínculo por CPF (sem ixc_employee_id ainda) também deve ser reaproveitado - nunca criar um
    `Collaborator` novo quando um já corresponde."""
    collaborator = make_collaborator(name="Ja Existe Por Cpf")
    collaborator.cpf = VALID_CPF_DIGITS
    db_session.commit()

    before_count = db_session.query(Collaborator).count()

    fake = FakeFuncionariosClient([_funcionario()])
    monkeypatch.setattr(invites_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.post(
            "/api/invites/from-ixc",
            json={"cpf": VALID_CPF, "collaborator_id": collaborator.id, "email": "fulano@uni.com.br"},
        )
        assert response.status_code == 201
    app.dependency_overrides.clear()

    assert db_session.query(Collaborator).count() == before_count  # nenhum colaborador novo criado
    db_session.refresh(collaborator)
    assert collaborator.ixc_employee_id == 901  # enriquecido, não duplicado


def test_invite_from_ixc_blocks_on_conflicting_cpf(db_session, admin_user, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Cpf Conflitante")
    collaborator.cpf = OTHER_VALID_CPF_DIGITS  # CPF diferente do que o IXC vai devolver
    db_session.commit()

    fake = FakeFuncionariosClient([_funcionario()])
    monkeypatch.setattr(invites_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.post(
            "/api/invites/from-ixc",
            json={"cpf": VALID_CPF, "collaborator_id": collaborator.id, "email": "fulano@uni.com.br"},
        )
        assert response.status_code == 409
    app.dependency_overrides.clear()

    assert db_session.query(AccountActionToken).filter(AccountActionToken.collaborator_id == collaborator.id).first() is None


def test_invite_from_ixc_blocks_on_conflicting_ixc_employee_id(db_session, admin_user, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Id Ixc Conflitante")
    collaborator.ixc_employee_id = 555  # id diferente do que o IXC vai devolver (901)
    db_session.commit()

    fake = FakeFuncionariosClient([_funcionario()])
    monkeypatch.setattr(invites_module, "get_ixc_client", lambda: fake)

    with _admin_client(db_session, admin_user) as client:
        response = client.post(
            "/api/invites/from-ixc",
            json={"cpf": VALID_CPF, "collaborator_id": collaborator.id, "email": "fulano@uni.com.br"},
        )
        assert response.status_code == 409
    app.dependency_overrides.clear()
