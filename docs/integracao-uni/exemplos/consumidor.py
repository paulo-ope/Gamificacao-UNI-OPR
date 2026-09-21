#!/usr/bin/env python3
"""Consumidor de exemplo — integração de leitura do Cubo de Dados Corporativo / Portal Executivo.

Demonstra, contra a API REST do UNI Workspace (ver ../openapi.yaml):
  1. Autenticação por LOGIN (e-mail/senha da conta de serviço) → Bearer JWT, com renovação
     automática quando expira. Não é um token fixo de longa duração: é o mesmo mecanismo de
     sessão usado por qualquer usuário humano (ver ../acesso.md seção 5).
  2. Consulta filtrada (Operação Analítica: overview por período/regional).
  3. Paginação (SGP Suporte: atendimentos OPA, page/page_size).
  4. Consulta de indicador (Operação Analítica: SLA).
  5. Tratamento de falhas (timeout, erro HTTP, erro de rede) com retry simples e backoff.

Não depende de sessão de navegador. Usa só `requests` (mesma stack Python do backend do projeto).
Não executa nenhuma operação de escrita — este script só faz GET (e o único POST, `/auth/login`,
é a própria autenticação, não uma operação de dado de negócio).

Uso:
    python consumidor.py

Variáveis de ambiente esperadas (ver ../.env.example):
    UNI_API_BASE_URL   - ex.: http://localhost:8000/api
    UNI_API_EMAIL       - e-mail da conta de serviço de leitura (ver ../acesso.md)
    UNI_API_PASSWORD    - senha dessa conta, obtida pelo canal seguro combinado (nunca por chat)
    UNI_API_TOKEN       - opcional: pula o login automático se já houver um Bearer válido em mãos
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any

import requests

DEFAULT_TIMEOUT_SECONDS = 15
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2


class UniApiError(RuntimeError):
    """Erro de negócio/contrato retornado pela API (4xx/5xx já tratado)."""


class UniApiClient:
    """Cliente HTTP mínimo, somente-leitura, para a API do UNI Workspace.

    Não implementa nenhum verbo de escrita de propósito — este consumidor
    de exemplo existe para provar leitura, não para ser um SDK completo.

    Autentica por LOGIN (e-mail/senha), não por token fixo: `POST /auth/login` é chamado uma vez
    na primeira requisição e de novo automaticamente se uma chamada devolver 401 (Bearer expirado)
    — é assim que "renovar a credencial" funciona aqui, sem passo manual algum.
    """

    def __init__(
        self,
        base_url: str,
        *,
        email: str | None = None,
        password: str | None = None,
        token: str | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not base_url:
            raise ValueError("UNI_API_BASE_URL não informado")
        if not token and not (email and password):
            raise ValueError("Informe UNI_API_TOKEN, ou UNI_API_EMAIL + UNI_API_PASSWORD")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._email = email
        self._password = password
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "uni-cubo-corporativo-exemplo/1.0",
            }
        )
        if token:
            self._set_token(token)
        else:
            self._login()

    def _set_token(self, token: str) -> None:
        self._session.headers["Authorization"] = f"Bearer {token}"

    def _login(self) -> None:
        if not (self._email and self._password):
            raise UniApiError(
                "Bearer expirou e não há UNI_API_EMAIL/UNI_API_PASSWORD para renovar sozinho "
                "(só foi passado UNI_API_TOKEN fixo). Gere um novo token manualmente ou informe "
                "email/senha da conta de serviço."
            )
        response = requests.post(
            f"{self.base_url}/auth/login",
            json={"email": self._email, "password": self._password},
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise UniApiError(
                f"Login falhou ({response.status_code}) — verificar UNI_API_EMAIL/UNI_API_PASSWORD "
                "e se a conta de serviço continua ativa (ver acesso.md seção 5)."
            )
        payload = response.json()
        self._set_token(payload["access_token"])
        permissions = payload.get("user", {}).get("permissions", [])
        print(f"  login OK — {len(permissions)} permissões concedidas a esta identidade")

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET com retry simples para erros transitórios (timeout, 502/503/504) e renovação
        automática de sessão em caso de 401 (tenta login de novo uma única vez).

        Erro de autorização (403) e de contrato (404/422) NÃO são reprocessados — indicam um
        problema que retry não resolve.
        """
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        relogged_in = False

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._session.get(url, params=params, timeout=self.timeout)
            except requests.exceptions.Timeout as exc:
                last_exc = exc
                print(f"  [tentativa {attempt}/{MAX_RETRIES}] timeout em {path}, tentando novamente...")
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue
            except requests.exceptions.ConnectionError as exc:
                last_exc = exc
                print(f"  [tentativa {attempt}/{MAX_RETRIES}] falha de conexão em {path}, tentando novamente...")
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue

            if response.status_code == 401:
                if not relogged_in:
                    print(f"  401 em {path} — Bearer expirado/inválido, tentando login de novo...")
                    relogged_in = True
                    self._login()
                    continue
                raise UniApiError(
                    "401 Unauthorized mesmo depois de renovar o login — credencial revogada ou "
                    "inválida. Verificar UNI_API_EMAIL/UNI_API_PASSWORD (ver acesso.md)."
                )
            if response.status_code == 403:
                raise UniApiError(
                    f"403 Forbidden em {path} — a identidade técnica não tem a permissão exigida "
                    "por esta rota. Não expandir permissão sem aprovação (ver acesso.md seção 2)."
                )
            if response.status_code == 404:
                raise UniApiError(f"404 Not Found em {path} — recurso inexistente ou fora do escopo do usuário.")
            if response.status_code == 422:
                raise UniApiError(f"422 Unprocessable Entity em {path} — parâmetros inválidos: {response.text}")
            if response.status_code in (502, 503, 504):
                last_exc = UniApiError(f"{response.status_code} em {path}")
                print(f"  [tentativa {attempt}/{MAX_RETRIES}] erro {response.status_code} em {path}, tentando novamente...")
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue
            if not response.ok:
                raise UniApiError(f"Erro HTTP {response.status_code} em {path}: {response.text[:500]}")

            return response.json()

        raise UniApiError(f"Falha após {MAX_RETRIES} tentativas em {path}: {last_exc}")

    def get_all_pages(self, path: str, params: dict[str, Any], items_key: str = "items", page_size: int = 100) -> list[Any]:
        """Percorre todas as páginas de um endpoint paginado (page/page_size), acumulando itens.

        Atenção (ver ../openapi.yaml e ../catalogo.md): a API não garante consistência
        de página caso os dados mudem durante a consulta (sem cursor estável) — para
        recortes que precisam de exatidão ponto-a-ponto, restringir por período curto
        e reconsultar, não presumir que a soma das páginas é atômica.
        """
        all_items: list[Any] = []
        page = 1
        while True:
            query = dict(params)
            query["page"] = page
            query["page_size"] = page_size
            payload = self.get(path, params=query)
            items = payload.get(items_key, [])
            all_items.extend(items)
            total = payload.get("total")
            if total is not None and len(all_items) >= total:
                break
            if not items or len(items) < page_size:
                break
            page += 1
        return all_items


