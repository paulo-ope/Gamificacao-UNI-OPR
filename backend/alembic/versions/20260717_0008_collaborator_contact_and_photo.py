"""add phone, email and profile photo columns to collaborators

Redesign do cadastro de colaborador pediu campos de contato (telefone/e-mail) e foto de perfil,
pra deixar o cadastro mais completo e o painel mais moderno (avatar de verdade em vez de só
iniciais). A foto é guardada como bytes direto no Postgres (BYTEA) - não existe nenhuma
infraestrutura de armazenamento de arquivo neste projeto (sem volume Docker dedicado, sem
serving estático), e o volume de colaboradores é pequeno o bastante (algumas centenas, uma foto
pequena cada) pra isso ser simples e seguro, sem precisar resolver storage externo nem servir
imagem sem autenticação (toda rota aqui exige Bearer token, o que uma tag <img src> não consegue
mandar - o front busca a foto como blob autenticado, igual já faz pro preview de PDF).

Revision ID: 20260717_0008
Revises: 20260715_0007
Create Date: 2026-07-17 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260717_0008"
down_revision = "20260715_0007"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "collaborators" not in _table_names():
        return
    op.add_column("collaborators", sa.Column("phone", sa.String(40), nullable=True))
    op.add_column("collaborators", sa.Column("email", sa.String(160), nullable=True))
    op.add_column("collaborators", sa.Column("photo", sa.LargeBinary(), nullable=True))
    op.add_column("collaborators", sa.Column("photo_content_type", sa.String(60), nullable=True))


def downgrade() -> None:
    if "collaborators" not in _table_names():
        return
    op.drop_column("collaborators", "photo_content_type")
    op.drop_column("collaborators", "photo")
    op.drop_column("collaborators", "email")
    op.drop_column("collaborators", "phone")
