"""Tela de login + consentimento do conector MCP remoto - a ponte entre `provider.authorize()`
(chamado pelo SDK do MCP quando o Claude abre `/authorize`) e a decisão humana de aprovar ou não.

Reaproveita o login (`User.password_hash`/`verify_password`) e o limitador de tentativas já
existentes em `app/api/routes/auth.py` - não é um sistema de conta novo, é a mesma conta que já
loga na Operação Analítica normalmente. A sessão desta tela vive num cookie próprio
(`mcp_oauth_session`, HttpOnly), separado do token Bearer usado pelo resto da API - só precisa
durar o suficiente pra completar o consentimento, não pra navegar o app inteiro.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from mcp.server.auth.provider import construct_redirect_uri
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.auth import _clear_login_attempts, _guard_login_attempts, _register_login_failure
from app.core.security import create_access_token, decode_access_token, permissions_for_user, verify_password
from app.db.session import get_db
from app.models import User

from .models import McpOAuthAuthorizationCode, McpOAuthPendingAuthorization
from .provider import AUTHORIZATION_CODE_TTL, SCOPE, _as_utc, _generate_secret, _hash_token

router = APIRouter(prefix="/oauth", tags=["mcp-oauth-consent"])

SESSION_COOKIE_NAME = "mcp_oauth_session"


def _is_https(request: Request) -> bool:
    # Mesmo raciocínio de ai/router.py sobre X-Forwarded-Proto: o proxy reverso da VM termina TLS
    # e repassa em HTTP puro, então request.url.scheme sozinho sempre diria "http" em produção.
    forwarded = request.headers.get("x-forwarded-proto")
    return (forwarded or request.url.scheme) == "https"


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<title>{escape(title)}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 480px; margin: 64px auto; padding: 0 24px; color: #1a1a1a; }}
h1 {{ font-size: 1.25rem; }}
label {{ display: block; margin-top: 16px; font-size: 0.9rem; color: #444; }}
input {{ width: 100%; padding: 8px; margin-top: 4px; box-sizing: border-box; font-size: 1rem; }}
button {{ margin-top: 24px; padding: 10px 20px; font-size: 1rem; cursor: pointer; }}
.primary {{ background: #1a1a1a; color: white; border: none; }}
.secondary {{ background: white; border: 1px solid #ccc; margin-left: 8px; }}
.error {{ background: #fee2e2; color: #991b1b; padding: 8px 12px; border-radius: 4px; margin-top: 16px; font-size: 0.9rem; }}
.hint {{ color: #666; font-size: 0.85rem; margin-top: 8px; }}
</style></head>
<body>{body}</body></html>""",
    )


