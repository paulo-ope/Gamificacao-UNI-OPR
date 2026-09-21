"""Swagger protegido e filtrado para o time de integração externa (UNI/Portal de Resultados).

Não é o `/docs` padrão (ver `app/main.py`: desligado em produção, expõe toda a API sem login).
Esta rota fica sempre ligada, mesmo em produção, mas só mostra os endpoints já documentados à mão
para consumo externo (`docs/api-operacao-analitica.md`) e exige autenticação em toda chamada.

Autenticação aceita (qualquer uma das duas):

- Sessão do workspace (`Authorization: Bearer <token de login>`) de usuário com a permissão
  `admin:integrations:read`.
- Token de integração (`AiApiToken`/`ApiKeyCredential`, o mesmo emitido em Administração > Gestão
  API/MCP), como header `x-api-key` ou como `?token=` na própria URL.

O `?token=` existe só para esta rota de LEITURA de documentação. O Swagger UI, ao abrir a página
HTML, busca o `openapi.json` sozinho via `fetch` do navegador e não repete headers customizados -
sem um jeito de embutir o token na própria URL do schema, a casca HTML autenticaria mas o
`openapi.json` (o que realmente importa) ficaria de fora.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, permissions_for_user
from app.db.session import get_db
from app.models import User
from app.modules.ai.auth import try_resolve_api_key_context

REQUIRED_PERMISSION = "admin:integrations:read"

# Tags do OpenAPI que compõem a documentação de integração externa hoje. Pedido do usuário em
# 2026-09-21 (Cubo de Dados Corporativo / Portal Executivo): cobertura de leitura de TODOS os
# módulos de negócio, sem exceção - cada tag aqui corresponde a um `APIRouter(tags=[...])` real
# do backend (ver `docs/api-completa.md` para o mapeamento completo módulo -> endpoints).
INTEGRATION_DOCS_TAGS = (
    "operations",
    "gamification",
    "dashboard",
    "scoring",
    "rules",
    "service-orders",
    "calculation-runs",
    "leadership",
    "point-balance",
    "collaborators",
    "audit",
    "support",
    "scheduling",
    "localiza",
    "management",
    "admin",
    "admin-ai-governance",
    "intelligence",
)

# Descrição por módulo, mostrada no Swagger acima de cada seção. Cada linha corresponde a um
# módulo real do ecossistema (ver docs/00-TRILHA-0.md) - mantida curta de propósito, o detalhe
# fica no docstring de cada endpoint.
_TAG_DESCRIPTIONS: dict[str, str] = {
    "operations": "Operação Analítica: O.S. importadas do IXC, SLA, backlog, garantia, produtividade, rede/login/ONU.",
    "gamification": "Gamificação Operacional: remuneração variável, pontuação e fechamento de produtividade a partir das O.S.",
    "dashboard": "Indicadores agregados do dashboard da Gamificação Operacional.",
    "scoring": "Regras de pontuação (grupos, exceções por assunto) usadas no cálculo de fechamento.",
    "rules": "Regras de saúde/penalidade aplicadas no cálculo de pontuação.",
    "service-orders": "Consulta das O.S. já importadas para a Gamificação Operacional.",
    "calculation-runs": "Execuções (runs) de fechamento de pontuação: status, histórico, auditoria (só leitura aqui - a execução em si é escrita, não exposta).",
    "leadership": "Bônus de liderança calculado sobre o fechamento do período.",
    "point-balance": "Saldo de pontos e garantia por colaborador, pós-pagamento.",
    "collaborators": "Cadastro de colaboradores (técnicos, operadores) e estrutura organizacional.",
    "audit": "Log de auditoria de alterações na Gamificação Operacional.",
    "support": "SGP Suporte: atendimentos, TMA/TMR, motivos, e o Atendimento IXC (indicador preditivo de incidente).",
    "scheduling": "Agendamento: tempo de resposta, produtividade e fila de reagendamento.",
    "localiza": "UNI Localiza: localização de login/cliente a partir do IXC - dado sensível de cliente, tratar com cuidado extra.",
    "management": "Gestão Integrada: estrutura operacional, casos de produtividade abaixo da meta, justificativas.",
    "admin": "Administração: usuários, perfis de acesso, permissões e módulos do ecossistema.",
    "admin-ai-governance": "Governança de acesso de IA: quais endpoints/campos ficam expostos a agentes de IA e tokens emitidos.",
    "intelligence": "UNI Intelligence: cockpit operacional, monitores, alertas e publicações.",
}

_OPENAPI_DESCRIPTION = """\
Documentação de integração externa do UNI Workspace - leitura corporativa, sem nenhuma operação de
escrita (a estrutura deste schema só inclui métodos `GET`, mesmo quando o módulo tem endpoint de
escrita em outro lugar da API real).

