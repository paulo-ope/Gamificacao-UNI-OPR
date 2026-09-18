"""Regression tests for backend/app/services/regional.py."""
from app.services.regional import (
    ROLIM_REGIONAL,
    SAO_FRANCISCO_REGIONAL,
    granular_regionals_for_group,
    normalize_regional,
    normalize_regional_grouped,
    regional_group_options,
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


def test_unknown_numeric_filial_code_does_not_leak_as_pseudo_regional():
    """Bug confirmado: id_filial numerico fora de REGIONAL_CODE_MAP e fora de
    INVALID_REGIONAL_CODES (ex.: "20", "23") vazava cru como se fosse nome de regional,
    aparecendo como uma opcao de filtro extra e desconectada em filter_options. Deve cair em
    "NAO IDENTIFICADO" até ser mapeado."""
    assert normalize_regional("20") == "NAO IDENTIFICADO"
    assert normalize_regional("23") == "NAO IDENTIFICADO"
    assert normalize_regional("999") == "NAO IDENTIFICADO"


def test_non_numeric_unmapped_value_still_passes_through():
    """Nomes de regional que já vêm como texto (não códigos numéricos crus) continuam
    passando sem alteração - a mudança é restrita a códigos puramente numéricos."""
    assert normalize_regional("UNI - JI PARANA") == "UNI - JI PARANA"


def test_ji_parana_hyphen_alias_normalizes_to_canonical_spelling():
    """Bug confirmado na auditoria de frontend de 2026-09-14: `operations_responsible_assignments`
    (atribuicao manual de responsavel/regional) tinha 36 registros gravados como
    "UNI - JI-PARANA" (hifen), nunca passados por REGIONAL_CODE_MAP (que so normaliza id_filial
    numerico) - apareciam como uma segunda opcao no filtro de regional da Gestao Integrada, a
    mesma filial (Ji-Parana/RO) com grafia divergente. Case/acento tambem devem cair no alias,
    ja que o alias e resolvido via normalize_key()."""
    assert normalize_regional("UNI - JI-PARANA") == "UNI - JI PARANA"
    assert normalize_regional("uni - ji-parana") == "UNI - JI PARANA"
    assert normalize_regional("  UNI - JI-PARANA  ") == "UNI - JI PARANA"


def test_ji_parana_alias_does_not_affect_other_regionals():
    """O alias e explicito e restrito - nao pode virar normalizacao generica que junte
    regionais diferentes por engano."""
    assert normalize_regional("UNI - JARU") == "UNI - JARU"
    assert normalize_regional("UNI - MACHADINHO DOESTE") == "UNI - MACHADINHO DOESTE"
    assert normalize_regional("UNI - JI PARANA-CENTRO") == "UNI - JI PARANA-CENTRO"


def test_sao_francisco_grouping_still_works_after_adding_rolim_alias():
    """Sanity check: adicionar o agrupamento de Sao Felipe/Rolim nao pode ter quebrado o
    agrupamento existente de Sao Francisco (Sao Miguel + Seringueiras + Sao Francisco do
    Guapore)."""
    assert normalize_regional_grouped("UNI - SAO MIGUEL DO GUAPORE") == SAO_FRANCISCO_REGIONAL
    assert normalize_regional_grouped("UNI - SERINGUEIRAS") == SAO_FRANCISCO_REGIONAL
    assert normalize_regional_grouped("16") == SAO_FRANCISCO_REGIONAL
    assert normalize_regional_grouped("17") == SAO_FRANCISCO_REGIONAL


def test_granular_regionals_for_group_expands_rolim_to_include_sao_felipe():
    """Novo filtro "Regional" (agrupado) da Operacao Analitica/Visao Geral/IA: selecionar
    "UNI - ROLIM DE MOURA" deve trazer a propria Rolim de Moura E a filial granular de Sao
    Felipe D'Oeste, que a coluna `OperationOrder.regional` guarda separada."""
    expanded = granular_regionals_for_group(ROLIM_REGIONAL)
    assert ROLIM_REGIONAL in expanded
    assert "UNI - SAO FELIPE DOESTE" in expanded


def test_granular_regionals_for_group_expands_sao_francisco_to_all_three():
    expanded = granular_regionals_for_group(SAO_FRANCISCO_REGIONAL)
    assert set(expanded) == {
        "UNI - SAO FRANCISCO DO GUAPORE",
        "UNI - SAO MIGUEL DO GUAPORE",
        "UNI - SERINGUEIRAS",
    }


def test_granular_regionals_for_group_unknown_group_returns_empty():
    """Grupo desconhecido nao pode expandir pra "todas as filiais" nem ser ignorado - o
    chamador (operations.queries) trata lista vazia como "nenhuma O.S. corresponde"."""
    assert granular_regionals_for_group("Regional Inexistente") == []


def test_regional_group_options_lists_distinct_groups_without_duplicating_members():
    options = regional_group_options()
    assert ROLIM_REGIONAL in options
    assert SAO_FRANCISCO_REGIONAL in options
    # As filiais que so existem agrupadas (Sao Felipe, Sao Miguel, Seringueiras) nao devem
    # aparecer como opcao propria do filtro "Regional" - so o nome do grupo aparece.
    assert "UNI - SAO FELIPE DOESTE" not in options
    assert "UNI - SAO MIGUEL DO GUAPORE" not in options
    assert "UNI - SERINGUEIRAS" not in options
