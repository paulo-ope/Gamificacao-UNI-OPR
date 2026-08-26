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
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    first_imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
