"""Regression tests for backend/app/services/regional.py."""
from app.services.regional import (
    ROLIM_REGIONAL,
    SAO_FRANCISCO_REGIONAL,
    normalize_regional,
    normalize_regional_grouped,
)


def test_sao_felipe_is_grouped_with_rolim_for_gamification():
    """Decisao do usuario (2026-07-31): Sao Felipe D'Oeste nao tem base de CPK propria (a frota
    e custeada pela garagem de Rolim de Moura) - a gamificacao passa a apurar e pagar Sao Felipe
    junto com Rolim de Moura (SLA, ranking, saude operacional, CPK e pagamento), mesmo criterio
    ja usado para agrupar Sao Miguel/Seringueiras dentro de Sao Francisco."""
    assert normalize_regional_grouped("UNI - SAO FELIPE DOESTE") == ROLIM_REGIONAL
    assert normalize_regional_grouped("13") == ROLIM_REGIONAL, "id_filial 13 (Sao Felipe) tambem deve agrupar"
    assert normalize_regional_grouped("Sao Felipe") == ROLIM_REGIONAL
    assert normalize_regional_grouped(ROLIM_REGIONAL) == ROLIM_REGIONAL, "Rolim continua sendo ela mesma"


def test_sao_felipe_keeps_its_own_identity_for_operacao_analitica():
    """A identidade granular (usada pela Operacao Analitica, nao pela gamificacao) NAO agrupa -
    Sao Felipe continua sendo Sao Felipe pra quem precisa da filial real."""
    assert normalize_regional("UNI - SAO FELIPE DOESTE") == "UNI - SAO FELIPE DOESTE"
    assert normalize_regional("13") == "UNI - SAO FELIPE DOESTE"


def test_sao_francisco_grouping_still_works_after_adding_rolim_alias():
    """Sanity check: adicionar o agrupamento de Sao Felipe/Rolim nao pode ter quebrado o
    agrupamento existente de Sao Francisco (Sao Miguel + Seringueiras + Sao Francisco do
    Guapore)."""
    assert normalize_regional_grouped("UNI - SAO MIGUEL DO GUAPORE") == SAO_FRANCISCO_REGIONAL
    assert normalize_regional_grouped("UNI - SERINGUEIRAS") == SAO_FRANCISCO_REGIONAL
    assert normalize_regional_grouped("16") == SAO_FRANCISCO_REGIONAL
    assert normalize_regional_grouped("17") == SAO_FRANCISCO_REGIONAL
