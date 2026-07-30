"""Modelos do módulo de Agendamento.

Espelho LOCAL dos eventos de agendamento do IXC (`su_oss_chamado_mensagem`), sincronizado de forma
incremental - a consulta ao vivo de um mês inteiro leva 2-3 minutos na API do IXC, inviável para um
painel com filtros interativos. Com o dado local, todo KPI vira SQL instantâneo (decisão registrada
em docs/estudo-kpis-agendamento.md, seção 4.1).

Duas tabelas de fato + um cadastro:
- `scheduling_orders`: uma linha por O.S. dos setores sincronizados (dimensões para filtro + datas
  derivadas que os KPIs usam direto, como `first_scheduled_at`).
- `scheduling_events`: uma linha por evento do log do IXC (Abertura/Agendamento/Reagendar/
  Fechamento), com o instante da INTERAÇÃO do operador (`event_at`) separado da janela combinada
  com o cliente (`window_start`) - a distinção que motivou a reescrita da métrica.
- `scheduling_operators`: cadastro de quem compõe a equipe do setor (decisão do dono do produto:
  a meta diária só vale para membros marcados, não para qualquer usuário que apareça no log).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models import utc_now

# Eventos de `su_oss_evento` que o sync espelha. O restante (Alteração, Em Análise etc.) não
# alimenta nenhum KPI do módulo e ficaria como peso morto no banco.
SYNCED_EVENT_TYPES = ("1", "5", "10", "6")  # Abertura, Agendamento, Reagendar, Fechamento


class SchedulingOrder(Base):
    __tablename__ = "scheduling_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ixc_os_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    setor_id: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    setor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    filial_id: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    assunto_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    assunto_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    status: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    # Derivados na sincronização para os KPIs não precisarem de subquery por O.S.:
    # primeiro evento 5 (resposta do setor) e a janela combinada desse primeiro agendamento.
    first_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    first_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_operator_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Técnico de campo designado no primeiro agendamento - distinto do operador (quem marcou a
    # agenda). Preenchido só quando a O.S. já foi agendada ao menos uma vez.
    first_technician_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    schedule_event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SchedulingEvent(Base):
    __tablename__ = "scheduling_events"
    __table_args__ = (UniqueConstraint("ixc_message_id", name="uq_scheduling_events_message"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ixc_message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ixc_os_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    # Instante em que o operador interagiu (campo `data` do IXC) - a base de TODA métrica de tempo
    # de resposta. NÃO confundir com window_start (`data_inicio`), que é a janela combinada com o
    # cliente e só alimenta o KPI de antecedência da agenda.
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    operator_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    technician_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Texto livre que o colaborador digitou ao registrar o evento (`mensagem` no IXC) e a nota
    # automática gerada pelo sistema (`historico`, ex.: "Usuário X reagendou a O.S. ..."). Nenhum dos
    # dois vira KPI - é só contexto qualitativo pro log completo da O.S. (pedido do dono do produto).
    mensagem: Mapped[str | None] = mapped_column(Text, nullable=True)
    historico: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SchedulingOperator(Base):
    __tablename__ = "scheduling_operators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ixc_user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    # Membro formal da equipe de agendamento: só estes entram na cobrança de meta diária. Os demais
    # operadores continuam aparecendo nos números (o evento aconteceu), mas sem régua de meta.
    is_team_member: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SchedulingTechnician(Base):
    """Cache de nomes de técnicos de campo (`funcionarios` no IXC, referenciados via `id_tecnico`)
    - espaço de ID diferente de `SchedulingOperator` (`usuarios`), por isso tabela própria."""

    __tablename__ = "scheduling_technicians"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ixc_funcionario_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SchedulingSavedFilter(Base):
    """Visão salva de filtros do dashboard (mesmo conceito de `OperationSavedFilter` do módulo
    Operação Analítica - pedido do dono do produto pra unificar o padrão entre os dois módulos).
    Guarda só o RECORTE (filial/setor/assunto/operador/contagem), nunca o período - a data em tela
    é sempre preservada ao aplicar uma visão."""

    __tablename__ = "scheduling_saved_filters"
    __table_args__ = (UniqueConstraint("user_id", "name", "visibility", name="uq_scheduling_saved_filters_user_name_visibility"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    filters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="personal", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
