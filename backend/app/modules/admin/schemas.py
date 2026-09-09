from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EcosystemPermissionOut(BaseModel):
    key: str
    label: str
    #: Rótulo do grupo na tela: nome do módulo, ou área transversal ("Portal do Colaborador").
    module: str
    #: Chave do módulo do registry. None em permissão transversal, que não pertence a um módulo.
    module_key: str | None = None
    sensitive: bool = False
    #: true = criada na aba Permissões (excluível); false = declarada em código (só revogável).
    custom: bool = False
    description: str | None = None
    #: Uso atual, para a tela mostrar quem é afetado antes de revogar ou excluir.
    profile_count: int = 0
    user_count: int = 0
    profile_names: list[str] = Field(default_factory=list)


class CustomPermissionCreate(BaseModel):
    key: str = Field(min_length=3, max_length=120)
    label: str = Field(min_length=3, max_length=160)
    module_key: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    sensitive: bool = False


class CustomPermissionUpdate(BaseModel):
    """A chave nunca muda (ver `permissions_service.update_custom_permission`)."""

    label: str | None = Field(default=None, min_length=3, max_length=160)
    module_key: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    sensitive: bool | None = None
    active: bool | None = None


class AccessProfileBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = None
    active: bool = True
    permission_keys: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Nome do perfil é obrigatório.")
        return text

    @field_validator("permission_keys")
    @classmethod
    def unique_permissions(cls, value: list[str]) -> list[str]:
        return sorted({item.strip() for item in value if item.strip()})


class AccessProfileCreate(AccessProfileBase):
    pass


class AccessProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None
    active: bool | None = None
    permission_keys: list[str] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = value.strip()
        if not text:
            raise ValueError("Nome do perfil é obrigatório.")
        return text

    @field_validator("permission_keys")
    @classmethod
    def unique_permissions(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        return sorted({item.strip() for item in value if item.strip()})


class AccessProfileOut(BaseModel):
    id: int
    name: str
    description: str | None
    legacy_role: str | None
    active: bool
    is_system: bool
    permission_keys: list[str]
    user_count: int = 0
    created_at: datetime
    updated_at: datetime
    #: Motivo pelo qual este perfil não pode ser excluído agora (None = pode). A tela mostra o
    #: texto em vez de esconder o botão, para o admin saber o que destravar.
    delete_blocked_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class AdminPersonStructureOut(BaseModel):
    id: int
    name: str
    role: str
    regional: str
    active: bool
    is_registered: bool
    cpf_masked: str | None = None
    employee_type: str | None = None
    team_type: str | None = None
    supervisor_user_id: int | None = None
    supervisor_name: str | None = None
    regional_manager_user_id: int | None = None
    regional_manager_name: str | None = None
    structure_status: str
    structure_notes: str | None = None
    ixc_employee_id: int | None = None
    portal_user_id: int | None = None
    portal_user_email: str | None = None
    has_photo: bool = False


class AdminStructureOption(BaseModel):
    id: int
    name: str


class AdminPeopleStructureSummary(BaseModel):
    total_people: int
    active_people: int
    without_supervisor: int
    without_team_type: int
    pending_review: int
    field_team: int
    scheduling_team: int


class AdminPeopleStructureOut(BaseModel):
    summary: AdminPeopleStructureSummary
    people: list[AdminPersonStructureOut]
    supervisors: list[AdminStructureOption]
    regional_managers: list[AdminStructureOption]
    employee_types: list[str]
    team_types: list[str]
    statuses: list[str]


class AdminPersonStructureUpdate(BaseModel):
    cpf: str | None = Field(default=None, max_length=20)
    employee_type: str | None = Field(default=None, max_length=40)
    team_type: str | None = Field(default=None, max_length=40)
    supervisor_user_id: int | None = None
    regional_manager_user_id: int | None = None
    structure_status: str | None = Field(default=None, max_length=40)
    structure_notes: str | None = Field(default=None, max_length=1000)

    @field_validator("cpf", "employee_type", "team_type", "structure_status", "structure_notes")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = value.strip()
        return text or None


class AdminModuleProfileVisibilityOut(BaseModel):
    profile_id: int
    profile_name: str
    visible: bool
    has_required_permission: bool


class AdminModuleUserVisibilityOut(BaseModel):
    user_id: int
    user_name: str
    user_email: str
    visible: bool
    reason: str | None = None


class AdminWorkspaceModuleOut(BaseModel):
    key: str
    name: str
    description: str
    web_path: str
    api_prefix: str
    required_permission: str
    status: str
    #: Valores do código (`app/modules/registry.py`), antes de qualquer ajuste do admin - a tela
    #: usa para mostrar "restaurar padrão" com o texto que voltaria.
    default_name: str = ""
    default_description: str = ""
    default_status: str = ""
    customized: bool = False
    sort_order: int = 0
    profiles: list[AdminModuleProfileVisibilityOut]
    user_overrides: list[AdminModuleUserVisibilityOut] = Field(default_factory=list)


class AdminModuleSettingsUpdate(BaseModel):
    """Ajuste de apresentação/disponibilidade do módulo. Campo enviado em branco (ou null) volta ao
    padrão do registry - é assim que a tela oferece "restaurar padrão" sem endpoint extra.

    Rota web, prefixo de API e permissão mínima não entram aqui de propósito (ver
    `modules_service`): mudar a permissão mínima pela tela deixaria o módulo visível para quem as
    rotas dele vão recusar com 403.
    """

    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    status: str | None = Field(default=None, max_length=20)
    sort_order: int | None = Field(default=None, ge=0, le=999)


class AdminModuleVisibilityUpdate(BaseModel):
    profile_id: int
    visible: bool
    reason: str | None = Field(default=None, max_length=300)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = value.strip()
        return text or None


class AdminModuleUserVisibilityUpsert(BaseModel):
    user_id: int
    visible: bool
    reason: str | None = Field(default=None, max_length=300)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = value.strip()
        return text or None


class WorkspaceVisibleModuleOut(BaseModel):
    key: str
    name: str
    description: str
    web_path: str
    api_prefix: str
    required_permission: str
    status: str