### Autenticação
1. Login: `POST /api/auth/login` com e-mail e senha da identidade de integração -> devolve um
   `access_token` (Bearer JWT).
2. Use `Authorization: Bearer <access_token>` em toda chamada. O token expira (ver
   `AUTH_TOKEN_EXPIRE_MINUTES`) - quando expirar, faça login de novo. Não existe refresh token
   separado: o mecanismo de renovação É o login novamente.
3. Alternativa só para ESTA página de documentação (não para os endpoints de dado): `?token=` na
   URL ou header `x-api-key`, com um token de integração emitido em Administração > Gestão API/MCP.

### Permissões da identidade de integração
Cada conta tem um conjunto fixo de permissões (`GET .../auth/login` devolve a lista em `user.permissions`).
Uma chamada para um dado fora do conjunto autorizado responde `403`, não `404` nem dado vazio.

### Cobertura
Ver `docs/integracao-uni/cobertura-validacao.md` no repositório para o que está verificado em
produção versus só documentado no código.
"""


# Respostas de erro comuns a QUALQUER endpoint desta doc (mesmo esquema de autenticação/
# autorização em todo o backend, ver core/security.py) - documentadas aqui uma vez, aplicadas em
# cada operação, em vez de exigir isso em 182 docstrings manuais.
_COMMON_ERROR_RESPONSES: dict[str, dict] = {
    "401": {"description": "Sem `Authorization: Bearer` válido, ou token expirado/malformado."},
    "403": {"description": "Autenticado, mas sem a permissão exigida por este endpoint (ver campo `x-permission` abaixo)."},
    "422": {"description": "Parâmetro obrigatório ausente ou em formato inválido (ex.: `date_from`/`date_to` fora do padrão `YYYY-MM-DD`)."},
}


def _permission_keys_from_dependant(dependant) -> list[str]:
    """Extrai, por introspecção real do código (não digitado à mão), toda chave de permissão que
    `require_permission`/`require_any_permission` exige nesta rota - inclui tanto a exigida no
    parâmetro da própria função quanto a herdada de `APIRouter(dependencies=[...])` (ex.: todo
    endpoint de `operations` herda `operations:read` do router, além da permissão específica do
    endpoint). Caminho certo de errar isso à mão seria esquecer uma das duas fontes."""
    found: list[str] = []
    stack = [dependant]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        call = getattr(current, "call", None)
        code = getattr(call, "__code__", None)
        closure = getattr(call, "__closure__", None)
        qualname = getattr(call, "__qualname__", "")
        if code is not None and closure is not None:
            freevars = code.co_freevars
            if qualname.startswith("require_permission.") and "permission" in freevars:
                found.append(closure[freevars.index("permission")].cell_contents)
            elif qualname.startswith("require_any_permission.") and "permissions" in freevars:
                found.extend(closure[freevars.index("permissions")].cell_contents)
        stack.extend(getattr(current, "dependencies", None) or [])
    # Ordem estável e sem duplicata (router + rota podem repetir a mesma chave).
    return sorted(set(found))


_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail=(
        "Acesso à documentação de integração exige login com a permissão "
        f"'{REQUIRED_PERMISSION}' ou um token de integração válido."
    ),
)


def _user_from_session_token(raw_token: str, db: Session) -> User | None:
    try:
        payload = decode_access_token(raw_token)
    except HTTPException:
        return None
    user = db.get(User, int(payload.get("sub") or 0))
    if not user or not user.active:
        return None
    return user


def require_integration_docs_access(
    request: Request,
    token: str | None = Query(
        default=None,
        description="Token de sessão (Bearer) ou de integração - alternativa ao header, para o Swagger UI carregar sozinho.",
    ),
    db: Session = Depends(get_db),
) -> User:
    header_auth = request.headers.get("authorization", "")
    session_token = token
    if not session_token and header_auth.lower().startswith("bearer "):
        session_token = header_auth[len("bearer "):].strip()

    if session_token:
        user = _user_from_session_token(session_token, db)
        if user and REQUIRED_PERMISSION in permissions_for_user(user):
            return user

    api_key = token or request.headers.get("x-api-key")
    if api_key:
        context = try_resolve_api_key_context(api_key, db)
        if context is not None:
            return context.user

    raise _UNAUTHORIZED


def build_integration_openapi_schema(request: Request) -> dict:
    """Schema OpenAPI completo do app, filtrado só para os endpoints de integração externa."""
    app = request.app
    allowed_tags = set(INTEGRATION_DOCS_TAGS)
    full_schema = get_openapi(
        title=f"{app.title} - Integração UNI",
        version=app.version,
        routes=app.routes,
        description=_OPENAPI_DESCRIPTION,
        tags=[
            {"name": tag, "description": _TAG_DESCRIPTIONS[tag]}
            for tag in INTEGRATION_DOCS_TAGS
            if tag in _TAG_DESCRIPTIONS
        ],
    )
    # (path_format, método) -> APIRoute real, para depois voltar da entrada do schema OpenAPI (que
    # só tem string) até o objeto de rota (que tem o `dependant` de verdade) e extrair a permissão
    # exigida por introspecção, não por texto digitado à mão. Nesta versão do FastAPI,
    # `app.routes`/`router.routes` guardam um `_IncludedRouter` por `include_router` (não a
    # `APIRoute` já com o prefixo aplicado) - a rota de verdade mora em
    # `_IncludedRouter.original_router.routes`, com o path relativo só ao próprio router. O
    # prefixo de CADA nível de inclusão (pode haver mais de um - ex.: `admin_router` incluído
    # dentro de `intelligence_router`, que por sua vez é incluído no app com `/api`) fica em
    # `_IncludedRouter.include_context.prefix` - por isso a recursão acumula prefixo por nível em
    # vez de assumir um único prefixo fixo.
    routes_by_path_method: dict[tuple[str, str], APIRoute] = {}

    def _index_route(route_obj, prefix: str) -> None:
        if isinstance(route_obj, APIRoute):
            for method in route_obj.methods or ():
                routes_by_path_method[(prefix + route_obj.path_format, method.lower())] = route_obj
        elif hasattr(route_obj, "original_router"):
            nested_prefix = prefix + getattr(route_obj.include_context, "prefix", "")
            for nested in route_obj.original_router.routes:
                _index_route(nested, nested_prefix)

    for route in app.routes:
        _index_route(route, "")

    filtered_paths: dict = {}
    for path, methods in full_schema.get("paths", {}).items():
        kept_methods = {
            method: operation
            for method, operation in methods.items()
            # Só GET: mesmo que um router misture leitura e escrita sob a mesma tag (ex.:
            # calculation-runs tem GET de status e POST /calculate no mesmo arquivo), a doc de
            # integração externa nunca deve LISTAR uma operação de escrita - "consulta,
            # exclusivamente em leitura" (pedido do usuário) é garantido aqui, não só pela
            # permissão da conta que consome.
            if method == "get" and allowed_tags & set(operation.get("tags", []))
        }
        for method, operation in kept_methods.items():
            route = routes_by_path_method.get((path, method))
            permissions = _permission_keys_from_dependant(route.dependant) if route else []
            operation["x-permission"] = permissions or ["nenhuma (só exige estar autenticado)"]
            note = (
                f"**Permissão exigida:** `{' ou '.join(permissions)}`"
                if permissions
                else "**Permissão exigida:** nenhuma além de estar autenticado."
            )
            operation["description"] = f"{operation.get('description', '').strip()}\n\n{note}".strip()
            responses = operation.setdefault("responses", {})
            for code, body in _COMMON_ERROR_RESPONSES.items():
                responses.setdefault(code, body)
        if kept_methods:
            filtered_paths[path] = kept_methods
    full_schema["paths"] = filtered_paths
    full_schema["tags"] = [
        tag for tag in full_schema.get("tags", []) if tag.get("name") in allowed_tags
    ]
    return full_schema
