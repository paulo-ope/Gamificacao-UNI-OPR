from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EcosystemPermissionOut(BaseModel):
    key: str
    label: str
    module: str


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

    model_config = ConfigDict(from_attributes=True)
