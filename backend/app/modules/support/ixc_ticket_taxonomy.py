"""Resolução de motivo (`subject_id`) -> tema -> categoria - Fase 0/1 do plano de evolução
analítica do Atendimento IXC (2026-09-14).

Fase 0: a tabela `support_ixc_taxonomy_mappings` existe mas está VAZIA - toda resolução cai no
fallback `NAO_MAPEADO` até alguém popular o de-para (fora do escopo desta fase). Funções puras,
sem side-effect, pra poderem ser chamadas tanto pelos endpoints de drill (Fase 2) quanto pela
camada de IA (Fase 5) sem duplicar a lógica de "qual linha está vigente".
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import SupportIxcTaxonomyMapping

NAO_MAPEADO = "NAO_MAPEADO"

_UNMAPPED: dict[str, Any] = {
    "theme_id": NAO_MAPEADO,
    "theme_label": NAO_MAPEADO,
    "category_id": NAO_MAPEADO,
    "category_label": NAO_MAPEADO,
    # Peso-base 0 (não 100) pra um motivo não mapeado - "sem taxonomia" não deve virar sinal de
    # risco por acidente (ver `ixc_ticket_text_signal.py`, que soma ajustes em cima deste peso).
    "risk_weight": 0,
}


def resolve_theme_for_subject(db: Session, subject_id: str | None, *, as_of: date | None = None) -> dict[str, Any]:
    """Mapeamento vigente pra um `subject_id`: a linha daquele motivo com o MAIOR
    `effective_from &lt;= as_of` (hoje, se omitido) - nunca a mais recente cadastrada, a mais
    recente VÁLIDA na data de referência (permite reconstruir a taxonomia que valia num período
    passado). Sem `subject_id`, ou sem nenhuma linha vigente (tabela vazia ou motivo ainda não
    mapeado) -&gt; `NAO_MAPEADO` (e `risk_weight=0`) nos campos, nunca `None` - quem consome não
    precisa tratar "sem taxonomia" como um caso `null` à parte."""
    if not subject_id:
        return dict(_UNMAPPED)

    reference_date = as_of or date.today()
    row = db.scalar(
        select(SupportIxcTaxonomyMapping)
        .where(
            SupportIxcTaxonomyMapping.subject_id == subject_id,
            SupportIxcTaxonomyMapping.effective_from <= reference_date,
        )
        .order_by(SupportIxcTaxonomyMapping.effective_from.desc())
        .limit(1)
    )
    if row is None:
        return dict(_UNMAPPED)
    return {
        "theme_id": row.theme_id,
        "theme_label": row.theme_label,
        "category_id": row.category_id,
        "category_label": row.category_label,
        "risk_weight": row.risk_weight,
    }


def taxonomy_coverage_pct(db: Session, subject_ids: list[str | None], *, as_of: date | None = None) -> float | None:
    """% dos `subject_ids` informados que têm mapeamento vigente (não caem em `NAO_MAPEADO`).
    `None` quando a lista vem vazia - não é "0% de cobertura", é "não há o que cobrir" (mesma
    distinção que o resto do módulo já faz pra `coverage_pct`/`tickets_per_1000_contracts`: nunca
    fingir um número quando o denominador é zero)."""
    ids = [subject_id for subject_id in subject_ids if subject_id]
    if not ids:
        return None
    mapped = sum(1 for subject_id in ids if resolve_theme_for_subject(db, subject_id, as_of=as_of)["theme_id"] != NAO_MAPEADO)
    return round(mapped / len(ids) * 100, 1)


def current_theme_map(db: Session, *, as_of: date | None = None) -> dict[str, dict[str, Any]]:
    """Mapeamento vigente de TODOS os `subject_id` cadastrados de uma vez (`subject_id ->
    tema/categoria`) - evita N chamadas de `resolve_theme_for_subject` quando o chamador precisa
    resolver vários motivos ao mesmo tempo (ex.: `filter_options`, que monta o filtro por tema
    pra tela). Mesma regra de vigência (maior `effective_from <= as_of` por `subject_id`), só que
    calculada em Python sobre UMA query só, não uma por motivo."""
    reference_date = as_of or date.today()
    rows = db.scalars(
        select(SupportIxcTaxonomyMapping)
        .where(SupportIxcTaxonomyMapping.effective_from <= reference_date)
        .order_by(SupportIxcTaxonomyMapping.subject_id.asc(), SupportIxcTaxonomyMapping.effective_from.desc())
    ).all()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.subject_id in result:
            continue  # já viu a linha vigente daquele subject_id (a primeira, dado o ORDER BY desc)
        result[row.subject_id] = {
            "theme_id": row.theme_id,
            "theme_label": row.theme_label,
            "category_id": row.category_id,
            "category_label": row.category_label,
            "risk_weight": row.risk_weight,
        }
    return result


def list_taxonomy_mappings(db: Session) -> list[dict[str, Any]]:
    """Todas as linhas cadastradas (todas as versões, não só a vigente) - usado pelo endpoint de
    leitura da Fase 0. Ordenado por motivo e depois pela vigência mais recente primeiro, pra quem
    olhar a lista já ver o mapeamento atual de cada `subject_id` no topo do seu grupo."""
    rows = db.scalars(
        select(SupportIxcTaxonomyMapping).order_by(
            SupportIxcTaxonomyMapping.subject_id.asc(),
            SupportIxcTaxonomyMapping.effective_from.desc(),
        )
    ).all()
    return [
        {
            "subject_id": row.subject_id,
            "theme_id": row.theme_id,
            "theme_label": row.theme_label,
            "category_id": row.category_id,
            "category_label": row.category_label,
            "version": row.version,
            "effective_from": row.effective_from.isoformat(),
            "risk_weight": row.risk_weight,
        }
        for row in rows
    ]
