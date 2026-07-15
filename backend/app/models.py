from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


LEADERSHIP_PERCENTAGE_BY_ROLE: dict[str, float] = {
    "supervisor": 10.0,
    "regional_manager": 7.5,
    "portfolio_manager": 5.0,
}

CALCULATION_RUN_STATUSES = ("draft", "review", "approved", "paid", "cancelled")


def default_percentage_for_role(role_type: str | None) -> float:
    return float(LEADERSHIP_PERCENTAGE_BY_ROLE.get((role_type or "").strip(), 0.0))


def default_percentage_for_role_context(context) -> float:
    return default_percentage_for_role(context.get_current_parameters().get("role_type"))


class Collaborator(Base):
    __tablename__ = "collaborators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(120), nullable=False)
    regional: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_registered: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    service_orders: Mapped[list["ServiceOrder"]] = relationship(back_populates="collaborator")
    scores: Mapped[list["CollaboratorScore"]] = relationship(back_populates="collaborator")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="viewer", nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")
    import_runs: Mapped[list["ImportRun"]] = relationship(back_populates="imported_by_user")
    import_service_order_audits: Mapped[list["ImportServiceOrderAudit"]] = relationship(back_populates="created_by_user")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    entity: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    before_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    user: Mapped[User | None] = relationship(back_populates="audit_logs")


class ServiceOrder(Base):
    __tablename__ = "service_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    os_code: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    contract_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    customer_login: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    customer_name: Mapped[str] = mapped_column(String(180), nullable=False)
    collaborator_id: Mapped[int] = mapped_column(ForeignKey("collaborators.id"), nullable=False)
    regional: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    os_type: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    os_subject: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    diagnosis: Mapped[str] = mapped_column(String(180), default="Não informado", index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(80), default="Concluída", nullable=False)
    sla_status: Mapped[str] = mapped_column(String(80), default="Dentro do prazo", nullable=False)
    sla_hours: Mapped[float | None] = mapped_column(Float, default=24, nullable=True)
    closing_time_hours: Mapped[float | None] = mapped_column(Float, default=0, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_warranty: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_recurrence: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_priority: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_reschedule: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_pending: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    collaborator: Mapped["Collaborator"] = relationship(back_populates="service_orders")
    import_audits: Mapped[list["ImportServiceOrderAudit"]] = relationship(back_populates="service_order")


class ScoringGroup(Base):
    __tablename__ = "scoring_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_points: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    point_value_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=True)

    rules: Mapped[list["ScoringRule"]] = relationship(back_populates="group")
    subject_rules: Mapped[list["ScoringSubjectRule"]] = relationship(back_populates="group")


class ScoringSubjectRule(Base):
    __tablename__ = "scoring_subject_rules"
    __table_args__ = (UniqueConstraint("os_type", "os_subject", name="uq_scoring_subject_rule_subject"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("scoring_groups.id"), nullable=False)
    os_type: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    os_subject: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    subject_category: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    custom_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    point_value_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    use_group_default: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=True)

    group: Mapped["ScoringGroup"] = relationship(back_populates="subject_rules")


class ScoringRule(Base):
    __tablename__ = "scoring_rules"
    __table_args__ = (UniqueConstraint("group_id", "os_type", "os_subject", name="uq_scoring_rule_subject"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("scoring_groups.id"), nullable=False)
    os_type: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    os_subject: Mapped[str | None] = mapped_column(String(180), index=True, nullable=True)
    points: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    group: Mapped["ScoringGroup"] = relationship(back_populates="rules")


class PenaltyRule(Base):
    __tablename__ = "penalty_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    penalty_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    points: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    calculation_mode: Mapped[str] = mapped_column(String(80), default="fixed", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DiagnosisPenaltyRule(Base):
    __tablename__ = "diagnosis_penalty_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    diagnosis_name: Mapped[str] = mapped_column(String(180), unique=True, index=True, nullable=False)
    penalty_points: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    force_points_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    action_type: Mapped[str] = mapped_column(String(40), default="no_penalty", index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=True)


class SlaPenaltyRule(Base):
    __tablename__ = "sla_penalty_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    condition_type: Mapped[str] = mapped_column(String(80), default="status_sla_out_of_time", index=True, nullable=False)
    penalty_type: Mapped[str] = mapped_column(String(80), default="none", index=True, nullable=False)
    penalty_value: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=True)


class RecurrenceClassificationRule(Base):
    __tablename__ = "recurrence_classification_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    os_type_pattern: Mapped[str | None] = mapped_column(String(160), nullable=True)
    os_subject_pattern: Mapped[str | None] = mapped_column(String(220), nullable=True)
    diagnosis_pattern: Mapped[str | None] = mapped_column(String(220), nullable=True)
    original_os_type_pattern: Mapped[str | None] = mapped_column(String(160), nullable=True)
    original_os_subject_pattern: Mapped[str | None] = mapped_column(String(220), nullable=True)
    return_os_type_pattern: Mapped[str | None] = mapped_column(String(160), nullable=True)
    return_os_subject_pattern: Mapped[str | None] = mapped_column(String(220), nullable=True)
    return_diagnosis_pattern: Mapped[str | None] = mapped_column(String(220), nullable=True)
    ignore_diagnosis_pattern: Mapped[str | None] = mapped_column(String(220), nullable=True)
    classification: Mapped[str] = mapped_column(String(60), default="nao_identificado", index=True, nullable=False)
    discount_points: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    require_same_subject: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    require_same_diagnosis: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=True)


