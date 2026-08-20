from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Iterator

import httpx

from app.core.config import get_settings

logger = logging.getLogger("opa_client")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class OpaApiError(RuntimeError):
    """Erro de comunicacao com a API do OPA Suite."""


@dataclass
class OpaPage:
    records: list[dict[str, Any]]
    total: int | None
    limit: int
    skip: int


class OpaClient:
    """Cliente HTTP puro da API OPA Suite.

    Este modulo nao calcula indicadores nem conhece regra de negocio da operacao. Ele so autentica,
    pagina, valida o formato basico e devolve payload bruto para a camada de ingestion.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        verify_ssl: bool = True,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not base_url:
            raise OpaApiError("OPA_API_BASE_URL não configurado.")
        if not token:
            raise OpaApiError("OPA_API_TOKEN não configurado.")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._verify_ssl = verify_ssl
        self._timeout = timeout
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        safe_params = {
            key: value
            for key, value in (params or {}).items()
            if value not in (None, "")
        }
        started_at = time.monotonic()
        try:
            with httpx.Client(
                timeout=self._timeout,
                verify=self._verify_ssl,
                transport=self._transport,
            ) as client:
                response = client.request(
                    method,
                    f"{self._base_url}/{path.lstrip('/')}",
                    headers=self._headers(),
                    params=safe_params,
                    json=json_body,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            duration_ms = round((time.monotonic() - started_at) * 1000)
            logger.warning(
                "FALHA method=%s path=%s params=%s body=%s duracao_ms=%s erro=%s",
                method,
                path,
                safe_params,
                json_body,
                duration_ms,
                exc,
            )
            raise OpaApiError(f"Falha ao consultar a API OPA Suite em '{path}': {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            duration_ms = round((time.monotonic() - started_at) * 1000)
            content_type = response.headers.get("content-type", "não informado").split(";", 1)[0]
            logger.warning(
                "RESPOSTA_INVALIDA path=%s status=%s content_type=%s duracao_ms=%s",
                path,
                response.status_code,
                content_type,
                duration_ms,
            )
            raise OpaApiError(
                f"O OPA Suite respondeu em formato inválido para '{path}' "
                f"(HTTP {response.status_code}, tipo {content_type})."
            ) from exc

        duration_ms = round((time.monotonic() - started_at) * 1000)
        logger.info("method=%s path=%s params=%s body=%s duracao_ms=%s", method, path, safe_params, json_body, duration_ms)
        return body

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
        return self._request("GET", path, params=params)

    def _get_with_body(self, path: str, *, json_body: dict[str, Any]) -> dict[str, Any] | list[Any]:
        return self._request("GET", path, json_body=json_body)

    @staticmethod
    def _extract_records(body: dict[str, Any] | list[Any]) -> tuple[list[dict[str, Any]], int | None]:
        if isinstance(body, list):
            return [item for item in body if isinstance(item, dict)], len(body)
        if not isinstance(body, dict):
            raise OpaApiError(f"Resposta inesperada do OPA Suite: {type(body).__name__}.")

        total = None
        for total_key in ("total", "count", "quantidade", "recordsTotal"):
            if total_key in body:
                try:
                    total = int(body[total_key])
                    break
                except (TypeError, ValueError):
                    total = None

        for key in ("data", "items", "results", "registros", "records", "atendimentos"):
            value = body.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)], total

        if all(isinstance(value, dict) for value in body.values()):
            return [value for value in body.values() if isinstance(value, dict)], total

        raise OpaApiError(f"Resposta inesperada do OPA Suite (chaves recebidas: {list(body.keys())}).")

    def list_attendances(
        self,
        *,
        opened_after: str | None = None,
        opened_before: str | None = None,
        closed_after: str | None = None,
        closed_before: str | None = None,
        limit: int = 100,
        skip: int = 0,
    ) -> OpaPage:
        filters = {
            key: value
            for key, value in {
                "dataInicialAbertura": opened_after,
                "dataFinalAbertura": opened_before,
                "dataInicialEncerramento": closed_after,
                "dataFinalEncerramento": closed_before,
            }.items()
            if value not in (None, "")
        }
        body = {
            "filter": filters,
            "options": {
                "limit": limit,
                "skip": skip,
            },
        }
        response_body = self._get_with_body("/api/v1/atendimento", json_body=body)
        records, total = self._extract_records(response_body)
        logger.info("atendimentos_recebidos=%s total_no_filtro=%s limit=%s skip=%s", len(records), total, limit, skip)
        return OpaPage(records=records, total=total, limit=limit, skip=skip)

    def iter_attendances(
        self,
        *,
        opened_after: str | None = None,
        opened_before: str | None = None,
        closed_after: str | None = None,
        closed_before: str | None = None,
        limit: int = 100,
        max_pages: int = 50,
        max_records: int = 5000,
    ) -> Iterator[dict[str, Any]]:
        skip = 0
        seen = 0
        pages = 0
        while pages < max_pages:
            page = self.list_attendances(
                opened_after=opened_after,
                opened_before=opened_before,
                closed_after=closed_after,
                closed_before=closed_before,
                limit=limit,
                skip=skip,
            )
            pages += 1
            if not page.records:
                return
            remaining = max_records - seen
            if remaining <= 0:
                logger.warning("importacao_interrompida_por_limite max_records=%s pages=%s", max_records, pages)
                return
            records = page.records[:remaining]
            yield from records
            seen += len(records)
            if seen >= max_records:
                logger.warning("importacao_interrompida_por_limite max_records=%s pages=%s", max_records, pages)
                return
            if page.total is not None and seen >= page.total:
                return
            if len(page.records) < limit:
                return
            skip += len(page.records)

    def list_collection(
        self,
        path: str,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        max_records: int = 5000,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        skip = 0
        while len(records) < max_records:
            body = {
                "filter": {
                    key: value
                    for key, value in (filters or {}).items()
                    if value not in (None, "")
                },
                "options": {
                    "limit": limit,
                    "skip": skip,
                },
            }
            response_body = self._get_with_body(path, json_body=body)
            page_records, total = self._extract_records(response_body)
            if not page_records:
                return records

            remaining = max_records - len(records)
            records.extend(page_records[:remaining])
            if total is not None and len(records) >= total:
                return records
            if total is None and len(page_records) < limit:
                return records
            skip += len(page_records)

        logger.warning("colecao_interrompida_por_limite path=%s max_records=%s", path, max_records)
        return records

    def list_users(self) -> list[dict[str, Any]]:
        return self.list_collection("/api/v1/usuario/")

    def list_reasons(self) -> list[dict[str, Any]]:
        return self.list_collection("/api/v1/atendimento/motivo")

    def list_departments(self) -> list[dict[str, Any]]:
        return self.list_collection("/api/v1/departamento/")

    def list_tags(self) -> list[dict[str, Any]]:
        return self.list_collection("/api/v1/etiqueta/")

    def list_clients(self) -> list[dict[str, Any]]:
        return self.list_collection("/api/v1/cliente/", max_records=50000)

    def get_attendance_detail(self, source_id: str) -> dict[str, Any]:
        body = self._get(f"/api/v1/atendimento/{source_id}")
        if isinstance(body, list):
            for item in body:
                if isinstance(item, dict):
                    return item
            raise OpaApiError(f"Detalhe do atendimento '{source_id}' veio vazio.")
        if not isinstance(body, dict):
            raise OpaApiError(f"Detalhe inesperado do atendimento '{source_id}': {type(body).__name__}.")

        # O detalhe do OPA pode vir envelopado como {status, code, data}, ao
        # contrário das listagens, em que `data` é uma lista paginada.
        detail = body.get("data")
        if isinstance(detail, dict):
            return detail
        if isinstance(detail, list):
            for item in detail:
                if isinstance(item, dict):
                    return item
            raise OpaApiError(f"Detalhe do atendimento '{source_id}' veio vazio.")

        records, _total = self._extract_records(body)
        if len(records) == 1 and not any(key in body for key in ("_id", "id", "protocolo", "date")):
            return records[0]
        return body


def get_opa_client() -> OpaClient:
    settings = get_settings()
    return OpaClient(
        base_url=settings.opa_api_base_url,
        token=settings.opa_api_token,
        verify_ssl=settings.opa_api_verify_ssl,
    )