def demo_consulta_filtrada(client: UniApiClient) -> None:
    print("\n== 2. Consulta filtrada — Operação Analítica: overview por período ==")
    params = {"date_from": "2026-09-01", "date_to": "2026-09-16"}
    overview = client.get("/operations/overview", params=params)
    print(f"  período consultado: {params['date_from']} a {params['date_to']}")
    print(f"  campos retornados (topo): {list(overview.keys())[:10]}")


def demo_paginacao(client: UniApiClient) -> None:
    print("\n== 3. Paginação — SGP Suporte: atendimentos OPA ==")
    params = {
        "date_from": "2026-09-01",
        "date_to": "2026-09-16",
        "date_basis": "opened_at",
    }
    items = client.get_all_pages("/support/opa/attendances", params=params, items_key="items", page_size=100)
    print(f"  total de atendimentos recuperados (todas as páginas): {len(items)}")


def demo_indicador(client: UniApiClient) -> None:
    print("\n== 4. Consulta de indicador — Operação Analítica: SLA ==")
    params = {"date_from": "2026-09-01", "date_to": "2026-09-16"}
    sla = client.get("/operations/sla", params=params)
    print(f"  indicador SLA (ver definição em ../catalogo.md#moperationssla_rate): {sla}")


def demo_tratamento_de_falha(client: UniApiClient) -> None:
    print("\n== 5. Tratamento de falha — rota inexistente (404 esperado) ==")
    try:
        client.get("/operations/rota-que-nao-existe")
    except UniApiError as exc:
        print(f"  falha tratada corretamente: {exc}")


def main() -> int:
    base_url = os.environ.get("UNI_API_BASE_URL", "")
    email = os.environ.get("UNI_API_EMAIL", "")
    password = os.environ.get("UNI_API_PASSWORD", "")
    token = os.environ.get("UNI_API_TOKEN", "")

    print("== 1. Autenticação ==")
    print(f"  base_url: {base_url or '(não definido)'}")
    print(f"  modo: {'token fixo (UNI_API_TOKEN)' if token else 'login automático (UNI_API_EMAIL/PASSWORD)'}")

    if not base_url or not (token or (email and password)):
        print(
            "\nUNI_API_BASE_URL e/ou credenciais não definidos. "
            "Copie ../.env.example para .env local e preencha com uma credencial válida "
            "(ver ../acesso.md seção 5)."
        )
        return 1

    client = UniApiClient(base_url=base_url, email=email or None, password=password or None, token=token or None)

    try:
        demo_consulta_filtrada(client)
        demo_paginacao(client)
        demo_indicador(client)
        demo_tratamento_de_falha(client)
    except UniApiError as exc:
        print(f"\nErro de API não recuperável: {exc}")
        return 2

    print("\nOK — todas as demonstrações executaram sem erro.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
