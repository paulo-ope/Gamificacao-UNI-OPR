"""Envelope `meta` para respostas analíticas - Fase 1, item 1 do plano de confiabilidade de dado
(pedido do usuário em 2026-08-15). Estritamente aditivo: não muda a lógica de filtro nenhuma,
só torna observável o que já acontece hoje - o que foi de fato aplicado, o que foi recebido mas
não se aplica àquele contexto (com motivo, nunca descartado em silêncio), e qualquer condição que
possa mudar a interpretação do resultado (cobertura parcial, fallback, ambiguidade).

Filtro inválido continua não sendo erro nesta etapa (decisão explícita do usuário) - isso fica
para quando o contrato único de filtros for definido e aprovado."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict


class IgnoredFilter(TypedDict):
    field: str
    reason: str


class ResponseMeta(TypedDict):
    applied_filters: dict[str, Any]
    ignored_filters: list[IgnoredFilter]
    # dict, não str - todo warning é estruturado com um "code" (ex.: DEPRECATED_FILTER_ALIAS,
    # PARTIAL_DIMENSION_COVERAGE, ver docs/proposta-filter-contract-v1.md §5) e campos extras que
    # variam por code - por isso dict[str, Any] livre em vez de um TypedDict fixo por warning.
    warnings: list[dict[str, Any]]
    generated_at: datetime
    source_last_sync: datetime | None


def build_meta(
    *,
    applied_filters: dict[str, Any] | None = None,
    ignored_filters: list[IgnoredFilter] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    source_last_sync: datetime | None = None,
) -> ResponseMeta:
    # Remove filtros vazios (list vazia, None, "") de `applied_filters` - um filtro que o chamador
    # nem passou não é "aplicado", é ausente; sem isso, toda resposta carregaria uma dezena de
    # chaves com valor vazio, escondendo os filtros que de fato importam.
    cleaned_filters = {key: value for key, value in (applied_filters or {}).items() if value not in (None, "", [])}
    return {
        "applied_filters": cleaned_filters,
        "ignored_filters": ignored_filters or [],
        "warnings": warnings or [],
        "generated_at": datetime.now(timezone.utc),
        "source_last_sync": source_last_sync,
    }
