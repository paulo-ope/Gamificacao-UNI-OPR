"""Fase 2D do Portal - solicitação de acesso (pedido original em 2026-08-28, estendida em
2026-08-29 pra autoatendimento por CPF e, no mesmo dia, pra aprovação sem convite, ver
docs/portal-ciclo-vida-conta-colaborador.md seção 6). Canal público pra quem não tem conta nem
convite pedir acesso - a solicitação nunca cria `User` nem vínculo sozinha; aprovar cria a conta
DIRETO, com a senha que a própria pessoa já escolheu no formulário (não gera mais convite/link).

Desde a extensão de 2026-08-29: nome e telefone vêm do IXC (revalidados no servidor, nunca
confiando no que o cliente manda) quando o CPF é encontrado; e-mail é SEMPRE digitado por quem
solicita (nunca herdado do IXC) e restrito ao domínio corporativo `@souuni.com`. A pessoa também
escolhe a própria senha (`new_password`/`confirm_password`) - só o hash é armazenado.

`52998224725`/`11144477735` são CPFs de teste com dígito verificador válido (mesmos usados em
test_portal_first_access.py).
"""

import pytest
from fastapi.testclient import TestClient

from app.api.routes import access_requests as access_requests_module
from app.core.security import get_current_user, verify_password
from app.db.session import get_db
from app.main import app
from app.models import AccountActionToken, AuditLog, PortalAccessRequest, User
from app.services.ixc_client import IxcApiError, IxcPage

VALID_CPF = "529.982.247-25"
VALID_CPF_DIGITS = "52998224725"
OTHER_VALID_CPF_DIGITS = "11144477735"
VALID_PASSWORD = "SenhaForte123"


class FakeFuncionariosClient:
    """Mesmo espírito do `FakeFuncionariosClient` de test_ixc_collaborator_lookup.py - reduzido ao
    que a busca por CPF precisa (filtro `=` num único campo, com fallback pro formato mascarado)."""

    def __init__(self, records: list[dict]):
        self.records = records
        self.calls: list[dict] = []

    def list(self, table, *, grid_param=None, page=1, rp=100, sortname=None, sortorder="asc"):
        self.calls.append({"table": table, "grid_param": grid_param})
        cpf_filter = next((item["P"] for item in (grid_param or []) if item["TB"] == "funcionarios.cpf_cnpj"), None)
        matches = [r for r in self.records if r.get("cpf_cnpj") == cpf_filter]
        return IxcPage(records=matches, total=len(matches), page=page)


class ErroringClient:
    def list(self, *args, **kwargs):
        raise IxcApiError("timeout simulado")


