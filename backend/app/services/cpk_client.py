from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger("cpk_client")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class CpkApiError(RuntimeError):
    """Erro de comunicação com a API de CPK da frota (rede, autenticação ou formato de resposta)."""


class CpkClient:
    """Cliente HTTP puro para a API de parceiro de CPK (BI Frota UNI).

    Só autenticação e leitura do endpoint estruturado - nenhuma regra de negócio da gamificação
    aqui (isso fica em cpk_health.py, que decide o que fazer com o `status` de cada regional)."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0) -> None:
        if not base_url:
            raise CpkApiError("CPK_API_BASE_URL não configurado.")
        if not api_key:
            raise CpkApiError("CPK_API_KEY não configurado.")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self._api_key}

    def get_relatorio_estruturado(self, ano: int, mes: int) -> dict[str, Any]:
        started_at = time.monotonic()
        try:
            response = httpx.get(
                f"{self._base_url}/api/v1/cpk/relatorio-estruturado",
                headers=self._headers(),
                params={"ano": ano, "mes": mes},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            duration_ms = round((time.monotonic() - started_at) * 1000)
            logger.warning("FALHA ano=%s mes=%s duracao_ms=%s erro=%s", ano, mes, duration_ms, exc)
            raise CpkApiError(f"Falha ao consultar o relatório de CPK ({ano}/{mes}): {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise CpkApiError(
                f"A API de CPK respondeu em formato inválido para {ano}/{mes} (HTTP {response.status_code})."
            ) from exc
        if not isinstance(body, dict) or "regionais" not in body:
            keys = list(body.keys()) if isinstance(body, dict) else type(body).__name__
            raise CpkApiError(f"Resposta inesperada da API de CPK para {ano}/{mes} (chaves recebidas: {keys}).")

        duration_ms = round((time.monotonic() - started_at) * 1000)
        logger.info(
            "ano=%s mes=%s mes_fechado=%s regionais=%s duracao_ms=%s",
            ano, mes, body.get("mes_fechado"), len(body.get("regionais") or []), duration_ms,
        )
        return body


def get_cpk_client() -> CpkClient:
    settings = get_settings()
    return CpkClient(base_url=settings.cpk_api_base_url, api_key=settings.cpk_api_key)
