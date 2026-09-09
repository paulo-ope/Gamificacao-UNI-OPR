from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
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
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    cpf: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    employee_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    team_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    supervisor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    regional_manager_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    structure_status: Mapped[str] = mapped_column(String(40), default="pending_review", nullable=False, index=True)
    structure_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Vincula o colaborador ao id do funcionario/tecnico no IXC (su_rh_funcionarios / campo
    # id_tecnico nas O.S.). Usado para casar o mesmo colaborador entre a gamificacao e o modulo
    # de operacoes analiticas sem depender de comparacao de nome (nome pode divergir/ter typo).
    ixc_employee_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True, index=True)
    # Foto de perfil guardada como bytes direto no banco (sem infraestrutura de arquivo neste
    # projeto - ver docs/plano-integracao-ixc.md não se aplica aqui, decisão registrada na
    # migration 20260717_0008). `photo_content_type` (ex: "image/jpeg") é necessário pra servir
    # com o Content-Type correto - sem isso o navegador não sabe renderizar os bytes crus.
    photo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    photo_content_type: Mapped[str | None] = mapped_column(String(60), nullable=True)

    service_orders: Mapped[list["ServiceOrder"]] = relationship(back_populates="collaborator")
    scores: Mapped[list["CollaboratorScore"]] = relationship(back_populates="collaborator")
    portal_user: Mapped["User | None"] = relationship(
        back_populates="collaborator",
        foreign_keys="User.collaborator_id",
        uselist=False,
    )
    supervisor_user: Mapped["User | None"] = relationship(foreign_keys=[supervisor_user_id])
    regional_manager_user: Mapped["User | None"] = relationship(foreign_keys=[regional_manager_user_id])


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="viewer", nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Vínculo direto com o colaborador que este usuário representa no /portal - substitui a
    # heurística por nome/e-mail aproximado (achado real: sem vínculo direto, um usuário sem match
    # caía no fallback "primeiro colocado do ranking", vazando dados de outro colaborador).
    # Único (um colaborador só pode estar vinculado a um usuário) e nullable (nem todo usuário
    # representa um colaborador - admin/operator/viewer internos não precisam de vínculo).
    collaborator_id: Mapped[int | None] = mapped_column(ForeignKey("collaborators.id"), unique=True, nullable=True)
    # Vínculo por regional pro perfil "regional_manager_viewer" - esse usuário não representa UM
    # colaborador (não tem O.S própria), ele acompanha a equipe inteira de uma filial. Guardado como
    # texto livre (normalizado na leitura via services/regional.normalize_regional, igual toda outra
    # comparação de regional no sistema), não como FK - não existe uma tabela de "regional" própria.
    managed_regional: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Sucessor de managed_regional: permite um gestor regional cobrir várias filiais ao mesmo
    # tempo (mesmo caso de uso que LeadershipProfileRegional resolve pra líderes). Lista de texto
    # livre em JSON em vez de tabela filha própria - não há necessidade de join em SQL, é só lida
    # em Python depois do usuário já carregado. managed_regional (singular) fica só como legado de
    # leitura pra contas antigas ainda não migradas; toda escrita nova usa managed_regionals.
    managed_regionals: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Primeiro acesso obrigatório do colaborador (Fase 1) - `first_access_completed_at is None` é o
    # sinal canônico de "nunca completou"; `must_change_password` existe à parte pra permitir um
    # reset administrativo futuro (Fase 2: painel admin) sem mexer na data de conclusão original.
    # As duas condições bloqueiam por OR (ver `require_portal_access` em core/security.py) de
    # propósito - depender só de uma seria mais fácil de destravar por engano.
    # Default seguro (`False`/`None` sem forçar bloqueio): quem cria o usuário decide explicitamente
    # quando exigir o fluxo (ver `create_user` em api/routes/users.py) - contas existentes antes
    # desta feature são resolvidas por backfill na migration, nunca pelo default do modelo.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    first_access_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")
    import_runs: Mapped[list["ImportRun"]] = relationship(back_populates="imported_by_user")
    import_service_order_audits: Mapped[list["ImportServiceOrderAudit"]] = relationship(back_populates="created_by_user")
    collaborator: Mapped[Collaborator | None] = relationship(
        back_populates="portal_user",
        foreign_keys=[collaborator_id],
    )
    access_profiles: Mapped[list["AccessProfile"]] = relationship(
        secondary="user_access_profiles",
        back_populates="users",
    )
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user")


