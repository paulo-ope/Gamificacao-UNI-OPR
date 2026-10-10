from __future__ import annotations

from dataclasses import dataclass
from html import escape

from app.core.config import get_settings
from app.services.email_sender import OutgoingEmail

# Paleta do UNI Workspace (mesma da tela de acesso, frontend/components/workspace/workspace-login.css).
_INK = "#152747"
_MUTED = "#5f7391"
_BLUE = "#2d5fff"
_TEAL = "#27d9bf"
_MIST = "#edf2ff"
_MIST_LINE = "#d3e0ff"
_LINE = "#dfe7f2"
_PAGE = "#f7f9fc"
_FONT = "'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
_MONO = "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace"


@dataclass(frozen=True)
class _CodeEmail:
    """Conteúdo de um e-mail de código de 6 dígitos. A estrutura visual é uma só (`_render_html`): cada
    e-mail só informa os textos."""

    subject: str
    kicker: str
    title: str
    intro: str
    ignore_note: str


_PASSWORD_RESET = _CodeEmail(
    subject="Seu código para redefinir a senha - UNI Workspace",
    kicker="Segurança de acesso",
    title="Redefinição de senha",
    intro=(
        "Recebemos um pedido para redefinir a senha do seu acesso ao UNI Workspace. "
        "Digite o código abaixo na tela de recuperação de senha para escolher uma senha nova."
    ),
    ignore_note="Se você não fez esse pedido, ignore este e-mail: sua senha continua a mesma e ninguém consegue alterá-la sem este código.",
)

_EMAIL_VERIFICATION = _CodeEmail(
    subject="Confirme seu e-mail - solicitação de acesso UNI Workspace",
    kicker="Solicitação de acesso",
    title="Confirme seu e-mail",
    intro=(
        "Recebemos uma solicitação de acesso ao UNI Workspace com este e-mail. "
        "Digite o código abaixo na tela da solicitação para confirmar que este e-mail é seu."
    ),
    ignore_note="Se você não fez essa solicitação, ignore este e-mail: nada será criado sem este código.",
)


def _first_name(name: str) -> str:
    return (name or "").strip().split(" ")[0] or "colaborador(a)"


def _logo_url() -> str | None:
    """Imagem precisa de URL pública absoluta. Em desenvolvimento (localhost/http) o e-mail sai só com a
    marca em texto, para não montar uma imagem quebrada que nenhum cliente de e-mail conseguiria abrir."""
    base = get_settings().frontend_url.strip().rstrip("/")
    return f"{base}/brand/uni-logo.png" if base.startswith("https://") else None


def _render_text(content: _CodeEmail, *, first_name: str, code: str, ttl_minutes: int) -> str:
    # A linha "Seu código de verificação é: ..." é parte do contrato (os testes e quem lê o texto simples
    # contam com ela) - não mudar o texto dela.
    return (
        f"UNI Workspace · {content.kicker}\n\n"
        f"Olá, {first_name}.\n\n"
        f"{content.intro}\n\n"
        f"Seu código de verificação é: {code}\n\n"
        f"Validade: {ttl_minutes} minutos, uso único.\n\n"
        f"{content.ignore_note}\n"
        f"Nunca compartilhe este código com ninguém.\n\n"
        f"--\n"
        f"UNI Internet · Ecossistema operacional\n"
        f"Mensagem automática do UNI Workspace.\n"
    )


