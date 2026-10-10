from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    text_body: str
    html_body: str | None = None


def send_email(message: OutgoingEmail) -> bool:
    """Envia um e-mail transacional via SMTP. Nunca levanta exceção para quem chamou: o envio roda
    em tarefa de segundo plano depois da resposta HTTP, e uma falha de SMTP não pode derrubar a
    rota nem vazar para o cliente se o destinatário existe (resposta pública é sempre genérica).

    Devolve True só quando o servidor SMTP aceitou a mensagem. Desligado (`EMAIL_ENABLED=false`) ou
    sem host configurado devolve False. O log nunca inclui o corpo da mensagem (que carrega o
    código) nem credenciais - só o destinatário mascarado e o tipo do erro."""
    settings = get_settings()
    if not settings.email_enabled:
        logger.info("Envio de e-mail desligado (EMAIL_ENABLED=false); mensagem para %s não enviada.", _mask(message.to))
        if settings.app_env.lower() not in {"production", "prod"}:
            # SÓ fora de produção: sem SMTP local não há como ver o código de verificação, então ele
            # aparece no console do desenvolvedor. Em produção o corpo nunca é logado.
            logger.warning("[DEV] E-mail para %s | %s\n%s", message.to, message.subject, message.text_body)
        return False
    if not settings.smtp_host:
        logger.error("EMAIL_ENABLED=true, mas SMTP_HOST está vazio; mensagem para %s não enviada.", _mask(message.to))
        return False

    mime = EmailMessage()
    mime["Subject"] = message.subject
    mime["From"] = formataddr((settings.smtp_from_name, settings.smtp_from))
    mime["To"] = message.to
    mime.set_content(message.text_body)
    if message.html_body:
        mime.add_alternative(message.html_body, subtype="html")

    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS, context=ssl.create_default_context()
            ) as server:
                _login_and_send(server, mime)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS) as server:
                server.starttls(context=ssl.create_default_context())
                _login_and_send(server, mime)
    except Exception as exc:  # noqa: BLE001 - qualquer falha de rede/SMTP deve virar só um log
        logger.error("Falha ao enviar e-mail para %s (%s).", _mask(message.to), type(exc).__name__)
        return False
    return True


def _login_and_send(server: smtplib.SMTP, mime: EmailMessage) -> None:
    settings = get_settings()
    if settings.smtp_user:
        server.login(settings.smtp_user, settings.smtp_password)
    server.send_message(mime)


def _mask(address: str) -> str:
    local, _, domain = address.partition("@")
    return f"{local[:2]}***@{domain}" if domain else "***"