class GamificationConfigVersion(Base):
    __tablename__ = "gamification_config_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), default="gamification_rules_config", nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class HealthRule(Base):
    __tablename__ = "health_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    min_sla: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    max_recurrence_rate: Mapped[float] = mapped_column(Float, default=100, nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, default=1, nullable=False)
    condition_operator: Mapped[str] = mapped_column(String(20), default="and", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CalculationRun(Base):
    __tablename__ = "calculation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    reference_month: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_year: Mapped[int] = mapped_column(Integer, nullable=False)
    regional: Mapped[str | None] = mapped_column(String(120), nullable=True)
    point_value: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    source_import_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rules_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    executed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    scores: Mapped[list["CollaboratorScore"]] = relationship(
        back_populates="calculation_run",
        cascade="all, delete-orphan",
    )


class CollaboratorScore(Base):
    __tablename__ = "collaborator_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    calculation_run_id: Mapped[int] = mapped_column(ForeignKey("calculation_runs.id"), nullable=False)
    collaborator_id: Mapped[int] = mapped_column(ForeignKey("collaborators.id"), nullable=False)
    service_orders_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gross_points: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    penalty_points: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    net_points: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    health_multiplier: Mapped[float] = mapped_column(Float, default=1, nullable=False)
    health_status: Mapped[str] = mapped_column(String(120), default="Boa", nullable=False)
    final_points: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    estimated_payment: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    balance_adjustment_points: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    balance_after: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    calculation_run: Mapped["CalculationRun"] = relationship(back_populates="scores")
    collaborator: Mapped["Collaborator"] = relationship(back_populates="scores")


class CollaboratorPointBalance(Base):
    """Saldo corrente (rolling) de pontos de garantia por colaborador."""

    __tablename__ = "collaborator_point_balances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("collaborators.id"), unique=True, nullable=False, index=True
    )
    balance_points: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    collaborator: Mapped["Collaborator"] = relationship()


POINT_BALANCE_ENTRY_TYPES = ("post_payment_warranty_debit", "period_settlement", "manual_adjustment")
POINT_BALANCE_ENTRY_STATUSES = ("pending", "applied", "reverted")


class PointBalanceEntry(Base):
    """Lançamento (ledger) de cada movimentação no saldo de pontos de um colaborador."""

    __tablename__ = "point_balance_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    collaborator_id: Mapped[int] = mapped_column(ForeignKey("collaborators.id"), nullable=False, index=True)
    entry_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    points: Mapped[float] = mapped_column(Float, nullable=False)

    original_service_order_id: Mapped[int | None] = mapped_column(ForeignKey("service_orders.id"), nullable=True)
    related_service_order_id: Mapped[int | None] = mapped_column(ForeignKey("service_orders.id"), nullable=True)
    # Guarda o os_code (estavel entre reimportacoes) alem do FK: apagar/reimportar o periodo troca o id
    # interno da O.S, mas o os_code sobrevive - preserva a identidade do lancamento e a deteccao de
    # duplicidade mesmo depois que a O.S original for apagada e reimportada.
    original_os_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    related_os_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    origin_calculation_run_id: Mapped[int | None] = mapped_column(ForeignKey("calculation_runs.id"), nullable=True)

    applied_calculation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("calculation_runs.id"), nullable=True, index=True
    )
    applied_reference_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applied_reference_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    recurrence_classification: Mapped[str | None] = mapped_column(String(60), nullable=True)
    recurrence_action: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    collaborator: Mapped["Collaborator"] = relationship()
    original_service_order: Mapped["ServiceOrder | None"] = relationship(foreign_keys=[original_service_order_id])
    related_service_order: Mapped["ServiceOrder | None"] = relationship(foreign_keys=[related_service_order_id])
    origin_calculation_run: Mapped["CalculationRun | None"] = relationship(foreign_keys=[origin_calculation_run_id])
    applied_calculation_run: Mapped["CalculationRun | None"] = relationship(foreign_keys=[applied_calculation_run_id])