def _funcionario(cpf=VALID_CPF_DIGITS, name="Fulano Funcionario", phone="69999990001"):
    return {"id": "1", "funcionario": name, "cpf_cnpj": cpf, "email": "fulano@uni.com.br", "fone_celular": phone, "ativo": "S"}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Dicts em memória no NÍVEL DO MÓDULO (mesmo padrão do rate limiter de `/auth/login`) - sem
    resetar entre testes, o TestClient (sempre o mesmo IP fake) acumula tentativas ao longo do
    arquivo e algum teste no meio do caminho tomaria 429 em vez do status esperado. Isolamento só
    de teste - não muda o comportamento real do rate limiter."""
    access_requests_module._submit_attempts.clear()
    access_requests_module._lookup_attempts.clear()
    yield


def _admin_client(db_session, admin_user) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    return TestClient(app)


def _public_client(db_session, ixc_client=None, monkeypatch=None) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    if ixc_client is not None:
        monkeypatch.setattr(access_requests_module, "get_ixc_client", lambda: ixc_client)
    return TestClient(app)


# --------------------------------------------------------------------------------------
# Autoatendimento por CPF (`POST /access-requests/lookup-cpf`) - achado real em 2026-08-29
# --------------------------------------------------------------------------------------


def test_lookup_cpf_returns_name_and_masked_phone_when_found(db_session, monkeypatch):
    fake = FakeFuncionariosClient([_funcionario(name="Colaborador Encontrado", phone="69988887777")])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post("/api/access-requests/lookup-cpf", json={"cpf": VALID_CPF})
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Colaborador Encontrado"
        assert body["phone_masked"] == "(69) ****-7777"
        assert "email" not in body
        assert VALID_CPF_DIGITS not in response.text
        assert "69988887777" not in response.text
    app.dependency_overrides.clear()


def test_lookup_cpf_not_found_returns_controlled_404(db_session, monkeypatch):
    fake = FakeFuncionariosClient([])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post("/api/access-requests/lookup-cpf", json={"cpf": VALID_CPF})
        assert response.status_code == 404
        assert "Traceback" not in response.text
    app.dependency_overrides.clear()


def test_lookup_cpf_invalid_never_reaches_ixc(db_session, monkeypatch):
    fake = FakeFuncionariosClient([])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post("/api/access-requests/lookup-cpf", json={"cpf": "111.111.111-11"})
        assert response.status_code == 422
    app.dependency_overrides.clear()
    assert fake.calls == []


def test_lookup_cpf_audit_never_stores_full_cpf(db_session, monkeypatch):
    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        client.post("/api/access-requests/lookup-cpf", json={"cpf": VALID_CPF})
    app.dependency_overrides.clear()

    entry = db_session.query(AuditLog).filter(AuditLog.action == "ixc_collaborator.self_lookup_found").one()
    assert VALID_CPF_DIGITS not in str(entry.after_data)
    assert entry.user_id is None  # autoatendimento não tem conta ainda


# --------------------------------------------------------------------------------------
# Envio da solicitação (`POST /access-requests`)
# --------------------------------------------------------------------------------------


def test_submit_always_uses_ixc_name_ignoring_client_supplied_value(db_session, monkeypatch):
    """Nome nunca vem do cliente quando o CPF é encontrado no IXC - é a confirmação de
    identidade ("é você?"), não pode ser trocado por quem preenche o formulário."""
    fake = FakeFuncionariosClient([_funcionario(name="Nome Real No Ixc", phone="69911112222")])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post(
            "/api/access-requests",
            json={
                "cpf": VALID_CPF,
                "email": "fulano@souuni.com",
                "name": "Nome Forjado",
                "new_password": VALID_PASSWORD,
                "confirm_password": VALID_PASSWORD,
            },
        )
        assert response.status_code == 201
        assert response.json() == {"received": True}
    app.dependency_overrides.clear()

    stored = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "fulano@souuni.com").one()
    assert stored.name == "Nome Real No Ixc"
    assert stored.cpf == VALID_CPF_DIGITS


def test_submit_uses_client_phone_correction_over_ixc_phone(db_session, monkeypatch):
    """Achado/pedido do usuário em 2026-08-29: se a pessoa não reconhece o telefone que o IXC
    devolveu (cadastro desatualizado), ela pode corrigir - o telefone que o cliente manda
    explicitamente tem prioridade sobre o do IXC (diferente do nome, que nunca é sobrescrito)."""
    fake = FakeFuncionariosClient([_funcionario(name="Nome Real No Ixc", phone="69911112222")])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post(
            "/api/access-requests",
            json={
                "cpf": VALID_CPF,
                "email": "corrigido@souuni.com",
                "phone": "(69) 98888-7777",
                "new_password": VALID_PASSWORD,
                "confirm_password": VALID_PASSWORD,
            },
        )
        assert response.status_code == 201
    app.dependency_overrides.clear()

    stored = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "corrigido@souuni.com").one()
    assert stored.name == "Nome Real No Ixc"  # nome continua do IXC
    assert stored.phone == "(69) 98888-7777"  # telefone é o que o cliente corrigiu, não o do IXC


def test_submit_uses_ixc_phone_when_client_omits_it(db_session, monkeypatch):
    """Fluxo normal (a pessoa confirma que o telefone do IXC está certo, sem corrigir nada) -
    continua usando o telefone do IXC."""
    fake = FakeFuncionariosClient([_funcionario(name="Nome Real No Ixc", phone="69911112222")])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post(
            "/api/access-requests",
            json={
                "cpf": VALID_CPF,
                "email": "confirmado@souuni.com",
                "new_password": VALID_PASSWORD,
                "confirm_password": VALID_PASSWORD,
            },
        )
        assert response.status_code == 201
    app.dependency_overrides.clear()

    stored = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "confirmado@souuni.com").one()
    assert stored.phone == "69911112222"


def test_submit_rejects_invalid_cpf_checksum(db_session, monkeypatch):
    fake = FakeFuncionariosClient([])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post("/api/access-requests", json={"cpf": "111.111.111-11", "email": "invalido@souuni.com"})
        assert response.status_code == 422
    app.dependency_overrides.clear()
    assert db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "invalido@souuni.com").first() is None


def test_submit_rejects_non_corporate_email(db_session, monkeypatch):
    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post("/api/access-requests", json={"cpf": VALID_CPF, "email": "fulano@gmail.com"})
        assert response.status_code == 422
    app.dependency_overrides.clear()
    assert db_session.query(PortalAccessRequest).filter(PortalAccessRequest.cpf == VALID_CPF_DIGITS).first() is None


def test_submit_falls_back_to_manual_name_phone_when_cpf_not_found_in_ixc(db_session, monkeypatch):
    """CPF não encontrado no IXC (cadastro ainda não sincronizado) - preserva a capacidade
    original de preencher nome/telefone manualmente, pra não regredir esse caso."""
    fake = FakeFuncionariosClient([])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post(
            "/api/access-requests",
            json={
                "cpf": VALID_CPF,
                "email": "manual@souuni.com",
                "name": "Preenchido A Mao",
                "phone": "69977776666",
                "new_password": VALID_PASSWORD,
                "confirm_password": VALID_PASSWORD,
            },
        )
        assert response.status_code == 201
    app.dependency_overrides.clear()

    stored = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "manual@souuni.com").one()
    assert stored.name == "Preenchido A Mao"
    assert stored.phone == "69977776666"


def test_submit_requires_manual_name_phone_when_not_found_and_missing(db_session, monkeypatch):
    fake = FakeFuncionariosClient([])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post(
            "/api/access-requests",
            json={
                "cpf": VALID_CPF,
                "email": "semdados@souuni.com",
                "new_password": VALID_PASSWORD,
                "confirm_password": VALID_PASSWORD,
            },
        )
        assert response.status_code == 422
    app.dependency_overrides.clear()
    assert db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "semdados@souuni.com").first() is None


def test_submit_suggests_matching_collaborator_by_cpf(db_session, make_collaborator, monkeypatch):
    collaborator = make_collaborator(name="Colaborador Com Cpf")
    collaborator.cpf = VALID_CPF_DIGITS
    db_session.flush()
    db_session.commit()

    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post(
            "/api/access-requests",
            json={
                "cpf": VALID_CPF,
                "email": "com.cpf@souuni.com",
                "new_password": VALID_PASSWORD,
                "confirm_password": VALID_PASSWORD,
            },
        )
        assert response.status_code == 201
    app.dependency_overrides.clear()

    stored = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "com.cpf@souuni.com").one()
    assert stored.suggested_collaborator_id == collaborator.id


def test_submit_prioritizes_ixc_employee_id_match_over_conflicting_cpf(db_session, make_collaborator, monkeypatch):
    """Prioridade exigida: `ixc_employee_id` > CPF > nome (`find_local_collaborator`). O
    colaborador local já está vinculado ao `ixc_employee_id` do funcionário encontrado, mas tem um
    CPF diferente cadastrado (cadastro legado) - a sugestão precisa seguir o vínculo mais forte
    (ixc_employee_id), não o CPF."""
    collaborator = make_collaborator(name="Vinculado Por Ixc Id")
    collaborator.ixc_employee_id = 1  # mesmo "id" devolvido por `_funcionario()`
    collaborator.cpf = OTHER_VALID_CPF_DIGITS  # propositalmente diferente do CPF da solicitação
    db_session.flush()
    db_session.commit()

    fake = FakeFuncionariosClient([_funcionario(cpf=VALID_CPF_DIGITS)])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post(
            "/api/access-requests",
            json={
                "cpf": VALID_CPF,
                "email": "ixc.id@souuni.com",
                "new_password": VALID_PASSWORD,
                "confirm_password": VALID_PASSWORD,
            },
        )
        assert response.status_code == 201
    app.dependency_overrides.clear()

    stored = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "ixc.id@souuni.com").one()
    assert stored.suggested_collaborator_id == collaborator.id


def test_submit_falls_back_to_name_match_when_no_ixc_id_or_cpf_match(db_session, make_collaborator, monkeypatch):
    """Terceira prioridade: nome normalizado, só quando ninguém bate por `ixc_employee_id` nem
    CPF - e só entra em jogo porque o nome vem do IXC (confirmado), não do cliente."""
    collaborator = make_collaborator(name="Fulano Funcionario")  # mesmo nome de `_funcionario()`

    fake = FakeFuncionariosClient([_funcionario(name="Fulano Funcionario")])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post(
            "/api/access-requests",
            json={
                "cpf": VALID_CPF,
                "email": "por.nome@souuni.com",
                "new_password": VALID_PASSWORD,
                "confirm_password": VALID_PASSWORD,
            },
        )
        assert response.status_code == 201
    app.dependency_overrides.clear()

    stored = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "por.nome@souuni.com").one()
    assert stored.suggested_collaborator_id == collaborator.id


def test_submit_without_matching_collaborator_has_no_suggestion(db_session, monkeypatch):
    fake = FakeFuncionariosClient([_funcionario(cpf=OTHER_VALID_CPF_DIGITS)])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post(
            "/api/access-requests",
            json={
                "cpf": "111.444.777-35",
                "email": "sem.colaborador@souuni.com",
                "new_password": VALID_PASSWORD,
                "confirm_password": VALID_PASSWORD,
            },
        )
        assert response.status_code == 201
    app.dependency_overrides.clear()

    stored = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "sem.colaborador@souuni.com").one()
    assert stored.suggested_collaborator_id is None


def test_submit_stores_password_hash_not_plaintext(db_session, monkeypatch):
    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post(
            "/api/access-requests",
            json={"cpf": VALID_CPF, "email": "com.senha@souuni.com", "new_password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD},
        )
        assert response.status_code == 201
        assert VALID_PASSWORD not in response.text
    app.dependency_overrides.clear()

    stored = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "com.senha@souuni.com").one()
    assert stored.password_hash is not None
    assert stored.password_hash != VALID_PASSWORD
    assert verify_password(VALID_PASSWORD, stored.password_hash)


def test_submit_rejects_password_confirmation_mismatch(db_session, monkeypatch):
    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post(
            "/api/access-requests",
            json={"cpf": VALID_CPF, "email": "senha.diferente@souuni.com", "new_password": VALID_PASSWORD, "confirm_password": "OutraSenha123"},
        )
        assert response.status_code == 422
    app.dependency_overrides.clear()
    assert db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "senha.diferente@souuni.com").first() is None


def test_submit_rejects_password_shorter_than_minimum(db_session, monkeypatch):
    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        response = client.post(
            "/api/access-requests",
            json={"cpf": VALID_CPF, "email": "senha.curta@souuni.com", "new_password": "curta", "confirm_password": "curta"},
        )
        assert response.status_code == 422
    app.dependency_overrides.clear()
    assert db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "senha.curta@souuni.com").first() is None


def test_duplicate_pending_submission_updates_instead_of_creating_new_row(db_session, monkeypatch):
    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        first = client.post(
            "/api/access-requests",
            json={"cpf": VALID_CPF, "email": "primeiro@souuni.com", "new_password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD},
        )
        assert first.status_code == 201
        second = client.post(
            "/api/access-requests",
            json={"cpf": VALID_CPF, "email": "segundo@souuni.com", "new_password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD},
        )
        assert second.status_code == 201
        assert second.json() == {"received": True}  # mesma resposta genérica, sem diferenciar
    app.dependency_overrides.clear()

    matching = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.cpf == VALID_CPF_DIGITS).all()
    assert len(matching) == 1
    assert matching[0].email == "segundo@souuni.com"  # atualizado, não duplicado


def test_non_admin_cannot_list_or_decide_requests(db_session):
    from app.core.security import hash_password

    non_admin = User(name="Sem Permissao", email="sem.permissao.acesso@pytest.local", role="viewer", active=True, password_hash=hash_password("Qualquer123"))
    db_session.add(non_admin)
    db_session.commit()

    with _admin_client(db_session, non_admin) as client:
        assert client.get("/api/access-requests").status_code == 403
        assert client.post("/api/access-requests/1/approve", json={"collaborator_id": 1}).status_code == 403
        assert client.post("/api/access-requests/1/reject", json={"decision_reason": "x"}).status_code == 403
    app.dependency_overrides.clear()


def test_admin_lists_requests_with_masked_cpf(db_session, admin_user, monkeypatch):
    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        client.post(
            "/api/access-requests",
            json={"cpf": VALID_CPF, "email": "listagem@souuni.com", "new_password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD},
        )
    app.dependency_overrides.clear()

    with _admin_client(db_session, admin_user) as client:
        response = client.get("/api/access-requests")
        assert response.status_code == 200
        item = next(i for i in response.json() if i["email"] == "listagem@souuni.com")
        assert item["cpf_masked"] == "***.***.***-25"
        assert "cpf" not in item
        assert "password_hash" not in item
        assert VALID_PASSWORD not in response.text
    app.dependency_overrides.clear()


def test_approve_creates_user_directly_with_submitted_password(db_session, make_collaborator, admin_user, monkeypatch):
    """2026-08-29: aprovar não gera mais convite - cria a conta direto, com a senha que a própria
    pessoa já escolheu ao solicitar."""
    collaborator = make_collaborator(name="Aprovado Direto")

    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        client.post(
            "/api/access-requests",
            json={"cpf": VALID_CPF, "email": "aprovado@souuni.com", "new_password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD},
        )
    app.dependency_overrides.clear()

    request_row = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "aprovado@souuni.com").one()

    with _admin_client(db_session, admin_user) as client:
        response = client.post(f"/api/access-requests/{request_row.id}/approve", json={"collaborator_id": collaborator.id})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "approved"
        assert "invite_token" not in body
        assert VALID_PASSWORD not in response.text
    app.dependency_overrides.clear()

    db_session.refresh(request_row)
    assert request_row.status == "approved"
    assert request_row.reviewed_by_user_id == admin_user.id
    assert request_row.password_hash is None  # limpo após uso, não fica retido à toa

    assert db_session.query(AccountActionToken).filter(AccountActionToken.email == "aprovado@souuni.com").first() is None

    user = db_session.query(User).filter(User.email == "aprovado@souuni.com").one()
    assert user.collaborator_id == collaborator.id
    assert user.role == "collaborator"
    assert user.active is True
    assert user.must_change_password is False
    assert user.first_access_completed_at is None
    assert verify_password(VALID_PASSWORD, user.password_hash)


def test_approved_user_can_login_to_portal_with_submitted_password(db_session, make_collaborator, admin_user, monkeypatch):
    """Fim a fim: depois de aprovado, o colaborador consegue logar com o e-mail e a senha que
    definiu no formulário - sem nenhum passo extra (sem convite/link)."""
    collaborator = make_collaborator(name="Login Depois De Aprovar")

    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        client.post(
            "/api/access-requests",
            json={"cpf": VALID_CPF, "email": "login.aprovado@souuni.com", "new_password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD},
        )
    app.dependency_overrides.clear()

    request_row = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "login.aprovado@souuni.com").one()

    with _admin_client(db_session, admin_user) as client:
        approve = client.post(f"/api/access-requests/{request_row.id}/approve", json={"collaborator_id": collaborator.id})
        assert approve.status_code == 200
    app.dependency_overrides.clear()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"email": "login.aprovado@souuni.com", "password": VALID_PASSWORD})
        assert login.status_code == 200
        assert login.json()["user"]["email"] == "login.aprovado@souuni.com"
    app.dependency_overrides.clear()


def test_approve_requires_collaborator_id_even_with_suggestion(db_session, make_collaborator, admin_user, monkeypatch):
    collaborator = make_collaborator(name="Sugestao Ignorada")
    collaborator.cpf = VALID_CPF_DIGITS
    db_session.flush()
    db_session.commit()

    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        client.post(
            "/api/access-requests",
            json={"cpf": VALID_CPF, "email": "sugestao@souuni.com", "new_password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD},
        )
    app.dependency_overrides.clear()

    request_row = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "sugestao@souuni.com").one()
    assert request_row.suggested_collaborator_id == collaborator.id

    with _admin_client(db_session, admin_user) as client:
        response = client.post(f"/api/access-requests/{request_row.id}/approve", json={})
        assert response.status_code == 422
    app.dependency_overrides.clear()

    assert db_session.query(User).filter(User.email == "sugestao@souuni.com").first() is None


def test_approve_rejects_legacy_request_without_password(db_session, make_collaborator, admin_user, monkeypatch):
    """Solicitação criada antes de `password_hash` existir (2026-08-29) - nunca cria conta sem
    senha; a aprovação recusa com um erro claro em vez de improvisar."""
    collaborator = make_collaborator(name="Sem Senha Legado")

    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        client.post(
            "/api/access-requests",
            json={"cpf": VALID_CPF, "email": "legado@souuni.com", "new_password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD},
        )
    app.dependency_overrides.clear()

    request_row = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "legado@souuni.com").one()
    request_row.password_hash = None  # simula uma solicitação anterior à coluna existir
    db_session.commit()

    with _admin_client(db_session, admin_user) as client:
        response = client.post(f"/api/access-requests/{request_row.id}/approve", json={"collaborator_id": collaborator.id})
        assert response.status_code == 422
    app.dependency_overrides.clear()

    assert db_session.query(User).filter(User.email == "legado@souuni.com").first() is None


def test_approve_rejects_collaborator_already_linked(db_session, make_collaborator, admin_user, monkeypatch):
    collaborator = make_collaborator(name="Ja Vinculado")
    from app.core.security import hash_password

    db_session.add(User(name="Existente", email="ja.tem.usuario@souuni.com", role="collaborator", active=True, password_hash=hash_password("Outra123456"), collaborator_id=collaborator.id))
    db_session.commit()

    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        client.post(
            "/api/access-requests",
            json={"cpf": VALID_CPF, "email": "duplicado@souuni.com", "new_password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD},
        )
    app.dependency_overrides.clear()

    request_row = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "duplicado@souuni.com").one()

    with _admin_client(db_session, admin_user) as client:
        response = client.post(f"/api/access-requests/{request_row.id}/approve", json={"collaborator_id": collaborator.id})
        assert response.status_code == 409
    app.dependency_overrides.clear()


def test_approve_already_decided_request_is_rejected(db_session, make_collaborator, admin_user, monkeypatch):
    collaborator = make_collaborator(name="Ja Decidido")

    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        client.post(
            "/api/access-requests",
            json={"cpf": VALID_CPF, "email": "ja.decidido@souuni.com", "new_password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD},
        )
    app.dependency_overrides.clear()

    request_row = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "ja.decidido@souuni.com").one()

    with _admin_client(db_session, admin_user) as client:
        first = client.post(f"/api/access-requests/{request_row.id}/approve", json={"collaborator_id": collaborator.id})
        assert first.status_code == 200
        second = client.post(f"/api/access-requests/{request_row.id}/approve", json={"collaborator_id": collaborator.id})
        assert second.status_code == 409
    app.dependency_overrides.clear()


def test_reject_requires_decision_reason_and_sets_status(db_session, admin_user, monkeypatch):
    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        client.post(
            "/api/access-requests",
            json={"cpf": VALID_CPF, "email": "rejeitado@souuni.com", "new_password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD},
        )
    app.dependency_overrides.clear()

    request_row = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "rejeitado@souuni.com").one()

    with _admin_client(db_session, admin_user) as client:
        missing_reason = client.post(f"/api/access-requests/{request_row.id}/reject", json={"decision_reason": ""})
        assert missing_reason.status_code == 422

        response = client.post(f"/api/access-requests/{request_row.id}/reject", json={"decision_reason": "CPF não corresponde a nenhum colaborador ativo."})
        assert response.status_code == 200
        assert response.json()["status"] == "rejected"
    app.dependency_overrides.clear()

    db_session.refresh(request_row)
    assert request_row.status == "rejected"
    assert request_row.decision_reason == "CPF não corresponde a nenhum colaborador ativo."
    assert request_row.password_hash is None  # limpo ao decidir, não fica retido à toa


def test_reject_already_decided_request_is_rejected(db_session, admin_user, monkeypatch):
    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        client.post(
            "/api/access-requests",
            json={"cpf": VALID_CPF, "email": "duplo.reject@souuni.com", "new_password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD},
        )
    app.dependency_overrides.clear()

    request_row = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "duplo.reject@souuni.com").one()

    with _admin_client(db_session, admin_user) as client:
        first = client.post(f"/api/access-requests/{request_row.id}/reject", json={"decision_reason": "Motivo qualquer."})
        assert first.status_code == 200
        second = client.post(f"/api/access-requests/{request_row.id}/reject", json={"decision_reason": "Outro motivo."})
        assert second.status_code == 409
    app.dependency_overrides.clear()


def test_audit_log_never_stores_full_cpf_or_password(db_session, make_collaborator, admin_user, monkeypatch):
    collaborator = make_collaborator(name="Auditoria Acesso")

    fake = FakeFuncionariosClient([_funcionario()])
    with _public_client(db_session, fake, monkeypatch) as client:
        client.post(
            "/api/access-requests",
            json={"cpf": VALID_CPF, "email": "auditoria.acesso@souuni.com", "new_password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD},
        )
    app.dependency_overrides.clear()

    request_row = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "auditoria.acesso@souuni.com").one()

    with _admin_client(db_session, admin_user) as client:
        client.post(f"/api/access-requests/{request_row.id}/approve", json={"collaborator_id": collaborator.id})
    app.dependency_overrides.clear()

    entries = db_session.query(AuditLog).filter(AuditLog.entity.in_(["portal_access_request", "users"])).all()
    payload = "".join(str(entry.before_data) + str(entry.after_data) for entry in entries)
    assert VALID_CPF_DIGITS not in payload
    assert VALID_PASSWORD not in payload
    user = db_session.query(User).filter(User.email == "auditoria.acesso@souuni.com").one()
    assert user.password_hash not in payload


def test_audit_log_records_phone_source(db_session, monkeypatch):
    """`phone_source` no log ajuda o admin a saber, sem CPF/telefone nenhum, se o número veio do
    IXC ou foi corrigido pela própria pessoa."""
    fake_confirmed = FakeFuncionariosClient([_funcionario(cpf=VALID_CPF_DIGITS)])
    with _public_client(db_session, fake_confirmed, monkeypatch) as client:
        response = client.post(
            "/api/access-requests",
            json={"cpf": VALID_CPF, "email": "fonte.ixc@souuni.com", "new_password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD},
        )
        assert response.status_code == 201
    app.dependency_overrides.clear()

    fake_corrected = FakeFuncionariosClient([_funcionario(cpf=OTHER_VALID_CPF_DIGITS)])
    with _public_client(db_session, fake_corrected, monkeypatch) as client:
        response = client.post(
            "/api/access-requests",
            json={
                "cpf": "111.444.777-35",
                "email": "fonte.corrigida@souuni.com",
                "phone": "(69) 97777-6666",
                "new_password": VALID_PASSWORD,
                "confirm_password": VALID_PASSWORD,
            },
        )
        assert response.status_code == 201
    app.dependency_overrides.clear()

    confirmed_request = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "fonte.ixc@souuni.com").one()
    corrected_request = db_session.query(PortalAccessRequest).filter(PortalAccessRequest.email == "fonte.corrigida@souuni.com").one()

    confirmed_entry = db_session.query(AuditLog).filter(
        AuditLog.action == "portal_access_request.created", AuditLog.entity_id == str(confirmed_request.id)
    ).one()
    corrected_entry = db_session.query(AuditLog).filter(
        AuditLog.action == "portal_access_request.created", AuditLog.entity_id == str(corrected_request.id)
    ).one()

    assert confirmed_entry.after_data["phone_source"] == "ixc"
    assert corrected_entry.after_data["phone_source"] == "manual"
