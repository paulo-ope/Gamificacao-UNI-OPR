from __future__ import annotations

from app.services.text_normalize import normalize_place_name


def test_normalize_place_name_merges_case_variants():
    assert normalize_place_name("CENTRO") == "Centro"
    assert normalize_place_name("centro") == "Centro"
    assert normalize_place_name("Centro") == "Centro"


def test_normalize_place_name_collapses_internal_whitespace():
    assert normalize_place_name("ZONA   RURAL") == "Zona Rural"
    assert normalize_place_name("  Beira Rio  ") == "Beira Rio"


def test_normalize_place_name_preserves_accents():
    assert normalize_place_name("JEQUITIBÁ") == "Jequitibá"
    assert normalize_place_name("são cristóvão") == "São Cristóvão"


def test_normalize_place_name_returns_none_for_empty():
    assert normalize_place_name(None) is None
    assert normalize_place_name("") is None
    assert normalize_place_name("   ") is None


def test_normalize_place_name_does_not_merge_genuinely_different_words():
    # "Rural" e "Zona Rural" são textos diferentes - normalização de caixa não deve inventar
    # correspondência entre palavras que não são a mesma.
    assert normalize_place_name("Rural") != normalize_place_name("Zona Rural")
