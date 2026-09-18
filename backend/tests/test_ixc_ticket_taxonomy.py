"""Fase 0 do plano de evolução analítica do Atendimento IXC (2026-09-14): resolução de motivo
(subject_id) -> tema -> categoria. A tabela nasce vazia - estes testes cobrem o fallback
NAO_MAPEADO e a regra de vigência por `effective_from`, não uma taxonomia real (que ainda não foi
definida)."""

from __future__ import annotations

from datetime import date

from app.modules.support import ixc_ticket_taxonomy
from app.modules.support.models import SupportIxcTaxonomyMapping


def _mapping(db, *, subject_id, theme_id, theme_label, category_id, category_label, effective_from, version=1, risk_weight=0):
    row = SupportIxcTaxonomyMapping(
        subject_id=subject_id,
        theme_id=theme_id,
        theme_label=theme_label,
        category_id=category_id,
        category_label=category_label,
        version=version,
        effective_from=effective_from,
        risk_weight=risk_weight,
    )
    db.add(row)
    return row


def test_resolve_theme_for_subject_falls_back_to_nao_mapeado_with_empty_table(db_session):
    resolved = ixc_ticket_taxonomy.resolve_theme_for_subject(db_session, "90")

    assert resolved == {
        "theme_id": ixc_ticket_taxonomy.NAO_MAPEADO,
        "theme_label": ixc_ticket_taxonomy.NAO_MAPEADO,
        "category_id": ixc_ticket_taxonomy.NAO_MAPEADO,
        "category_label": ixc_ticket_taxonomy.NAO_MAPEADO,
        "risk_weight": 0,
    }


def test_resolve_theme_for_subject_falls_back_to_nao_mapeado_without_subject_id(db_session):
    assert ixc_ticket_taxonomy.resolve_theme_for_subject(db_session, None)["theme_id"] == ixc_ticket_taxonomy.NAO_MAPEADO


def test_resolve_theme_for_subject_returns_mapped_row_when_it_exists(db_session):
    _mapping(
        db_session,
        subject_id="90",
        theme_id="conectividade",
        theme_label="Conectividade",
        category_id="operacoes",
        category_label="Operações",
        effective_from=date(2026, 1, 1),
        risk_weight=95,
    )
    db_session.commit()

    resolved = ixc_ticket_taxonomy.resolve_theme_for_subject(db_session, "90", as_of=date(2026, 9, 14))

    assert resolved == {
        "theme_id": "conectividade",
        "theme_label": "Conectividade",
        "category_id": "operacoes",
        "category_label": "Operações",
        "risk_weight": 95,
    }


def test_resolve_theme_for_subject_picks_the_latest_effective_row_not_the_future_one(db_session):
    """Achado do plano (2026-09-14): vigência é por `effective_from &lt;= as_of`, não "a última
    linha cadastrada" - uma correção agendada pro futuro não pode valer antes da hora."""
    _mapping(
        db_session, subject_id="90", theme_id="conectividade", theme_label="Conectividade",
        category_id="operacoes", category_label="Operações", effective_from=date(2026, 1, 1),
    )
    _mapping(
        db_session, subject_id="90", theme_id="triagem", theme_label="Triagem Operacional",
        category_id="operacoes", category_label="Operações", effective_from=date(2099, 1, 1), version=2,
    )
    db_session.commit()

    resolved = ixc_ticket_taxonomy.resolve_theme_for_subject(db_session, "90", as_of=date(2026, 9, 14))

    assert resolved["theme_id"] == "conectividade"


def test_resolve_theme_for_subject_respects_as_of_for_historical_lookups(db_session):
    _mapping(
        db_session, subject_id="90", theme_id="conectividade_v1", theme_label="Conectividade (v1)",
        category_id="operacoes", category_label="Operações", effective_from=date(2026, 1, 1),
    )
    _mapping(
        db_session, subject_id="90", theme_id="conectividade_v2", theme_label="Conectividade (v2)",
        category_id="operacoes", category_label="Operações", effective_from=date(2026, 6, 1), version=2,
    )
    db_session.commit()

    assert ixc_ticket_taxonomy.resolve_theme_for_subject(db_session, "90", as_of=date(2026, 3, 1))["theme_id"] == "conectividade_v1"
    assert ixc_ticket_taxonomy.resolve_theme_for_subject(db_session, "90", as_of=date(2026, 7, 1))["theme_id"] == "conectividade_v2"


def test_taxonomy_coverage_pct_is_none_for_empty_list(db_session):
    assert ixc_ticket_taxonomy.taxonomy_coverage_pct(db_session, []) is None


def test_taxonomy_coverage_pct_computes_mapped_fraction(db_session):
    _mapping(
        db_session, subject_id="90", theme_id="conectividade", theme_label="Conectividade",
        category_id="operacoes", category_label="Operações", effective_from=date(2026, 1, 1),
    )
    db_session.commit()

    # "90" mapeado, "91" e "92" não - 1 de 3 = 33,3%.
    coverage = ixc_ticket_taxonomy.taxonomy_coverage_pct(db_session, ["90", "91", "92"])

    assert coverage == 33.3


def test_list_taxonomy_mappings_is_empty_by_default(db_session):
    assert ixc_ticket_taxonomy.list_taxonomy_mappings(db_session) == []


def test_list_taxonomy_mappings_returns_all_versions_ordered(db_session):
    _mapping(
        db_session, subject_id="90", theme_id="conectividade_v1", theme_label="Conectividade (v1)",
        category_id="operacoes", category_label="Operações", effective_from=date(2026, 1, 1),
    )
    _mapping(
        db_session, subject_id="90", theme_id="conectividade_v2", theme_label="Conectividade (v2)",
        category_id="operacoes", category_label="Operações", effective_from=date(2026, 6, 1), version=2,
    )
    db_session.commit()

    rows = ixc_ticket_taxonomy.list_taxonomy_mappings(db_session)

    assert [row["theme_id"] for row in rows] == ["conectividade_v2", "conectividade_v1"]
