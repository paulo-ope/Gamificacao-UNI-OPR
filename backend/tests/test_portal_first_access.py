"""Fase 1 do primeiro acesso obrigatório do colaborador no Portal (pedido do usuário em
2026-08-28): antes de ver ranking, O.S., auditoria ou qualquer dado financeiro/operacional
individual, o colaborador precisa confirmar CPF/telefone/e-mail e trocar a senha uma vez.

`52998224725` e `11144477735` são CPFs de teste com dígito verificador válido (checksum real,
não sequência aleatória) - `is_valid_cpf` rejeita qualquer sequência de 11 dígitos que não bata a
conta, então um CPF "qualquer" não serve pra testar o caminho de sucesso.
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.security import get_current_user, verify_password
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, User
from app.services.documents import is_valid_cpf

VALID_CPF = "529.982.247-25"
VALID_CPF_DIGITS = "52998224725"
OTHER_VALID_CPF = "111.444.777-35"


def _client_for(db_session, user: User) -> TestClient:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _pending_user(db_session, collaborator, **overrides) -> User:
    defaults = dict(
        name=collaborator.name,
        email=f"{collaborator.name.lower().replace(' ', '.')}@login.local",
        role="collaborator",
        active=True,
        password_hash="x",
        collaborator_id=collaborator.id,
        must_change_password=True,
        first_access_completed_at=None,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    db_session.commit()
    return user


def test_is_valid_cpf_rejects_checksum_and_repeated_sequences():
    """Base do resto dos testes: sem isso, um CPF "qualquer" de 11 dígitos passaria."""
    assert is_valid_cpf(VALID_CPF) is True
    assert is_valid_cpf("111.111.111-11") is False
    assert is_valid_cpf("529.982.247-99") is False
    assert is_valid_cpf("123") is False
    assert is_valid_cpf(None) is False


def test_pending_first_access_blocks_portal_data_endpoints(db_session, make_collaborator):
    """O achado central da Fase 1: colaborador com primeiro acesso pendente não acessa dado
    financeiro/operacional nenhum, em nenhuma das rotas listadas explicitamente no pedido."""
    collaborator = make_collaborator(name="Pendente Teste")
    user = _pending_user(db_session, collaborator)

    with _client_for(db_session, user) as client:
        for path in ("/api/portal/summary", "/api/portal/my-orders", "/api/portal/my-audit", "/api/portal/simulation"):
            response = client.get(path)
            assert response.status_code == 403, f"{path} deveria bloquear com primeiro acesso pendente"
            assert "primeiro acesso" in response.json()["detail"].lower()
    app.dependency_overrides.clear()


def test_first_access_status_and_complete_remain_reachable_while_pending(db_session, make_collaborator):
    """As duas rotas de onboarding são a exceção deliberada ao bloqueio - senão ninguém pendente
    conseguiria completar o próprio primeiro acesso."""
    collaborator = make_collaborator(name="Consulta Status")
    user = _pending_user(db_session, collaborator)

    with _client_for(db_session, user) as client:
        status = client.get("/api/portal/first-access/status")
        assert status.status_code == 200
        assert status.json()["required"] is True
    app.dependency_overrides.clear()


def test_collaborator_completes_first_access_with_matching_cpf(db_session, make_collaborator):
    """CPF já cadastrado (veio do RH/importação) + colaborador digita o MESMO CPF -> confirma,
    não sobrescreve, e libera o acesso."""
    collaborator = make_collaborator(name="Ja Tem Cpf")
    collaborator.cpf = VALID_CPF_DIGITS
    db_session.flush()
    user = _pending_user(db_session, collaborator)

    with _client_for(db_session, user) as client:
        response = client.post(
            "/api/portal/first-access/complete",
            json={
                "cpf": VALID_CPF,
                "phone": "(69) 99999-0001",
                "email": "novo.contato@exemplo.com",
                "new_password": "SenhaForte123",
                "confirm_password": "SenhaForte123",
            },
        )
        assert response.status_code == 200
        assert response.json()["required"] is False

        # Liberado de verdade: a mesma sessão agora acessa dado financeiro sem 403.
        summary = client.get("/api/portal/summary")
        assert summary.status_code == 200
    app.dependency_overrides.clear()

    db_session.refresh(user)
    db_session.refresh(collaborator)
    assert user.must_change_password is False
    assert user.first_access_completed_at is not None
    assert user.password_changed_at is not None
    assert verify_password("SenhaForte123", user.password_hash) is True
    assert collaborator.cpf == VALID_CPF_DIGITS  # confirmado, não trocado
    assert collaborator.phone == "(69) 99999-0001"
    assert collaborator.email == "novo.contato@exemplo.com"


def test_collaborator_without_cpf_saves_it_on_first_access(db_session, make_collaborator):
    """Colaborador sem CPF cadastrado ainda (caso comum de quem entrou antes do RH digitar) ->
    o primeiro acesso é quem grava o CPF pela primeira vez."""
    collaborator = make_collaborator(name="Sem Cpf Ainda")
    assert collaborator.cpf is None
    user = _pending_user(db_session, collaborator)

    with _client_for(db_session, user) as client:
        response = client.post(
            "/api/portal/first-access/complete",
            json={
                "cpf": VALID_CPF,
                "phone": "(69) 99999-0002",
                "email": "sem.cpf@exemplo.com",
                "new_password": "OutraSenha123",
                "confirm_password": "OutraSenha123",
            },
        )
        assert response.status_code == 200
    app.dependency_overrides.clear()

    db_session.refresh(collaborator)
    assert collaborator.cpf == VALID_CPF_DIGITS


def test_mismatched_cpf_is_rejected_and_nothing_changes(db_session, make_collaborator):
    """CPF já cadastrado E diferente do digitado -> recusa (409), sem confirmar identidade errada
    nem deixar a pessoa passar."""
    collaborator = make_collaborator(name="Cpf Diferente")
    collaborator.cpf = VALID_CPF_DIGITS
    db_session.flush()
    user = _pending_user(db_session, collaborator)

    with _client_for(db_session, user) as client:
        response = client.post(
            "/api/portal/first-access/complete",
            json={
                "cpf": OTHER_VALID_CPF,
                "phone": "(69) 99999-0003",
                "email": "divergente@exemplo.com",
                "new_password": "SenhaValida123",
                "confirm_password": "SenhaValida123",
            },
        )
        assert response.status_code == 409
    app.dependency_overrides.clear()

    db_session.refresh(user)
    db_session.refresh(collaborator)
    assert collaborator.cpf == VALID_CPF_DIGITS  # não mudou
    assert user.first_access_completed_at is None  # continua pendente
    assert user.must_change_password is True


def test_password_and_confirmation_mismatch_is_rejected(db_session, make_collaborator):
    collaborator = make_collaborator(name="Senha Diferente")
    user = _pending_user(db_session, collaborator)

    with _client_for(db_session, user) as client:
        response = client.post(
            "/api/portal/first-access/complete",
            json={
                "cpf": VALID_CPF,
                "phone": "(69) 99999-0004",
                "email": "senha.diferente@exemplo.com",
                "new_password": "SenhaValida123",
                "confirm_password": "OutraCoisa456",
            },
        )
        assert response.status_code == 422
    app.dependency_overrides.clear()

    db_session.refresh(user)
    assert user.first_access_completed_at is None


def test_weak_password_is_rejected(db_session, make_collaborator):
    """Não existia política de senha no projeto antes desta feature - o mínimo de 8 caracteres é
    a política nova, introduzida especificamente pra esta troca de senha obrigatória."""
    collaborator = make_collaborator(name="Senha Fraca")
    user = _pending_user(db_session, collaborator)

    with _client_for(db_session, user) as client:
        response = client.post(
            "/api/portal/first-access/complete",
            json={
                "cpf": VALID_CPF,
                "phone": "(69) 99999-0005",
                "email": "senha.fraca@exemplo.com",
                "new_password": "123",
                "confirm_password": "123",
            },
        )
        assert response.status_code == 422
    app.dependency_overrides.clear()

    db_session.refresh(user)
    assert user.first_access_completed_at is None


def test_invalid_cpf_checksum_is_rejected(db_session, make_collaborator):
    collaborator = make_collaborator(name="Cpf Invalido")
    user = _pending_user(db_session, collaborator)

    with _client_for(db_session, user) as client:
        response = client.post(
            "/api/portal/first-access/complete",
            json={
                "cpf": "111.111.111-11",
                "phone": "(69) 99999-0006",
                "email": "cpf.invalido@exemplo.com",
                "new_password": "SenhaValida123",
                "confirm_password": "SenhaValida123",
            },
        )
        assert response.status_code == 422
    app.dependency_overrides.clear()


def test_internal_admin_user_is_never_blocked_by_first_access(db_session, admin_user):
    """Usuário interno (sem `collaborator_id`) não representa uma pessoa física cadastrada como
    colaborador - o primeiro acesso não se aplica a ele, mesmo sem nunca ter passado pelo fluxo."""
    assert admin_user.collaborator_id is None
    assert admin_user.first_access_completed_at is None  # nunca setado, e não deveria bloquear

    with _client_for(db_session, admin_user) as client:
        response = client.get("/api/portal/overview")
        assert response.status_code == 200
    app.dependency_overrides.clear()


def test_audit_log_never_stores_full_cpf_or_password(db_session, make_collaborator):
    collaborator = make_collaborator(name="Auditoria Segura")
    user = _pending_user(db_session, collaborator)

    with _client_for(db_session, user) as client:
        response = client.post(
            "/api/portal/first-access/complete",
            json={
                "cpf": VALID_CPF,
                "phone": "(69) 99999-0007",
                "email": "auditoria@exemplo.com",
                "new_password": "SenhaSecreta123",
                "confirm_password": "SenhaSecreta123",
            },
        )
        assert response.status_code == 200
    app.dependency_overrides.clear()

    entry = db_session.query(AuditLog).filter(AuditLog.action == "complete_first_access", AuditLog.entity_id == str(user.id)).one()
    payload = str(entry.before_data) + str(entry.after_data)
    assert VALID_CPF_DIGITS not in payload
    assert "SenhaSecreta123" not in payload


def test_new_collaborator_linked_user_is_created_pending(db_session, make_collaborator, admin_user):
    """`create_user` deve marcar `must_change_password=True` só quando o usuário novo já nasce
    vinculado a um colaborador - é a regra que fecha o ciclo: sem isso, colaborador novo entraria
    direto sem nunca passar pelo primeiro acesso."""
    collaborator = make_collaborator(name="Novo Vinculado")

    with _client_for(db_session, admin_user) as client:
        response = client.post(
            "/api/users",
            json={
                "name": "Novo Vinculado",
                "email": "novo.vinculado@exemplo.com",
                "password": "SenhaTemporaria123",
                "role": "collaborator",
                "collaborator_id": collaborator.id,
            },
        )
        assert response.status_code == 201
        assert response.json()["portal_first_access_required"] is True
    app.dependency_overrides.clear()

    created = db_session.query(User).filter(User.email == "novo.vinculado@exemplo.com").one()
    assert created.must_change_password is True
    assert created.first_access_completed_at is None


def test_pre_existing_user_backfilled_is_not_retroactively_blocked(db_session, make_collaborator):
    """Simula o efeito do backfill da migration 20260828_0081: usuário que já existia antes desta
    feature, com `first_access_completed_at` preenchido (equivalente ao `created_at` que o backfill
    usa), continua acessando o portal normalmente - não é bloqueado por uma feature que não
    existia quando a conta foi criada."""
    collaborator = make_collaborator(name="Usuario Antigo")
    user = _pending_user(
        db_session,
        collaborator,
        must_change_password=False,
        first_access_completed_at=datetime.now(timezone.utc),
    )

    with _client_for(db_session, user) as client:
        response = client.get("/api/portal/summary")
        assert response.status_code == 200
    app.dependency_overrides.clear()
