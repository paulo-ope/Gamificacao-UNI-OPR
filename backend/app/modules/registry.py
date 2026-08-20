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
    ModuleDefinition(
        key="scheduling",
        name="Agendamento",
        description="Tempo de resposta, produtividade e fila do setor de agendamento.",
        web_path="/agendamento",
        api_prefix="/api/scheduling",
        required_permission="scheduling:read",
        status="active",
    ),
    ModuleDefinition(
        key="support",
        name="SGP Suporte",
        description="Indicadores, atendimentos e métricas de suporte vindos do OPA Suite.",
        web_path="/suporte",
        api_prefix="/api/support",
        required_permission="support:read",
        status="active",
    ),
    ModuleDefinition(
        key="management",
        name="Gestão Integrada",
        description="Estrutura operacional, casos de gestão, justificativas e tomada de decisão da matriz.",
        web_path="/gestao",
        api_prefix="/api/management",
        required_permission="management:read",
        status="active",
    ),
    ModuleDefinition(
        key="admin",
        name="Administração",
        description="Usuários, perfis de acesso, permissões e escopos do ecossistema.",
        web_path="/admin",
        api_prefix="/api/admin",
        required_permission="admin:users:read",
        status="active",
    ),
    ModuleDefinition(
        key="intelligence",
        name="UNI Intelligence",
        description="Cockpit operacional, alertas, monitores e publicações do UNI Intelligence.",
        web_path="/intelligence",
        api_prefix="/api/intelligence",
        required_permission="intelligence:read",
        status="active",
    ),
)


def list_modules() -> tuple[ModuleDefinition, ...]:
    """Retorna os módulos em ordem de navegação."""

    return MODULES


def get_module(key: str) -> ModuleDefinition | None:
    """Busca um módulo pela sua chave estável."""

    return next((module for module in MODULES if module.key == key), None)
