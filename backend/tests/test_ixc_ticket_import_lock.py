"""Achado real em produção (2026-09-11): o primeiro ciclo da sincronização automática deixou o
advisory lock do Postgres preso pra sempre (`pg_locks` mostrava a conexão "idle" com o lock ainda
concedido, destravado manualmente via `pg_terminate_backend`). Causa: um erro de banco dentro do
`with _ticket_import_lock(db)` deixa a sessão "precisando de rollback" - chamar `db.execute`
direto no `finally` (código antigo) levanta `PendingRollbackError`, mascarando o erro original E
matando o `pg_advisory_unlock` antes de rodar. Este teste prova que o `rollback()` defensivo no
`finally` evita esse vazamento, usando um fake que simula exatamente essa sessão poluída."""

from __future__ import annotations

import pytest

from app.modules.support.ixc_ticket_ingestion import _ticket_import_lock


class _FakeDialect:
    name = "postgresql"


class _FakeBind:
    dialect = _FakeDialect()


class _PoisonedSession:
    """Simula uma sessão que já sofreu um erro de banco: a PRIMEIRA chamada de `execute` depois
    do rollback (a tentativa de unlock, se não houver rollback antes) levantaria
    `PendingRollbackError` de verdade - aqui simplificado para qualquer `execute` sem rollback
    prévio explodir, e voltar a funcionar normalmente depois de `rollback()`."""

    def __init__(self):
        self.rolled_back = False
        self.unlock_calls = 0
        self.lock_calls = 0

    def get_bind(self):
        return _FakeBind()

    def execute(self, statement, params=None):
        text_sql = str(statement)
        if "pg_try_advisory_lock" in text_sql:
            self.lock_calls += 1
            return type("Result", (), {"scalar": lambda self: True})()
        if "pg_advisory_unlock" in text_sql:
            if not self.rolled_back:
                raise RuntimeError("PendingRollbackError simulado - sessão precisa de rollback antes")
            self.unlock_calls += 1
            return None
        raise AssertionError(f"execute inesperado: {text_sql}")

    def rollback(self):
        self.rolled_back = True


def test_lock_is_released_even_when_body_raises_a_db_error():
    session = _PoisonedSession()

    with pytest.raises(ValueError, match="erro de banco simulado"):
        with _ticket_import_lock(session):
            raise ValueError("erro de banco simulado")

    assert session.unlock_calls == 1, "o unlock deveria ter sido chamado depois do rollback defensivo"


def test_lock_is_released_on_success_path_too():
    session = _PoisonedSession()
    session.rolled_back = True  # sessão limpa (caminho feliz, sem erro pendente)

    with _ticket_import_lock(session):
        pass

    assert session.unlock_calls == 1
