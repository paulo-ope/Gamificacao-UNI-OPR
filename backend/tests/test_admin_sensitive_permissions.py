"""Achado real: a tela de Perfis de Acesso tinha um único botão "Selecionar módulo" por módulo, e
`management:review` (aprovar/rejeitar a decisão da matriz) caía no mesmo módulo que permissões de
rotina (`management:read`, `management:write_justification`) - marcar o módulo inteiro dava, sem
aviso, poder de aprovação a qualquer perfil. `list_permissions` agora marca essas permissões como
`sensitive`, e o frontend as exclui do toggle em lote (ver setProfileModulePermissions)."""
from __future__ import annotations

from app.modules.admin.router import SENSITIVE_PERMISSIONS, list_permissions


def test_management_review_and_admin_are_flagged_sensitive():
    catalog = {item.key: item for item in list_permissions(_=None)}

    assert catalog["management:review"].sensitive is True
    assert catalog["management:admin"].sensitive is True


def test_routine_management_permissions_are_not_sensitive():
    catalog = {item.key: item for item in list_permissions(_=None)}

    assert catalog["management:read"].sensitive is False
    assert catalog["management:write_justification"].sensitive is False


def test_sensitive_permissions_are_all_in_the_catalog():
    from app.core.security import PERMISSION_LABELS

    assert SENSITIVE_PERMISSIONS.issubset(PERMISSION_LABELS.keys())
