"""Sobe o backend LOCAL isolado, para testar fluxos de conta (ex.: esqueci minha senha) sem tocar em
nada real: banco SQLite descartável, todas as sincronizações externas (IXC/OPA/CPK/agendamento)
desligadas e e-mail desligado - o corpo do e-mail (com o código de 6 dígitos) aparece no console.

Uso (a partir da pasta `backend`):
    ..\\.venv\\Scripts\\python scripts\\run_local.py

Variáveis opcionais: LOCAL_TEST_EMAIL (padrão operacional@souuni.com), LOCAL_PORT (padrão 8000).
Apague o arquivo `.local-reset-test.db` para recomeçar do zero.
"""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BACKEND_DIR / ".local-reset-test.db"

# Atribuição direta (não setdefault): o `.env` da raiz pode ter IXC_SYNC_ENABLED=true e credenciais
# reais, e um teste local nunca pode sincronizar com sistemas de produção.
os.environ.update(
    {
        "APP_ENV": "development",
        "DATABASE_URL": f"sqlite:///{DB_PATH.as_posix()}",
        "AUTH_SECRET_KEY": "local-only-secret-not-for-production-0123456789",
        "FRONTEND_URL": "http://localhost:3001",
        "EMAIL_ENABLED": "false",
        "IXC_SYNC_ENABLED": "false",
        # URL local que recusa conexão, de propósito: rotas públicas (ex.: solicitar acesso) criam o
        # cliente IXC antes de qualquer coisa e quebram com 500 se a URL estiver vazia. Assim a consulta
        # falha rápido (IxcApiError) e o fluxo segue pelo caminho manual, sem nunca tocar no IXC real.
        "IXC_API_BASE_URL": "http://127.0.0.1:9",
        "IXC_API_TOKEN": "local-test-dummy",
        "OPA_SYNC_ENABLED": "false",
        "OPA_API_BASE_URL": "",
        "OPA_API_TOKEN": "",
        "SCHEDULING_SYNC_ENABLED": "false",
        "CPK_API_BASE_URL": "",
        "CPK_API_KEY": "",
        "AUTO_SEED": "false",
        "INITIAL_ADMIN_EMAIL": "",
        "INITIAL_ADMIN_PASSWORD": "",
    }
)
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)  # evita que um `.env` de outra pasta seja lido por engano


def prepare_database(email: str) -> None:
    from sqlalchemy import select

    import app.main  # noqa: F401 - registra os models de TODOS os módulos antes do create_all
    from app.core.security import hash_password
    from app.db.base import Base
    from app.db.session import SessionLocal, engine
    from app.models import User

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            return
        # Senha aleatória descartada de propósito: o teste é justamente redefini-la pelo código.
        db.add(User(name="Usuário Teste Local", email=email, role="viewer", active=True, password_hash=hash_password(secrets.token_urlsafe(16))))
        db.commit()
        print(f"[local] usuário de teste criado: {email}")


if __name__ == "__main__":
    import uvicorn

    prepare_database(os.environ.get("LOCAL_TEST_EMAIL", "operacional@souuni.com").strip().lower())
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("LOCAL_PORT", "8000")), log_level="info")
