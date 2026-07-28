"""Registro declarativo dos módulos do UNI Workspace.

O registro não concede acesso por si só: cada rota continua validando a permissão
no backend. Ele existe para documentar fronteiras, habilitar descoberta futura e
evitar que a navegação vire uma lista de módulos espalhada pelo projeto.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ModuleStatus = Literal["active", "planned", "disabled"]


@dataclass(frozen=True)
class ModuleDefinition:
    key: str
    name: str
    description: str
    web_path: str
    api_prefix: str
    required_permission: str
    status: ModuleStatus


MODULES: tuple[ModuleDefinition, ...] = (
    ModuleDefinition(
        key="gamification",
        name="Gamificação Operacional",
        description="Remuneração variável, fechamento e auditoria de produtividade.",
        web_path="/gamificacao",
        api_prefix="/api",
        required_permission="dashboard:read",
        status="active",
    ),
    ModuleDefinition(
        key="operations",
        name="Operação Analítica",
        description="Análise de Ordens de Serviço, SLA, backlog, garantia e produtividade operacional.",
        web_path="/operacao",
        api_prefix="/api/operations",
        required_permission="operations:read",
        status="active",
    ),
)


def list_modules() -> tuple[ModuleDefinition, ...]:
    """Retorna os módulos em ordem de navegação."""

    return MODULES


def get_module(key: str) -> ModuleDefinition | None:
    """Busca um módulo pela sua chave estável."""

    return next((module for module in MODULES if module.key == key), None)
