"""Modelo do módulo UNI Localiza.

Uma linha por solicitação de localização: o atendente gera um link de uso único para o cliente
compartilhar a posição atual por GPS. `token_hash` guarda um SHA-256 simples do token (não
`hash_password`/pbkdf2 como `AccountActionToken`) de propósito - o volume esperado aqui (uma
solicitação por atendimento, potencialmente muitas por dia) é bem maior que o de convites, e o
token já tem 256 bits de entropia própria (não depende de custo de hash para resistir a força
bruta). Um hash simples e INDEXADO permite localizar o token em O(1); o padrão de
`portal_invites._find_pending_invite_by_token` (iterar candidatos com `verify_password`) não
escalaria aqui.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models import User, utc_now


class LocationRequest(Base):
    __tablename__ = "location_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Identificador curto e não sequencial para exibição ao atendente (referência da solicitação
    # fora do link público) - o `id` interno nunca é exposto fora do backend/autenticação.
    public_id: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # Nullable de propósito: o link de localização costuma ser enviado ANTES de existir O.S. no
    # IXC (o atendente ainda está coletando a posição para abrir o atendimento). `attach_order_code`
    # (service.py) preenche este campo depois, quando a O.S. já existe. `opa_protocol` é o
    # identificador disponível nesse momento inicial (atendimento já aberto no OPA Suite).
    order_code: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    opa_protocol: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(180), nullable=True)

    # pending | confirmed | invalidated. "expired" nunca é gravado aqui - é sempre CALCULADO a
    # partir de expires_at (mesmo padrão de `portal_invites._display_status`), para uma leitura
    # nunca ter efeito colateral de escrita.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)

    registered_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    registered_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    gps_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    confirmed_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    confirmed_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    adjusted_manually: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    distance_from_registered_meters: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Hash truncado (nunca o IP em claro) - só para correlação/abuso, sem valor de identificação
    # direta. Ver `service._hash_ip`.
    created_ip_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confirmed_ip_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    # Só para exibir "solicitado por" na consulta interna (pedido do usuário) - nunca usado pra
    # regra de negócio nem exposto na API pública.
    created_by_user: Mapped[User | None] = relationship(foreign_keys=[created_by_user_id])

    # Primeira vez que o link público foi aberto com sucesso (token válido, ainda pendente) -
    # usado só para não repetir o evento de auditoria LINK_OPENED a cada consulta de status.
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
