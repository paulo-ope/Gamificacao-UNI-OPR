from __future__ import annotations

from html import escape

from app.services.email_sender import OutgoingEmail


def build_password_reset_code_email(*, to: str, name: str, code: str, ttl_minutes: int) -> OutgoingEmail:
    """E-mail do código de 6 dígitos de recuperação de senha. Sem link de propósito: a pessoa digita
    o código na própria tela de recuperação, então não existe URL com credencial para vazar ou ser
    encaminhada."""
    first_name = (name or "").strip().split(" ")[0] or "colaborador(a)"
    text_body = (
        f"Olá, {first_name}.\n\n"
        f"Recebemos um pedido para redefinir a senha do seu acesso ao UNI Workspace.\n\n"
        f"Seu código de verificação é: {code}\n\n"
        f"Ele vale por {ttl_minutes} minutos e só pode ser usado uma vez. "
        f"Digite-o na tela de recuperação de senha para escolher uma senha nova.\n\n"
        f"Se você não fez esse pedido, ignore este e-mail: sua senha continua a mesma e ninguém "
        f"consegue alterá-la sem este código. Nunca compartilhe o código com ninguém.\n\n"
        f"UNI Internet · Ecossistema operacional\n"
    )
    html_body = (
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:0 auto;color:#0f172a">'
        f"<p>Olá, {escape(first_name)}.</p>"
        "<p>Recebemos um pedido para redefinir a senha do seu acesso ao UNI Workspace.</p>"
        "<p>Seu código de verificação é:</p>"
        f'<p style="font-size:32px;font-weight:700;letter-spacing:8px;margin:16px 0">{escape(code)}</p>'
        f"<p>Ele vale por {ttl_minutes} minutos e só pode ser usado uma vez. Digite-o na tela de "
        "recuperação de senha para escolher uma senha nova.</p>"
        "<p style=\"color:#475569;font-size:13px\">Se você não fez esse pedido, ignore este e-mail: sua "
        "senha continua a mesma e ninguém consegue alterá-la sem este código. Nunca compartilhe o "
        "código com ninguém.</p>"
        '<p style="color:#94a3b8;font-size:12px">UNI Internet · Ecossistema operacional</p>'
        "</div>"
    )
    return OutgoingEmail(
        to=to,
        subject="Seu código para redefinir a senha - UNI Workspace",
        text_body=text_body,
        html_body=html_body,
    )
