from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


OPERATIONAL_MEMBER_STATUSES = (
    "pending_validation",
    "validated_operation",
    "outside_operation",
    "without_supervisor",
    "without_team_model",
    "active_management",
    "conflict",
    "inactive",
)

MANAGEMENT_CASE_STATUSES = (
    "pending",
    "justified",
    "in_progress",
    "resolved",
    "rejected",
    "overdue",
)

# Estados em que o caso ainda cobra ação de alguém.
OPEN_CASE_STATUSES = ("pending", "justified", "in_progress")

# Encerramentos - só a matriz (`management:review`) chega neles.
CLOSED_CASE_STATUSES = ("resolved", "rejected")

# Para onde o supervisor pode mover o caso ao justificar.
JUSTIFY_TARGET_STATUSES = ("justified", "in_progress")

# Para onde a matriz pode mover o caso ao revisar. `in_progress` permite devolver o caso ao
# supervisor pedindo complemento, sem ter que rejeitar de vez.
REVIEW_TARGET_STATUSES = ("resolved", "rejected", "in_progress")

# `overdue` nunca é gravado: é derivado de `due_date` na leitura (ver cases.is_overdue). Gravar
# exigiria varredura periódica, que ficaria errada entre execuções.


class ManagementOperationalMember(Base):
    __tablename__ = "management_operational_members"
    __table_args__ = (
        UniqueConstraint("responsible_name", "regional", name="uq_management_member_name_regional"),
        Index("ix_management_member_supervisor_status", "supervisor_user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collaborator_id: Mapped[int | None] = mapped_column(ForeignKey("collaborators.id", ondelete="SET NULL"), nullable=True, index=True)
    ixc_employee_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    responsible_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    regional: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    supervisor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    team_model_id: Mapped[int | None] = mapped_column(ForeignKey("operations_team_models.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending_validation", index=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="operations", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_order_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    validated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    supervisor = relationship("User", foreign_keys=[supervisor_user_id])
    collaborator = relationship("Collaborator")
    team_model = relationship("OperationTeamModel")


class ManagementCaseReason(Base):
    __tablename__ = "management_case_reasons"
    __table_args__ = (UniqueConstraint("name", name="uq_management_case_reason_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(140), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    requires_description: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class ManagementCase(Base):
    __tablename__ = "management_cases"
    __table_args__ = (
        Index("ix_management_case_status_severity", "status", "severity"),
        Index("ix_management_case_period_regional", "reference_year", "reference_month", "regional"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    source_module: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    reference_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    reference_month: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    reference_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    regional: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    collaborator_id: Mapped[int | None] = mapped_column(ForeignKey("collaborators.id", ondelete="SET NULL"), nullable=True, index=True)
    responsible_name: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    supervisor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    team_model_id: Mapped[int | None] = mapped_column(ForeignKey("operations_team_models.id", ondelete="SET NULL"), nullable=True, index=True)
    metric_name: Mapped[str] = mapped_column(String(120), nullable=False)
    expected_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    deviation_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium", index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    reason_id: Mapped[int | None] = mapped_column(ForeignKey("management_case_reasons.id", ondelete="SET NULL"), nullable=True)
    justification_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    justified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reason = relationship("ManagementCaseReason")
    supervisor = relationship("User", foreign_keys=[supervisor_user_id])
    collaborator = relationship("Collaborator")
    team_model = relationship("OperationTeamModel")


class ManagementCaseComment(Base):
    __tablename__ = "management_case_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("management_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