class Notification(Base):
    """Notificação in-app (sino no topo, sem integração externa) - avisa um usuário de algo que
    precisa da atenção dele, com um link pra abrir direto o que gerou o aviso. Genérica de
    propósito (entity_type/entity_id livres): a primeira origem é a Gestão Integrada (caso
    justificado, pronto pra decisão da matriz), mas outros eventos podem reaproveitar a mesma
    tabela sem precisar de uma nova por funcionalidade."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    link_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    user: Mapped[User] = relationship(back_populates="notifications")


class AccessProfile(Base):
    __tablename__ = "access_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    legacy_role: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    permissions: Mapped[list["AccessProfilePermission"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )
    users: Mapped[list[User]] = relationship(
        secondary="user_access_profiles",
        back_populates="access_profiles",
    )


class AccessProfilePermission(Base):
    __tablename__ = "access_profile_permissions"
    __table_args__ = (UniqueConstraint("profile_id", "permission", name="uq_access_profile_permission"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("access_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    profile: Mapped[AccessProfile] = relationship(back_populates="permissions")


class AccessProfilePermissionSeed(Base):
    """Registro de que uma permissão de perfil de sistema JÁ FOI semeada uma vez.

    Achado real (2026-09-09): `ensure_access_profiles` roda a cada start do backend e fazia
    `permissions - existing` -> `db.add(...)`, ou seja, só adicionava. Uma permissão removida na
    tela de Perfis de Acesso (ex.: tirar `management:review` do "Admin Ecossistema") voltava
    sozinha no próximo restart do container, sem aviso e sem registro de auditoria - na prática,
    permissão de perfil de sistema não era removível.

    Esta tabela separa "o admin removeu de propósito" de "esta instalação nunca viu esta
    permissão": a semeadura passa a acontecer UMA vez por (perfil de sistema, permissão). Assim a
    remoção fica de pé, e uma permissão nova que entre em `ROLE_PERMISSIONS` no futuro (módulo
    novo) continua chegando aos perfis existentes na primeira subida depois do deploy.

    A chave é `legacy_role` e não `profile_id` de propósito: sobrevive à exclusão do perfil, então
    perfil de sistema excluído pela tela também não é recriado no próximo start.
    """

    __tablename__ = "access_profile_permission_seeds"
    __table_args__ = (UniqueConstraint("legacy_role", "permission", name="uq_access_profile_permission_seed"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    legacy_role: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    seeded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class UserAccessProfile(Base):
    __tablename__ = "user_access_profiles"
    __table_args__ = (UniqueConstraint("user_id", "profile_id", name="uq_user_access_profile"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("access_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class CustomPermission(Base):
    """Permissão criada pela própria tela de Administração (aba Permissões), não declarada em código.

    O catálogo efetivo é a UNIÃO de `PERMISSION_LABELS` (app/core/security.py, permissões do
    sistema - as que as rotas do backend exigem) com as linhas desta tabela. A separação é o que
    permite excluir permissão pela tela sem risco: chave de código não é excluível (apagar o
    rótulo deixaria a rota inalcançável, sem aviso); chave criada aqui é.

    Uma permissão própria é um marcador de acesso concedível/revogável - ela aparece em
    `user.permissions` e pode ser lida por integração ou tela, mas não protege rota nenhuma do
    backend por si só, porque rota é código. Ver aba Permissões, que diz isso na tela.
    """

    __tablename__ = "custom_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Chave do módulo do registry a que a permissão pertence (só para agrupar na tela). Null =
    # "Outras permissões".
    module_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    # Mesmo significado de `SENSITIVE_PERMISSIONS`: fica fora do "Selecionar módulo" em lote.
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class WorkspaceModuleSetting(Base):
    """Ajuste do admin sobre um módulo declarado em código (`app/modules/registry.py`).

    Sobrepõe só o que é apresentação e disponibilidade - nome, descrição, status e ordem. Rota web,
    prefixo de API e permissão mínima continuam vindo do código de propósito: mudar a permissão
    mínima pela tela deixaria o módulo visível para quem as rotas dele vão recusar com 403 (as
    rotas validam as próprias permissões, escritas em código), o que é pior que não poder editar.

    Campo nulo = "usa o valor do registry". Excluir a linha volta o módulo ao padrão.
    """

    __tablename__ = "workspace_module_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    module_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class WorkspaceModuleVisibility(Base):
    """Uma linha vale para um perfil (`profile_id`) OU um usuário específico (`user_id`), nunca os
    dois - as constraints UNIQUE abaixo funcionam mesmo com NULL porque, em SQL padrão, NULL nunca
    é igual a NULL, então várias linhas de usuário (profile_id NULL) para o mesmo módulo não colidem
    entre si."""

    __tablename__ = "workspace_module_visibility"
    __table_args__ = (
        UniqueConstraint("module_key", "profile_id", name="uq_workspace_module_visibility_profile"),
        UniqueConstraint("module_key", "user_id", name="uq_workspace_module_visibility_user"),
        CheckConstraint(
            "(profile_id IS NOT NULL AND user_id IS NULL) OR (profile_id IS NULL AND user_id IS NOT NULL)",
            name="ck_workspace_module_visibility_target",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    module_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("access_profiles.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    profile: Mapped[AccessProfile | None] = relationship(foreign_keys=[profile_id])
    target_user: Mapped[User | None] = relationship(foreign_keys=[user_id])
    updated_by_user: Mapped[User | None] = relationship(foreign_keys=[updated_by])


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


class AccountActionToken(Base):
    """Fase 2 do Portal (ciclo de vida da conta, ver
    docs/portal-ciclo-vida-conta-colaborador.md seção 8) - tabela compartilhada entre convite
    (`purpose="invite"`, Fase 2C) e reset de senha por e-mail (`purpose="password_reset"`, Fase
    2E, ainda não implementada): mesmo mecanismo de token de uso único, mesma expiração, mesmo
    hash - de propósito, pra não duplicar essa lógica quando a 2E for implementada.

    `token_hash` guarda só o hash do token (mesmo algoritmo de `hash_password`/`hash_api_key`) -
    o valor em claro existe só na memória da requisição que cria o convite/reset, nunca é
    persistido em nenhuma coluna."""

    __tablename__ = "account_action_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    # Só usado em purpose="invite" - é aqui que o ADMIN fixa o vinculo financeiro/operacional,
    # nunca a pessoa convidada (principio de seguranca da Fase 2, secao 2 do documento).
    collaborator_id: Mapped[int | None] = mapped_column(ForeignKey("collaborators.id", ondelete="CASCADE"), nullable=True, index=True)
    role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    user: Mapped[User | None] = relationship(foreign_keys=[user_id])
    collaborator: Mapped[Collaborator | None] = relationship(foreign_keys=[collaborator_id])
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_user_id])


class PortalAccessRequest(Base):
    """Fase 2D do Portal (solicitação de acesso, ver
    docs/portal-ciclo-vida-conta-colaborador.md seção 6) - canal formal pra quem não tem conta e
    não recebeu convite pedir acesso. Nunca cria `User` nem `collaborator_id` sozinha:
    `suggested_collaborator_id` é só uma SUGESTÃO de correspondência automática (prioridade
    `ixc_employee_id` > CPF > nome, ver `find_local_collaborator`), que um admin confirma (ou
    troca) explicitamente ao aprovar. Desde 2026-08-29, aprovar cria a conta DIRETO (com a senha
    que a própria pessoa já definiu no formulário, ver `password_hash` abaixo) - não gera mais
    convite (Fase 2C continua existindo, só não é mais o caminho da aprovação de solicitação)."""

    __tablename__ = "portal_access_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    # Normalizado (só dígitos), igual `Collaborator.cpf` - nunca exibido completo fora do backend
    # (ver services/documents.py `mask_document`, seção 9 do documento de planejamento).
    cpf: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(40), nullable=False)
    email: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    # Nunca a senha em claro - só o hash, igual `User.password_hash`/`AccountActionToken.token_hash`.
    # Nullable: solicitações criadas ANTES desta coluna existir (2026-08-29) não têm senha - a
    # aprovação recusa essas com um erro claro em vez de criar conta sem senha (ver
    # `approve_access_request`), nunca apaga ou força um valor nelas.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    suggested_collaborator_id: Mapped[int | None] = mapped_column(ForeignKey("collaborators.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    suggested_collaborator: Mapped[Collaborator | None] = relationship(foreign_keys=[suggested_collaborator_id])
    reviewed_by: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_user_id])


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
    min_hours_between: Mapped[float | None] = mapped_column(Float, nullable=True)
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
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CpkRegionalSnapshot(Base):
    """Ultimo status de CPK sincronizado da API da frota, por (ano, mes, regional). Guardado em
    cache local em vez de chamar a API ao vivo a cada calculo de folha - se a API da frota cair
    na hora do fechamento, o calculo usa o ultimo snapshot em vez de travar (ver cpk_health.py)."""

    __tablename__ = "cpk_regional_snapshots"
    __table_args__ = (UniqueConstraint("reference_year", "reference_month", "regional", name="uq_cpk_snapshot_period_regional"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    reference_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    reference_month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    regional: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    # "na_meta" | "fora_meta" | "sem_base" (regional sem condutores elegiveis suficientes)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    cpk_realizado: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpk_meta: Mapped[float | None] = mapped_column(Float, nullable=True)
    mes_fechado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


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

    # So preenchido para post_payment_warranty_debit: mes/ano do RETORNO (a O.S de garantia), nao
    # da origem - achado real: sem isso, o lancamento era consumido no PROXIMO fechamento que
    # fosse marcado como pago, independente do mes (ex.: origem em julho, retorno detectado em
    # agosto, mas julho e marcado pago um dia depois - o desconto saia do pagamento de julho,
    # confundindo quem conferia o fechamento). Com o alvo, apply_pending_entries_for_paid_run so
    # consome o lancamento quando o fechamento do mes/ano do RETORNO (ou posterior) for pago.
    target_reference_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_reference_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

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


SCHEDULING_JOB_STATUSES = ("pending", "running", "completed", "failed")


class SchedulingJob(Base):
    """Job assíncrono do módulo de Agendamento (`app/modules/scheduling`).

    Hoje o único `job_type` em uso é "sync" (sincronização IXC → tabelas locais do módulo, que
    leva 1-3 minutos por mês cheio - tempo real de rede, roda em background com polling, mesmo
    padrão de `OperationBackfillJob`). `params` guarda os argumentos da chamada e `result` o
    resumo final. Os tipos antigos "metrics"/"lead_time" (consulta ao vivo, substituída pelo sync
    local) podem existir como histórico em linhas antigas."""

    __tablename__ = "scheduling_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
