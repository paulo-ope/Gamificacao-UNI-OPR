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
        if kept_methods:
            filtered_paths[path] = kept_methods
    full_schema["paths"] = filtered_paths
    full_schema["tags"] = [
        tag for tag in full_schema.get("tags", []) if tag.get("name") in allowed_tags
    ]
    return full_schema
