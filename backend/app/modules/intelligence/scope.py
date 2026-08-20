"""Usuario transiente usado pelos monitores para chamar as funcoes de consulta de `operations`
sem escopo regional restrito.

As funcoes de operations/queries.py e operations/services.py recebem um `User` só para decidir
se recortam por regional: isso só acontece quando `user.managed_regional`/`managed_regionals`
está preenchido OU `user.role == "regional_manager_viewer"` (ver operations/queries.py:275-282).
Qualquer outro role, sem regional configurada, enxerga tudo - exatamente o que um monitor de
fundo precisa (ele avalia a operação inteira, não a visão recortada de uma pessoa).

Este usuário nunca é persistido nem adicionado a uma sessão - é só um objeto Python com os
atributos que essas funções leem."""
from __future__ import annotations

from app.models import User

# Role deliberadamente fora de ROLE_PERMISSIONS (core/security.py) - não é uma identidade de
# login, não deve nunca autenticar nem receber permissões por acidente.
SYSTEM_MONITOR_ROLE = "system_monitor"


def system_user() -> User:
    return User(
        id=0,
        name="UNI Intelligence",
        email="system@intelligence.local",
        password_hash="",
        role=SYSTEM_MONITOR_ROLE,
        active=True,
        managed_regional=None,
        managed_regionals=[],
    )
