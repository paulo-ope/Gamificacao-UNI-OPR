import os
from datetime import datetime, timezone

os.environ.setdefault("AUTH_SECRET_KEY", "pytest-only-not-for-production")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.ai_governance.bootstrap import ensure_ai_governance_seed
from app.models import (
    AppSetting,
    Collaborator,
    HealthRule,
    RecurrenceClassificationRule,
    ScoringGroup,
    ScoringSubjectRule,
    ServiceOrder,
    User,
)


@pytest.fixture()
def db_session():
    """Fresh, isolated in-memory SQLite database for a single test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        # Mesma inicialização que `main.py:lifespan` roda em produção (ensure_ai_governance_seed) -
        # sem isso, toda rota que passa pelo gate de `ai_governance` nega tudo por padrão (nenhum
        # AiEndpoint/AiFieldPermission cadastrado), diferente do sistema real já inicializado.
        ensure_ai_governance_seed(session)
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def _bind_opa_ingestion_session_local(request, monkeypatch):
    """`opa_ingestion.py` abre sessões próprias e curtas (`SessionLocal()`) pra
    commitar o status da run de importação OPA sem depender do commit/rollback do
    chamador (ver `_create_running_import_run`/`_persist_run_terminal_status`). Em
    produção isso aponta pro mesmo engine de sempre; em teste, `app.db.session.engine`
    é um banco `:memory:` GLOBAL e diferente do engine isolado por teste que
    `db_session` cria — sem este bind, `SessionLocal()` dentro de `opa_ingestion.py`
    escreveria num banco que o teste nunca enxerga. Só ativa quando o teste usa
    `db_session`, igual ao padrão já usado manualmente em `test_opa_scheduler.py`."""
    if "db_session" not in request.fixturenames:
        return
    session = request.getfixturevalue("db_session")
    from app.modules.support import opa_ingestion as opa_ingestion_module

    class _SessionLocalStub:
        def __call__(self):
            return self

        def __enter__(self):
            return session

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(opa_ingestion_module, "SessionLocal", _SessionLocalStub())


@pytest.fixture()
def admin_user(db_session):
    admin = User(name="Admin", email="admin@pytest.local", role="admin", active=True, password_hash="x")
    db_session.add(admin)
    db_session.flush()
    return admin


@pytest.fixture()
def client(db_session, admin_user):
    """FastAPI TestClient wired to the test's db_session and an authenticated admin."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def make_collaborator(db_session):
    def _make(name="Colaborador Teste", regional="UNI SUL", role="Tecnico", registered=True):
        collaborator = Collaborator(name=name, role=role, regional=regional, active=True, is_registered=registered)
        db_session.add(collaborator)
        db_session.flush()
        return collaborator

    return _make


@pytest.fixture()
def make_service_order(db_session):
    counter = {"n": 0}

    def _make(collaborator, **overrides):
        counter["n"] += 1
        defaults = dict(
            os_code=f"OS-{counter['n']}",
            contract_id="C-1",
            customer_login="cliente1",
            customer_name="Cliente Um",
            collaborator_id=collaborator.id,
            regional=collaborator.regional,
            os_type="Manutencao",
            os_subject="Reparo",
            diagnosis="Falha",
            status="Concluida",
            sla_status="Dentro do prazo",
            opened_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
            closed_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
        )
        defaults.update(overrides)
        order = ServiceOrder(**defaults)
        db_session.add(order)
        db_session.flush()
        return order

    return _make


@pytest.fixture()
def scoring_setup(db_session):
    """Base scoring config: one group/rule (Manutencao/Reparo = 15 pts) + point value."""
    group = ScoringGroup(name="Manutencao", default_points=15.0, active=True)
    db_session.add(group)
    db_session.flush()
    db_session.add(
        ScoringSubjectRule(group_id=group.id, os_type="Manutencao", os_subject="Reparo", use_group_default=True, active=True)
    )
    db_session.add(HealthRule(name="Boa", min_sla=0, max_recurrence_rate=100, multiplier=1.0, active=True))
    db_session.add(AppSetting(key="point_value", value="2.00"))
    db_session.flush()
    return group


@pytest.fixture()
def recurrence_setup(db_session):
    """Recurrence classification config: 'garantia' discounts the original order's points."""
    db_session.add(
        RecurrenceClassificationRule(name="Garantia", classification="garantia", discount_points=True, active=True, priority=1, max_days=30)
    )
    db_session.add(AppSetting(key="recurrence_action", value="annul_original"))
    db_session.add(AppSetting(key="recurrence_window_days", value="30"))
    db_session.flush()
