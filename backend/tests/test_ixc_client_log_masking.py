"""Fase 2C - convite inteligente por CPF integrado ao IXC (pedido do usuário em 2026-08-29, ver
docs/portal-ciclo-vida-conta-colaborador.md). Achado real que motivou esta correção: antes de
existir uma busca por CPF, `IxcClient.list`'s `safe_filter_summary` só logava filtros inofensivos
(ids, datas, status) - assim que a busca por `funcionarios.cpf_cnpj` passou a existir, o mesmo
código logaria o CPF em texto puro no log do container em nível INFO. Este arquivo prova que isso
NUNCA acontece, para CPF/CNPJ, e-mail e telefone.

`caplog` sozinho não enxerga o logger "ixc_client": ele fixa `propagate = False` de propósito (pra
sempre aparecer no log do container, independente da configuração de logging do resto da
aplicação) - por isso os testes aqui anexam um handler próprio direto nesse logger, em vez de
depender da propagação até a raiz que o `caplog` escuta por padrão.
"""

import logging

from app.services.ixc_client import IxcClient


def _fake_json_response(records: list[dict], total: int | None = None):
    body = {"registros": records, "total": total if total is not None else len(records)}
    return type(
        "FakeResponse",
        (),
        {
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "raise_for_status": lambda self: None,
            "json": lambda self: body,
        },
    )()


class _CapturedRecords(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


def _capture_ixc_client_log():
    logger = logging.getLogger("ixc_client")
    handler = _CapturedRecords()
    logger.addHandler(handler)
    return logger, handler


def test_cpf_filter_is_masked_in_log(monkeypatch):
    monkeypatch.setattr("app.services.ixc_client.httpx.post", lambda *a, **k: _fake_json_response([{"id": "1"}]))
    client = IxcClient("https://ixc.example.test", "token")
    logger, handler = _capture_ixc_client_log()
    try:
        client.list("funcionarios", grid_param=[{"TB": "funcionarios.cpf_cnpj", "OP": "=", "P": "52998224725"}])
    finally:
        logger.removeHandler(handler)

    log_text = "\n".join(handler.lines)
    assert "52998224725" not in log_text
    assert "***.***.***-25" in log_text


def test_cnpj_filter_is_masked_in_log(monkeypatch):
    monkeypatch.setattr("app.services.ixc_client.httpx.post", lambda *a, **k: _fake_json_response([{"id": "1"}]))
    client = IxcClient("https://ixc.example.test", "token")
    logger, handler = _capture_ixc_client_log()
    try:
        client.list("cliente", grid_param=[{"TB": "cliente.cnpj_cpf", "OP": "=", "P": "11144477735"}])
    finally:
        logger.removeHandler(handler)

    log_text = "\n".join(handler.lines)
    assert "11144477735" not in log_text
    assert "***.***.***-35" in log_text


def test_email_filter_is_masked_in_log(monkeypatch):
    monkeypatch.setattr("app.services.ixc_client.httpx.post", lambda *a, **k: _fake_json_response([{"id": "1"}]))
    client = IxcClient("https://ixc.example.test", "token")
    logger, handler = _capture_ixc_client_log()
    try:
        client.list("funcionarios", grid_param=[{"TB": "funcionarios.email", "OP": "=", "P": "fulano.secreto@exemplo.com"}])
    finally:
        logger.removeHandler(handler)

    log_text = "\n".join(handler.lines)
    assert "fulano.secreto@exemplo.com" not in log_text
    assert "@exemplo.com" in log_text  # domínio pode ficar visível, o endereço completo não


def test_phone_filter_is_masked_in_log(monkeypatch):
    monkeypatch.setattr("app.services.ixc_client.httpx.post", lambda *a, **k: _fake_json_response([{"id": "1"}]))
    client = IxcClient("https://ixc.example.test", "token")
    logger, handler = _capture_ixc_client_log()
    try:
        client.list("funcionarios", grid_param=[{"TB": "funcionarios.fone_celular", "OP": "=", "P": "69999990000"}])
    finally:
        logger.removeHandler(handler)

    log_text = "\n".join(handler.lines)
    assert "69999990000" not in log_text


def test_non_sensitive_filters_still_log_useful_summary(monkeypatch):
    """A correção não pode quebrar os logs úteis de tabela/página/rp/total/duração nem os filtros
    que já eram inofensivos (ids, datas, status)."""
    monkeypatch.setattr("app.services.ixc_client.httpx.post", lambda *a, **k: _fake_json_response([{"id": "1"}], total=1))
    client = IxcClient("https://ixc.example.test", "token")
    logger, handler = _capture_ixc_client_log()
    try:
        client.list("su_oss_chamado", grid_param=[{"TB": "su_oss_chamado.id", "OP": ">=", "P": "100"}], page=2, rp=50)
    finally:
        logger.removeHandler(handler)

    log_text = "\n".join(handler.lines)
    assert "su_oss_chamado.id >= 100" in log_text
    assert "tabela=su_oss_chamado" in log_text
    assert "pagina=2" in log_text
    assert "rp=50" in log_text
    assert "total_no_filtro=1" in log_text
