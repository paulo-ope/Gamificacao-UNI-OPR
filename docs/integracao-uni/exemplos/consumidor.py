#!/usr/bin/env python3
"""Consumidor de exemplo — integração de leitura do Cubo de Dados Corporativo / Portal Executivo.

Demonstra, contra a API REST do UNI Workspace (ver ../openapi.yaml):
  1. Autenticação via token de API (header Authorization: Bearer) lido de variável de ambiente
     — nenhuma credencial fica hardcoded neste arquivo.
  2. Consulta filtrada (Operação Analítica: overview por período/regional).
  3. Paginação (SGP Suporte: atendimentos OPA, page/page_size).
  4. Consulta de indicador (Operação Analítica: SLA).
  5. Tratamento de falhas (timeout, erro HTTP, erro de rede) com retry simples e backoff.

Não depende de sessão de navegador. Usa só `requests` (mesma stack Python do backend do projeto).
Não executa nenhuma operação de escrita — este script só faz GET.

Uso:
    python consumidor.py

Variáveis de ambiente esperadas (ver ../.env.example):
    UNI_API_BASE_URL   - ex.: http://localhost:8000/api
    UNI_API_TOKEN       - token Bearer da identidade técnica de leitura (ver ../acesso.md)
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
    """

    def __init__(self, base_url: str, token: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        if not base_url:
            raise ValueError("UNI_API_BASE_URL não informado")
        if not token:
            raise ValueError("UNI_API_TOKEN não informado")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "uni-cubo-corporativo-exemplo/1.0",
            }
        )

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET com retry simples para erros transitórios (timeout, 502/503/504).

        Erros de autenticação/autorização (401/403) e de contrato (404/422)
        NÃO são reprocessados — indicam um problema que retry não resolve.
        """
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None

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
                raise UniApiError(
                    "401 Unauthorized — token ausente, expirado ou inválido. "
                    "Verificar UNI_API_TOKEN e a validade/revogação da credencial (ver acesso.md)."
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
    token = os.environ.get("UNI_API_TOKEN", "")

    print("== 1. Autenticação ==")
    print(f"  base_url: {base_url or '(não definido)'}")
    print(f"  token presente: {'sim' if token else 'não'}")

    if not base_url or not token:
        print(
            "\nUNI_API_BASE_URL e/ou UNI_API_TOKEN não definidos. "
            "Copie ../.env.example para .env local e preencha com uma credencial válida "
            "(ver ../acesso.md — provisionamento ainda pendente nesta análise)."
        )
        return 1

    client = UniApiClient(base_url=base_url, token=token)

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