def _render_html(content: _CodeEmail, *, first_name: str, code: str, ttl_minutes: int) -> str:
    """HTML de e-mail: tabelas e estilos inline (os clientes de e-mail ignoram CSS externo e <style>
    em parte dos casos). O gradiente da faixa superior tem cor sólida de reserva para o Outlook."""
    logo = _logo_url()
    brand_logo = (
        f'<td style="padding-right:12px;vertical-align:middle;">'
        f'<img src="{escape(logo, quote=True)}" alt="UNI Internet" width="60" style="display:block;border:0;outline:none;height:auto;width:60px;">'
        f"</td>"
        f'<td style="padding-right:12px;vertical-align:middle;"><div style="width:1px;height:26px;background:{_LINE};font-size:0;line-height:0;">&nbsp;</div></td>'
        if logo
        else ""
    )
    preheader = f"Seu código de verificação: {code}. Válido por {ttl_minutes} minutos."
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{escape(content.title)}</title>
</head>
<body style="margin:0;padding:0;background:{_PAGE};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;font-size:1px;line-height:1px;color:{_PAGE};">{escape(preheader)}&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_PAGE};">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:560px;">
<tr><td style="padding:0 4px 20px 4px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
{brand_logo}<td style="vertical-align:middle;font-family:{_FONT};font-size:20px;font-weight:700;letter-spacing:-0.2px;color:{_INK};">workspace<span style="color:{_TEAL};">.</span></td>
</tr></table>
</td></tr>
<tr><td style="background:#ffffff;border:1px solid {_LINE};border-radius:16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td style="height:4px;line-height:4px;font-size:0;background:{_BLUE};background-image:linear-gradient(90deg,{_BLUE},{_TEAL});border-radius:16px 16px 0 0;">&nbsp;</td></tr>
<tr><td style="padding:32px 36px 12px 36px;font-family:{_FONT};color:{_INK};">
<p style="margin:0 0 8px 0;font-size:11px;font-weight:700;letter-spacing:1.6px;text-transform:uppercase;color:{_BLUE};">{escape(content.kicker)}</p>
<h1 style="margin:0 0 20px 0;font-size:24px;line-height:1.25;font-weight:700;color:{_INK};">{escape(content.title)}</h1>
<p style="margin:0 0 12px 0;font-size:15px;line-height:1.6;color:{_INK};">Olá, {escape(first_name)}.</p>
<p style="margin:0 0 24px 0;font-size:15px;line-height:1.6;color:{_INK};">{escape(content.intro)}</p>
</td></tr>
<tr><td style="padding:0 36px 8px 36px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
<td align="center" style="background:{_MIST};border:1px solid {_MIST_LINE};border-radius:12px;padding:22px 12px 18px 12px;">
<p style="margin:0 0 10px 0;font-family:{_FONT};font-size:11px;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;color:{_MUTED};">Seu código de verificação</p>
<div style="font-family:{_MONO};font-size:38px;line-height:1;font-weight:700;letter-spacing:10px;padding-left:10px;color:{_INK};">{escape(code)}</div>
<p style="margin:12px 0 0 0;font-family:{_FONT};font-size:12px;color:{_MUTED};">Válido por {ttl_minutes} minutos &middot; uso único</p>
</td>
</tr></table>
</td></tr>
<tr><td style="padding:20px 36px 32px 36px;font-family:{_FONT};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
<td style="background:{_PAGE};border-left:3px solid {_TEAL};border-radius:4px;padding:14px 16px;font-size:13px;line-height:1.6;color:{_MUTED};">
<strong style="color:{_INK};">Nunca compartilhe este código com ninguém.</strong><br>
{escape(content.ignore_note)}
</td>
</tr></table>
</td></tr>
</table>
</td></tr>
<tr><td align="center" style="padding:20px 8px 0 8px;font-family:{_FONT};font-size:12px;line-height:1.6;color:{_MUTED};">
UNI Internet &middot; Ecossistema operacional<br>
<span style="color:#97accf;">Mensagem automática do UNI Workspace.</span>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


def _build(content: _CodeEmail, *, to: str, name: str, code: str, ttl_minutes: int) -> OutgoingEmail:
    first_name = _first_name(name)
    return OutgoingEmail(
        to=to,
        subject=content.subject,
        text_body=_render_text(content, first_name=first_name, code=code, ttl_minutes=ttl_minutes),
        html_body=_render_html(content, first_name=first_name, code=code, ttl_minutes=ttl_minutes),
    )


def build_password_reset_code_email(*, to: str, name: str, code: str, ttl_minutes: int) -> OutgoingEmail:
    """E-mail do código de 6 dígitos de recuperação de senha. Sem link de propósito: a pessoa digita o
    código na própria tela de recuperação, então não existe URL com credencial para vazar ou ser
    encaminhada."""
    return _build(_PASSWORD_RESET, to=to, name=name, code=code, ttl_minutes=ttl_minutes)


def build_email_verification_code_email(*, to: str, name: str, code: str, ttl_minutes: int) -> OutgoingEmail:
    """E-mail do código de 6 dígitos que prova a posse da caixa na solicitação de acesso. Sem link,
    pelo mesmo motivo do código de recuperação de senha."""
    return _build(_EMAIL_VERIFICATION, to=to, name=name, code=code, ttl_minutes=ttl_minutes)
