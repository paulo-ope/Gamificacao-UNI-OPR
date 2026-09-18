"""Achado real: a tela de Perfis de Acesso tinha um único botão "Selecionar módulo" por módulo, e
`management:review` (aprovar/rejeitar a decisão da matriz) caía no mesmo módulo que permissões de
rotina (`management:read`, `management:write_justification`) - marcar o módulo inteiro dava, sem
aviso, poder de aprovação a qualquer perfil. O catálogo marca essas permissões como `sensitive`, e
o frontend as exclui do toggle em lote (ver setProfileModulePermissions)."""
from __future__ import annotations

from app.modules.admin.permissions_service import SENSITIVE_PERMISSIONS, permission_catalog


def _catalog(db_session):
    return {item.key: item for item in permission_catalog(db_session)}


def test_management_review_and_admin_are_flagged_sensitive(db_session):
    catalog = _catalog(db_session)

    assert catalog["management:review"].sensitive is True
    assert catalog["management:admin"].sensitive is True


def test_routine_management_permissions_are_not_sensitive(db_session):
    catalog = _catalog(db_session)

    assert catalog["management:read"].sensitive is False
    assert catalog["management:write_justification"].sensitive is False


def test_permissions_that_redesign_access_control_are_sensitive(db_session):
    """Criar/excluir permissão e reconfigurar módulo redesenham o próprio controle de acesso -
    não podem entrar de carona num "Selecionar módulo" da Administração."""
    catalog = _catalog(db_session)

    assert catalog["admin:permissions:write"].sensitive is True
    assert catalog["admin:modules:write"].sensitive is True


def test_sensitive_permissions_are_all_in_the_catalog(db_session):
    catalog = _catalog(db_session)

    assert SENSITIVE_PERMISSIONS.issubset(catalog.keys())
