from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SupportOpaImportRun(Base):
    __tablename__ = "support_opa_import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="opa", index=True)
    entity: Mapped[str] = mapped_column(String(80), nullable=False, default="attendance", index=True)
    mode: Mapped[str] = mapped_column(String(40), nullable=False, default="manual", index=True)
    date_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    date_to: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="running", index=True)
    page_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    pages_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_skip: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    checkpoint_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    imported_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SupportOpaAttendanceRaw(Base):
    __tablename__ = "support_opa_attendances_raw"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_support_opa_attendances_raw_source_id"),
        Index("ix_support_opa_raw_opened_closed", "opened_at", "closed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SupportOpaDimension(Base):
    __tablename__ = "support_opa_dimensions"
    __table_args__ = (
        UniqueConstraint("dimension_type", "source_id", name="uq_support_opa_dimensions_type_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dimension_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(220), nullable=True, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SupportOpaAttendantOverride(Base):
    """Cadastro manual de classificação de atendente do OPA Suite — hoje usado só
    pra forçar `attendant_type="bot"` (via `classification="virtual_agent"`) quando
    a dimensão sincronizada da API (`SupportOpaDimension.payload_json.tipo`) não
    reflete isso, seja porque o OPA nunca mandou `tipo="bot"` pra aquele atendente,
    seja porque o atendente nem chegou a ser sincronizado como dimensão. Tem
    prioridade sobre `payload_json.tipo` — ver `opa_attendant_overrides.resolve_attendant_type`.
    """

    __tablename__ = "support_opa_attendant_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attendant_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    attendant_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    classification: Mapped[str] = mapped_column(String(40), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SupportOpaSavedFilter(Base):
    """Recorte de filtros salvo da tela /suporte.

    `scope` separa dois usos que o usuario pediu explicitamente como coisas
    diferentes:
      - "personal": so aparece para quem criou, mas sincroniza entre dispositivos
        (diferente do atalho de localStorage, que morre com o navegador).
      - "global": aparece para todo mundo que enxerga o modulo, para recortes
        oficiais da operacao.
    Editar/apagar um filtro global exige a mesma permissao de gestao do modulo -
    ver o router; qualquer usuario pode criar e apagar os proprios "personal".

    `filters_json` guarda o recorte cru (mesmas chaves da querystring da tela).
    Deliberadamente sem FK para colunas de filtro: se uma etiqueta/atendente sumir
    do OPA, o filtro salvo continua abrindo e simplesmente nao casa nada, em vez de
    quebrar a tela inteira.
    """

    __tablename__ = "support_opa_saved_filters"
    __table_args__ = (
        Index("ix_support_opa_saved_filters_scope_owner", "scope", "owner_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="personal")
    filters_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class SupportOpaAttendance(Base):
    __tablename__ = "support_opa_attendances"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_support_opa_attendances_source_id"),
        Index("ix_support_opa_attendances_opened_closed", "opened_at", "closed_at"),
        Index("ix_support_opa_attendances_attendant_reason", "attendant_name", "reason_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    protocol: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(220), nullable=True)
    attendant_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    attendant_name: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    department_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    department_name: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    reason_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    reason_name: Mapped[str | None] = mapped_column(String(220), nullable=True, index=True)
    channel: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    channel_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    channel_customer: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    tma_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tmr_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # TMR geral: mesmo cálculo do tmr_seconds, mas conta resposta de QUALQUER
    # atendente (bot ou humano) como resposta válida — pensado pra comparar
    # com painéis que não distinguem bot de humano no TMR. tmr_seconds
    # continua sendo o TMR só-humano, não foi alterado.
    tmr_all_responses_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Nullable de propósito: NULL = atendimento ainda não classificado (histórico
    # anterior à Fase 2, ou mensagens indisponíveis) — nunca tratar como False.
    # Ver opa_ingestion._classify_bot_human.
    handled_by_bot: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reached_human: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    bot_to_human_handoff: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Resumo mínimo de handoff a partir das MESMAS mensagens já buscadas pro TMR
    # (zero chamada extra à API do OPA Suite) — existe só pra preparar uma
    # comparação futura contra o painel oficial do OPA (divergência de contagem
    # documentada em docs/roteiro-comparacao-tmr-opa-suite.md, seção 10.3), NÃO
    # altera tmr_seconds/tmr_all_responses_seconds/handled_by_bot/reached_human/
    # bot_to_human_handoff, que continuam calculados exatamente como antes.
    # NULL = mensagens indisponíveis ou atendimento sem resposta humana
    # classificável — nunca tratar como "sem handoff".
    distinct_human_attendant_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    first_human_attendant_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_human_attendant_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    human_message_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bot_message_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_message_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Etiquetas do atendimento projetadas do `raw_payload` (`tags[].id_tag`) numa
    # string delimitada — ex.: ",id1,id2,". Existe porque etiqueta é a única
    # dimensão de filtro que o OPA só entrega dentro do JSON: filtrar direto no
    # payload (`json_array_elements`) medido em ~410 ms por query no volume real,
    # inviável numa tela que dispara ~8 agregações por carga. Sempre gravado com
    # separador nas duas pontas pra que `LIKE '%,id,%'` não case com um id que
    # apenas contenha outro como prefixo/sufixo. NULL = atendimento importado
    # antes desta coluna existir e ainda não reprojetado; string vazia com
    # separadores (",") = atendimento sem nenhuma etiqueta, que é diferente.
    tag_ids_text: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    first_imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