def _pending_or_404(db: Session, request_id: str) -> McpOAuthPendingAuthorization:
    pending = (
        db.query(McpOAuthPendingAuthorization)
        .filter(McpOAuthPendingAuthorization.request_id == request_id)
        .one_or_none()
    )
    if pending is None or _as_utc(pending.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(status_code=404, detail="Pedido de autorização inexistente ou expirado. Peça ao Claude para tentar conectar de novo.")
    return pending


def _current_user_from_cookie(request: Request, db: Session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except HTTPException:
        return None
    user = db.get(User, int(payload.get("sub") or 0))
    return user if user and user.active else None


@router.get("/consent", response_class=HTMLResponse)
def consent_screen(request_id: str, request: Request, db: Session = Depends(get_db)):
    pending = _pending_or_404(db, request_id)
    user = _current_user_from_cookie(request, db)

    if user is None:
        return _page(
            "Entrar - Operação Analítica",
            f"""
            <h1>Entrar na Operação Analítica</h1>
            <p class="hint">O Claude está pedindo acesso de leitura aos dados analíticos de O.S. Entre com sua conta para continuar.</p>
            <form method="post" action="/api/oauth/consent/login">
                <input type="hidden" name="request_id" value="{escape(request_id)}">
                <label>E-mail<input type="email" name="email" required autofocus></label>
                <label>Senha<input type="password" name="password" required></label>
                <button class="primary" type="submit">Entrar</button>
            </form>
            """,
        )

    if SCOPE not in permissions_for_user(user):
        return _page(
            "Sem permissão",
            f"<h1>Sem permissão</h1><p>Sua conta ({escape(user.email)}) não tem a permissão "
            f"'{escape(SCOPE)}' necessária para esta integração. Peça a um administrador para conceder acesso.</p>",
        )

    return _page(
        "Autorizar Claude - Operação Analítica",
        f"""
        <h1>Autorizar acesso do Claude</h1>
        <p>Conectado como <strong>{escape(user.name)}</strong> ({escape(user.email)}).</p>
        <p>O Claude poderá <strong>consultar</strong> dados analíticos de O.S. (agregações, busca, backlog, garantia, metas) em seu nome. Nenhuma tool desta integração escreve ou altera dado nenhum.</p>
        <form method="post" action="/api/oauth/consent/decide">
            <input type="hidden" name="request_id" value="{escape(request_id)}">
            <button class="primary" type="submit" name="decision" value="approve">Permitir</button>
            <button class="secondary" type="submit" name="decision" value="deny">Negar</button>
        </form>
        """,
    )


@router.post("/consent/login")
def consent_login(
    request: Request,
    request_id: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    _pending_or_404(db, request_id)  # 404 cedo se o pedido já morreu, antes de gastar uma tentativa de login
    attempt_key = _guard_login_attempts(request, email)
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not user.active or not verify_password(password, user.password_hash):
        _register_login_failure(attempt_key)
        return _page(
            "Entrar - Operação Analítica",
            f"""
            <h1>Entrar na Operação Analítica</h1>
            <p class="error">E-mail ou senha inválidos.</p>
            <form method="post" action="/api/oauth/consent/login">
                <input type="hidden" name="request_id" value="{escape(request_id)}">
                <label>E-mail<input type="email" name="email" value="{escape(email)}" required autofocus></label>
                <label>Senha<input type="password" name="password" required></label>
                <button class="primary" type="submit">Entrar</button>
            </form>
            """,
        )
    _clear_login_attempts(attempt_key)
    response = RedirectResponse(url=f"/api/oauth/consent?request_id={request_id}", status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_access_token(user),
        httponly=True,
        secure=_is_https(request),
        samesite="lax",
        max_age=900,  # 15 min - só o suficiente pra completar o consentimento nesta mesma visita
    )
    return response


@router.post("/consent/decide")
def consent_decide(
    request: Request,
    request_id: str = Form(...),
    decision: str = Form(...),
    db: Session = Depends(get_db),
):
    pending = _pending_or_404(db, request_id)
    user = _current_user_from_cookie(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Sessão de login expirada - recomece o processo de conexão no Claude.")

    # Captura os campos ANTES de deletar+commitar - `SessionLocal` usa `expire_on_commit=True`
    # (padrão), então acessar um atributo do objeto depois do commit dispararia um reload e
    # estouraria `ObjectDeletedError` (o registro já não existe mais na hora do reload).
    redirect_uri, state = pending.redirect_uri, pending.state

    if decision != "approve":
        db.delete(pending)
        db.commit()
        return RedirectResponse(construct_redirect_uri(redirect_uri, error="access_denied", state=state), status_code=303)

    if SCOPE not in permissions_for_user(user):
        raise HTTPException(status_code=403, detail=f"Sua conta não tem a permissão '{SCOPE}'.")

    raw_code = _generate_secret()
    db.add(
        McpOAuthAuthorizationCode(
            code_hash=_hash_token(raw_code),
            client_id=pending.client_id,
            user_id=user.id,
            redirect_uri=redirect_uri,
            redirect_uri_provided_explicitly=pending.redirect_uri_provided_explicitly,
            code_challenge=pending.code_challenge,
            scopes=pending.scopes,
            resource=pending.resource,
            expires_at=datetime.now(timezone.utc) + AUTHORIZATION_CODE_TTL,
        )
    )
    db.delete(pending)
    db.commit()
    return RedirectResponse(construct_redirect_uri(redirect_uri, code=raw_code, state=state), status_code=303)