class LeadershipProfile(Base):
    __tablename__ = "leadership_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    role_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    percentage: Mapped[float] = mapped_column(Float, default=default_percentage_for_role_context, nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, default=1, nullable=False)
    role_profile_id: Mapped[int | None] = mapped_column(ForeignKey("leadership_role_profiles.id"), nullable=True, index=True)
    use_custom_multiplier: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    custom_multiplier: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_source: Mapped[str] = mapped_column(String(40), default="collaborators", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    collaborator_id: Mapped[int | None] = mapped_column(ForeignKey("collaborators.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    role_profile: Mapped["LeadershipRoleProfile | None"] = relationship(back_populates="leaders")
    regionals: Mapped[list["LeadershipProfileRegional"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )
    bonus_results: Mapped[list["LeadershipBonusResult"]] = relationship(back_populates="profile")


class LeadershipProfileRegional(Base):
    __tablename__ = "leadership_profile_regionals"
    __table_args__ = (UniqueConstraint("leadership_profile_id", "regional_name", name="uq_leadership_profile_regional"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    leadership_profile_id: Mapped[int] = mapped_column(ForeignKey("leadership_profiles.id"), nullable=False, index=True)
    regional_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    profile: Mapped["LeadershipProfile"] = relationship(back_populates="regionals")


class LeadershipRoleProfile(Base):
    __tablename__ = "leadership_role_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    default_multiplier: Mapped[float] = mapped_column(Float, default=1, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    leaders: Mapped[list["LeadershipProfile"]] = relationship(back_populates="role_profile")


class LeadershipBonusResult(Base):
    __tablename__ = "leadership_bonus_results"
    __table_args__ = (UniqueConstraint("calculation_run_id", "leadership_profile_id", name="uq_leadership_bonus_run_profile"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    calculation_run_id: Mapped[int] = mapped_column(ForeignKey("calculation_runs.id"), nullable=False, index=True)
    leadership_profile_id: Mapped[int] = mapped_column(ForeignKey("leadership_profiles.id"), nullable=False, index=True)
    role_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, default=1, nullable=False)
    average_final_points: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    scoped_collaborators: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    point_value: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    base_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    bonus_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    regionals_snapshot: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    profile: Mapped["LeadershipProfile"] = relationship(back_populates="bonus_results")


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ImportRun(Base):
    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(120), default="upvalue", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="completed", nullable=False, index=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    imported_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    missing_date_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unknown_collaborator_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    required_field_missing_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paid_period_blocked_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ignored_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    imported_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_columns: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    mapped_columns: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    errors: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    imported_by_user: Mapped["User | None"] = relationship(back_populates="import_runs")
    audits: Mapped[list["ImportServiceOrderAudit"]] = relationship(
        back_populates="import_run",
        cascade="all, delete-orphan",
    )


class ImportServiceOrderAudit(Base):
    __tablename__ = "import_service_order_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    import_run_id: Mapped[int] = mapped_column(ForeignKey("imports.id"), nullable=False, index=True)
    os_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    service_order_id: Mapped[int | None] = mapped_column(ForeignKey("service_orders.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    field_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)

    import_run: Mapped["ImportRun"] = relationship(back_populates="audits")
    service_order: Mapped["ServiceOrder | None"] = relationship(back_populates="import_audits")
    created_by_user: Mapped["User | None"] = relationship(back_populates="import_service_order_audits")
