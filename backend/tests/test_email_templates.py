"""E-mails de código de 6 dígitos (recuperação de senha e verificação de e-mail da solicitação de acesso):
estrutura HTML segura para clientes de e-mail, paleta do Workspace e texto simples organizado."""

import re

import pytest

from app.core.config import get_settings
from app.services.email_templates import build_email_verification_code_email, build_password_reset_code_email

BUILDERS = [build_password_reset_code_email, build_email_verification_code_email]


@pytest.fixture()
def frontend_url(monkeypatch):
    def _set(value: str):
        monkeypatch.setenv("FRONTEND_URL", value)
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


@pytest.mark.parametrize("builder", BUILDERS)
def test_both_emails_carry_the_code_ttl_and_the_contract_line(builder):
    message = builder(to="pessoa@souuni.com", name="Maria da Silva", code="470029", ttl_minutes=10)
    assert message.to == "pessoa@souuni.com"
    # Linha do texto simples que os demais testes e quem lê o e-mail em texto usam.
    assert "Seu código de verificação é: 470029" in message.text_body
    assert "Validade: 10 minutos" in message.text_body
    assert "470029" in message.html_body
    assert "10 minutos" in message.html_body
    assert "Olá, Maria." in message.text_body
    assert "Olá, Maria." in message.html_body


@pytest.mark.parametrize("builder", BUILDERS)
def test_html_uses_the_workspace_palette_and_is_email_safe(builder):
    html = builder(to="a@souuni.com", name="Ana", code="123456", ttl_minutes=10).html_body
    for color in ("#2d5fff", "#27d9bf", "#152747", "#edf2ff"):
        assert color in html
    assert html.lower().startswith("<!doctype html>")
    assert 'lang="pt-BR"' in html
    # Cliente de e-mail não executa script nem carrega CSS/JS externo.
    assert "<script" not in html.lower()
    assert "<link" not in html.lower()
    assert "@import" not in html
    # Layout em tabela, com estilos inline.
    assert 'role="presentation"' in html
    assert "style=" in html


@pytest.mark.parametrize("builder", BUILDERS)
def test_user_supplied_values_are_escaped(builder):
    message = builder(to="a@souuni.com", name='<img src=x onerror="alert(1)"> Zé', code="<b>1</b>", ttl_minutes=10)
    assert "<img src=x" not in message.html_body
    assert "&lt;img" in message.html_body
    assert "<b>1</b>" not in message.html_body


@pytest.mark.parametrize("builder", BUILDERS)
def test_empty_name_falls_back_to_a_neutral_greeting(builder):
    message = builder(to="a@souuni.com", name="   ", code="123456", ttl_minutes=10)
    assert "Olá, colaborador(a)." in message.text_body


@pytest.mark.parametrize("builder", BUILDERS)
def test_logo_only_when_the_frontend_has_a_public_https_url(builder, frontend_url):
    frontend_url("http://localhost:3000")
    assert "<img" not in builder(to="a@souuni.com", name="Ana", code="123456", ttl_minutes=10).html_body

    frontend_url("https://operacao.souuni.com/")
    html = builder(to="a@souuni.com", name="Ana", code="123456", ttl_minutes=10).html_body
    assert 'src="https://operacao.souuni.com/brand/uni-logo.png"' in html
    assert 'alt="UNI Internet"' in html


@pytest.mark.parametrize("builder", BUILDERS)
def test_preheader_shows_the_code_in_the_inbox_preview(builder):
    html = builder(to="a@souuni.com", name="Ana", code="123456", ttl_minutes=10).html_body
    match = re.search(r'display:none[^>]*>([^<]*)<', html)
    assert match and "123456" in match.group(1)


def test_each_email_keeps_its_own_subject_and_wording():
    reset = build_password_reset_code_email(to="a@souuni.com", name="Ana", code="123456", ttl_minutes=10)
    verify = build_email_verification_code_email(to="a@souuni.com", name="Ana", code="123456", ttl_minutes=10)
    assert reset.subject == "Seu código para redefinir a senha - UNI Workspace"
    assert verify.subject == "Confirme seu e-mail - solicitação de acesso UNI Workspace"
    assert "Redefinição de senha" in reset.html_body and "Redefinição de senha" not in verify.html_body
    assert "Confirme seu e-mail" in verify.html_body and "solicitação de acesso" in verify.text_body
