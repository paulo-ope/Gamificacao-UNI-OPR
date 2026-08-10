"""Bootstrap do usuário de serviço da IA e emissão de chave de API.

Uso: docker exec opr-gamification-backend python -m app.modules.ai.cli create-service-user
[--name "Claude.ai MCP"]

Não existe (ainda) uma tela de administração para isso - hoje é só uma chave, então um comando
único cobre o caso real sem construir uma API de gestão de chaves para um problema que não existe.
"""

from __future__ import annotations

import argparse
import secrets

from app.core.security import hash_api_key, hash_password
from app.db.session import SessionLocal
from app.models import User
from app.modules.ai.auth import API_KEY_PREFIX_LENGTH
from app.modules.ai.models import ApiKeyCredential

SERVICE_USER_EMAIL = "ai-service@internal.souuni.com"
SERVICE_USER_NAME = "Serviço de IA"


def create_service_user_and_key(name: str) -> str:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == SERVICE_USER_EMAIL).one_or_none()
        if not user:
            # password_hash nunca é usado para login por senha deste usuário (é uma identidade de
            # máquina) - só precisa ser um valor que não seja texto puro, mesmo esquema de sempre.
            user = User(
                name=SERVICE_USER_NAME,
                email=SERVICE_USER_EMAIL,
                password_hash=hash_password(secrets.token_urlsafe(32)),
                role="ai_service",
                active=True,
            )
            db.add(user)
            db.flush()

        raw_key = secrets.token_urlsafe(32)
        db.add(
            ApiKeyCredential(
                user_id=user.id,
                name=name,
                key_prefix=raw_key[:API_KEY_PREFIX_LENGTH],
                key_hash=hash_api_key(raw_key),
            )
        )
        db.commit()
        return raw_key
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser(
        "create-service-user",
        help="Cria (se preciso) o usuário de serviço e emite uma nova chave de API.",
    )
    create_parser.add_argument(
        "--name",
        default="Claude.ai MCP",
        help="Rótulo da chave, para identificar qual integração a usa (ex.: 'Claude.ai MCP').",
    )

    args = parser.parse_args()
    if args.command == "create-service-user":
        raw_key = create_service_user_and_key(name=args.name)
        print("Chave de API gerada - copie agora, ela não será mostrada de novo:")
        print(raw_key)


if __name__ == "__main__":
    main()
