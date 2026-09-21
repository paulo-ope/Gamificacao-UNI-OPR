"""Mapa de identidade de pessoa neste módulo (reorganização pedida pelo usuário em 2026-08-21,
plano em generic-riding-petal.md) - existem 4 representações da "mesma pessoa" no sistema, cada
uma com ciclo de vida e fonte de dado próprios; nenhuma foi fundida numa entidade só de propósito:

  Collaborator (app/models.py)               -> cadastro oficial da Gamificação (RH, foto,
                                                 supervisor, "regional de origem" - nunca usada em
                                                 regra de negócio aqui, só exibição).
  OperationIxcCollaborator (operations)       -> espelho do funcionário sincronizado do IXC
                                                 (fonte externa, read-only pra este módulo).
  OperationResponsibleAssignment (operations) -> cadastro manual responsável x regional x equipe,
                                                 mantido pela tela de Operação.
  ManagementOperationalMember (aqui)          -> visão do management: candidato + status de
                                                 validação/supervisor/escala. Populado por
                                                 `refresh_operational_members` (services.py) a
                                                 partir de `resolve_responsible_regional_candidates`
                                                 (operations/responsible_regional.py) - ESSA é a
                                                 fonte única de "regional operacional" hoje;
                                                 cadastro manual (OperationResponsibleAssignment)
                                                 tem prioridade sobre histórico de O.S.

Chave de casamento entre elas: nome normalizado (`cases._norm`, que delega em
`regional.normalize_key` - casefold, colapsa espaço E remove acento), mais `ixc_employee_id`
quando disponível - não há FK direta entre `ManagementOperationalMember` e
`OperationResponsibleAssignment`/`OperationOrder`. Uma pessoa pode ter mais de uma linha de
`ManagementOperationalMember` (uma por regional em que teve cadastro/atividade) - "regional
canônica de uma pessoa pelo nome" é resolvida por `cases.py:_resolve_member_for_case`, não por
uma FK única.

Achado real (2026-09-16): até aqui a normalização não removia acento ("José Souza"/"Jose Souza"
- variação real de digitação/importação do IXC entre lotes - viravam DUAS pessoas diferentes),
o que fazia casos de gestão/pendência de justificativa aparecerem sob uma identidade quando
deveriam estar sob a outra (falso positivo, falso negativo e pessoa errada, todos o mesmo
sintoma). Corrigido reaproveitando `regional.normalize_key` (já resolvia isso para nome de
regional) em vez de duplicar um algoritmo mais fraco; o filtro exato por nome em SQL usa
`cases.names_matching` (resolve a comparação em Python - `unicodedata` não roda em SQL)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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

# Escala de trabalho do colaborador - pedido do usuário em 2026-08-20: equipes 12x36 (trabalha um
# dia, folga no seguinte) tinham dia de folga tratado como "produção zero num dia esperado" pela
# geração automática de caso diário (achado real: gerava caso indevido no dia de folga). "standard"
# (default/None) é a régua atual - segunda a sexta (ou sábado/domingo com regra própria do modelo
# de equipe), sem folga alternada. "alternating" usa `shift_cycle_days_on`/`shift_cycle_days_off` a
# partir de `shift_anchor_date` (um dia CONHECIDO de trabalho) pra saber se um dia qualquer é de
# trabalho ou de folga - ver `cases.is_scheduled_workday`. Fica em `ManagementOperationalMember`
# (não em `OperationTeamModel`) porque dois colaboradores da MESMA equipe 12x36 costumam estar em
# fases opostas do ciclo (um trabalha enquanto o outro descansa, pra cobrir os dois dias).
MEMBER_SHIFT_PATTERNS = ("standard", "alternating")

# Nomes de OperationTeamModel.name elegiveis pra escala alternada - pedido do usuario em
# 2026-08-21: "alternating" (dia sim, dia nao) so faz sentido pra quem e 12x36; os demais modelos
# de equipe ja sao comercial (segunda a sabado, via OperationTeamTargetRule por modelo) e nao
# devem poder ligar a folga alternada. Casamento por NOME (nao ha campo proprio em
# OperationTeamModel pra marcar "e 12x36") - unico registro hoje e "TECNICO 12/36H"; se outro
# modelo 12x36 for cadastrado depois com nome diferente, precisa entrar neste set tambem.
ALTERNATING_SHIFT_ELIGIBLE_TEAM_MODEL_NAMES = frozenset({"TECNICO 12/36H"})


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
    # Escala 12x36/alternada - ver MEMBER_SHIFT_PATTERNS acima. `shift_pattern` nulo/"standard"
    # significa "sem folga alternada", os outros 3 campos ficam vazios.
    shift_pattern: Mapped[str | None] = mapped_column(String(20), nullable=True)
    shift_cycle_days_on: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shift_cycle_days_off: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shift_anchor_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    supervisor = relationship("User", foreign_keys=[supervisor_user_id])
    collaborator = relationship("Collaborator")
    team_model = relationship("OperationTeamModel")


GENERATION_EXCLUSION_SCOPES = ("member", "regional")


class ManagementCaseGenerationExclusion(Base):
    """Suspende a cobrança de caso (automática E manual, via `POST /cases/daily`/`/cases/monthly`)
    pra um colaborador específico (`member_id`, a linha de `ManagementOperationalMember` - não
    `Collaborator.id`, porque uma pessoa pode ter mais de uma linha, uma por regional, e a exclusão
    precisa valer só pra uma delas) ou pra uma regional inteira, num período opcional. Pedido do
    usuário em 2026-09-21: hoje só dava pra desligar a cobrança MUDANDO O MODELO DE EQUIPE inteiro
    (afeta todo mundo que usa aquele modelo) ou marcando o colaborador `outside_operation`/
    `inactive` (remove ele de tudo, não só da cobrança) - nenhuma das duas serve pra um caso
    pontual (férias, filial nova sem estrutura validada).

    `date_to` nulo = sem fim (exclusão permanente a partir de `date_from`). `date_from` nulo = sem
    início (vale desde sempre) - normalmente só faz sentido combinado com `date_to` nulo também
    (exclusão permanente sem data), mas a coluna permite os dois nulos por simplicidade de
    validação, não por caso de uso esperado.

    Nunca é apagada de verdade - só desativada (`active=False`) - histórico de "por que esse
    período não foi cobrado" é auditoria, igual ao resto do módulo."""

    __tablename__ = "management_case_generation_exclusions"
    __table_args__ = (
        CheckConstraint(
            "(scope_type = 'member' AND member_id IS NOT NULL AND regional IS NULL) OR "
            "(scope_type = 'regional' AND regional IS NOT NULL AND member_id IS NULL)",
            name="ck_management_case_generation_exclusion_scope",
        ),
        CheckConstraint(
            "date_from IS NULL OR date_to IS NULL OR date_from <= date_to",
            name="ck_management_case_generation_exclusion_date_range",
        ),
        Index("ix_management_case_generation_exclusion_member", "member_id"),
        Index("ix_management_case_generation_exclusion_regional", "regional"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    member_id: Mapped[int | None] = mapped_column(
        ForeignKey("management_operational_members.id", ondelete="CASCADE"), nullable=True
    )
    regional: Mapped[str | None] = mapped_column(String(160), nullable=True)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    member = relationship("ManagementOperationalMember")
    created_by_user = relationship("User", foreign_keys=[created_by])


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

