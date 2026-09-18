"""Módulos do ecossistema como o sistema os vê depois dos ajustes do admin.

O `app/modules/registry.py` continua sendo a fonte de verdade estrutural (que módulos existem,
qual rota, qual prefixo de API, qual permissão mínima). O que o admin parametriza pela tela é a
CAMADA DE APRESENTAÇÃO E DISPONIBILIDADE - nome, descrição, status e ordem - guardada em
`workspace_module_settings`.

Rota, prefixo de API e permissão mínima ficam fora de propósito: as rotas do backend validam as
próprias permissões, escritas em código, então trocar a permissão mínima pela tela deixaria o
módulo visível para quem vai levar 403 em tudo lá dentro - pior que não poder editar.

Tanto a Administração (`/admin/modules`) quanto a navegação do usuário (`/workspace/modules`) leem
daqui, para não existir "módulo ativo na tela do admin e desativado na barra lateral".
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import WorkspaceModuleSetting
from app.modules.registry import ModuleDefinition, get_module, list_modules

MODULE_STATUSES = ("active", "planned", "disabled")


class ModuleValidationError(ValueError):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class EffectiveModule:
    key: str
    name: str
    description: str
    web_path: str
    api_prefix: str
    required_permission: str
    status: str
    default_name: str
    default_description: str
    default_status: str
    customized: bool
    sort_order: int


def _settings_by_module(db: Session) -> dict[str, WorkspaceModuleSetting]:
    return {item.module_key: item for item in db.scalars(select(WorkspaceModuleSetting))}


def _effective(module: ModuleDefinition, setting: WorkspaceModuleSetting | None, registry_index: int) -> EffectiveModule:
    name = (setting.name if setting and setting.name else None) or module.name
    description = (setting.description if setting and setting.description else None) or module.description
    status = (setting.status if setting and setting.status else None) or module.status
    sort_order = setting.sort_order if setting and setting.sort_order is not None else registry_index
    return EffectiveModule(
        key=module.key,
        name=name,
        description=description,
        web_path=module.web_path,
        api_prefix=module.api_prefix,
        required_permission=module.required_permission,
        status=status,
        default_name=module.name,
        default_description=module.description,
        default_status=module.status,
        customized=bool(
            setting
            and (
                (setting.name and setting.name != module.name)
                or (setting.description and setting.description != module.description)
                or (setting.status and setting.status != module.status)
                or setting.sort_order is not None
            )
        ),
        sort_order=sort_order,
    )


def effective_modules(db: Session) -> list[EffectiveModule]:
    """Módulos na ordem de navegação: a ordem escolhida pelo admin, com a do registry como padrão.

    O índice do registry entra como desempate para a ordem não depender da chave (alfabética
    mudaria a navegação de todos ao renomear um módulo).
    """
    settings = _settings_by_module(db)
    rows = []
    for index, module in enumerate(list_modules()):
        setting = settings.get(module.key)
        explicit = bool(setting and setting.sort_order is not None)
        rows.append((_effective(module, setting, index), explicit, index))
    # Ordem escolhida pelo admin primeiro; em empate, quem foi ordenado à mão vence quem só herdou
    # o índice do registry (senão mandar um módulo para a posição 0 empataria com o primeiro do
    # registry e a ordem seria decidida pela chave, que não é uma escolha de ninguém).
    return [
        item
        for item, _explicit, _index in sorted(
            rows, key=lambda row: (row[0].sort_order, 0 if row[1] else 1, row[2])
        )
    ]


def effective_module(db: Session, module_key: str) -> EffectiveModule | None:
    return next((item for item in effective_modules(db) if item.key == module_key), None)


def update_module_settings(
    db: Session,
    module_key: str,
    *,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
    sort_order: int | None = None,
    updated_by: int | None = None,
    fields_provided: set[str] | None = None,
) -> WorkspaceModuleSetting:
    """Grava o ajuste. Campo enviado vazio (string em branco / null explícito) volta ao padrão do
    registry - é assim que a tela oferece "restaurar padrão" sem um endpoint só para isso."""
    module = get_module(module_key)
    if not module:
        raise ModuleValidationError("Módulo não encontrado.", status_code=404)
    provided = fields_provided or set()

    if status is not None and status not in MODULE_STATUSES:
        raise ModuleValidationError("Status inválido. Use ativo, planejado ou desativado.")

    setting = db.scalar(select(WorkspaceModuleSetting).where(WorkspaceModuleSetting.module_key == module_key))
    if not setting:
        setting = WorkspaceModuleSetting(module_key=module_key)
        db.add(setting)
        db.flush()

    if "name" in provided:
        text = (name or "").strip()
        setting.name = text or None
    if "description" in provided:
        text = (description or "").strip()
        setting.description = text or None
    if "status" in provided:
        setting.status = status or None
    if "sort_order" in provided:
        setting.sort_order = sort_order
    setting.updated_by = updated_by
    db.flush()
    return setting
