from __future__ import annotations

import unicodedata


SAO_FRANCISCO_REGIONAL = "UNI - SAO FRANCISCO DO GUAPORE"
ROLIM_REGIONAL = "UNI - ROLIM DE MOURA"
INVALID_REGIONAL_CODES = {"0", "1", "5"}  # "5" = filial "geral de cadastro" do IXC, não é uma regional operacional

REGIONAL_CODE_MAP: dict[str, str] = {
    "6": "UNI - JI PARANA",
    "7": "UNI - MACHADINHO DOESTE",
    "8": ROLIM_REGIONAL,
    "9": "UNI - JARU",
    "10": "UNI - OURO PRETO DOESTE",
    "11": "UNI - NOVA BRASILANDIA DOESTE",
    "12": "UNI - PRESIDENTE MEDICI",
    # id_filial 13 é a filial própria de São Felipe D'Oeste, identidade real usada pela Operação
    # Analítica - a gamificação, por sua vez, apura e paga São Felipe junto com Rolim de Moura
    # (mesma frota/CPK e sem base de CPK própria) - ver `normalize_regional_grouped` abaixo.
    "13": "UNI - SAO FELIPE DOESTE",
    "14": "UNI - ALVORADA DOESTE",
    "15": "UNI - ALTA FLORESTA DOESTE",
    # Cada id_filial do IXC é uma filial própria (16 -> São Miguel do Guaporé, 17 -> Seringueiras,
    # 18 -> São Francisco do Guaporé): é a identidade real usada pela Operação Analítica, que
    # precisa das 3 separadas. A gamificação, por sua vez, apura e paga as 3 como uma regional só
    # (São Francisco) - ver `normalize_regional_grouped` logo abaixo.
    "16": "UNI - SAO MIGUEL DO GUAPORE",
    "17": "UNI - SERINGUEIRAS",
    "18": SAO_FRANCISCO_REGIONAL,
}

REGIONAL_GROUP_ALIASES: dict[str, str] = {
    "UNI - SAO MIGUEL DO GUAPORE": SAO_FRANCISCO_REGIONAL,
    "UNI - SAO MIGUEL": SAO_FRANCISCO_REGIONAL,
    "SAO MIGUEL DO GUAPORE": SAO_FRANCISCO_REGIONAL,
    "SAO MIGUEL": SAO_FRANCISCO_REGIONAL,
    "UNI - SERINGUEIRAS": SAO_FRANCISCO_REGIONAL,
    "SERINGUEIRAS": SAO_FRANCISCO_REGIONAL,
    "UNI - SAO FRANCISCO DO GUAPORE": SAO_FRANCISCO_REGIONAL,
    "UNI - SAO FRANCISCO": SAO_FRANCISCO_REGIONAL,
    "SAO FRANCISCO DO GUAPORE": SAO_FRANCISCO_REGIONAL,
    "SAO FRANCISCO": SAO_FRANCISCO_REGIONAL,
    "UNI - SAO FELIPE DOESTE": ROLIM_REGIONAL,
    "UNI - SAO FELIPE": ROLIM_REGIONAL,
    "SAO FELIPE DOESTE": ROLIM_REGIONAL,
    "SAO FELIPE": ROLIM_REGIONAL,
}


def normalize_key(value: str | None) -> str:
    if not value:
        return ""
    cleaned = unicodedata.normalize("NFKD", value)
    without_accents = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
    return " ".join(without_accents.upper().strip().split())


def normalize_regional(value: str | None) -> str:
    """Identidade granular (uma filial real por id_filial). É a base de tudo - inclusive de
    `normalize_regional_grouped` - e é o que a Operação Analítica usa diretamente, porque lá
    São Miguel do Guaporé, Seringueiras e São Francisco do Guaporé precisam continuar separadas."""
    if not value or not value.strip():
        return "NAO IDENTIFICADO"
    raw = value.strip()
    if raw in INVALID_REGIONAL_CODES:
        return "NAO IDENTIFICADO"
    return REGIONAL_CODE_MAP.get(raw, raw)


def normalize_regional_grouped(value: str | None) -> str:
    """Identidade usada pela gamificação: agrupa São Miguel do Guaporé, Seringueiras e São
    Francisco do Guaporé como uma única regional (São Francisco) para SLA, ranking, saúde
    operacional e pagamento - as 3 filiais apuram e pagam juntas. A Operação Analítica não usa
    esta função (ver `normalize_regional`), porque lá o controle é por filial/id_filial real."""
    mapped = normalize_regional(value)
    return REGIONAL_GROUP_ALIASES.get(normalize_key(mapped), mapped)


def same_regional(left: str | None, right: str | None) -> bool:
    return normalize_regional(left) == normalize_regional(right)


def same_regional_grouped(left: str | None, right: str | None) -> bool:
    return normalize_regional_grouped(left) == normalize_regional_grouped(right)


def is_valid_regional(value: str | None) -> bool:
    normalized = normalize_regional(value)
    return normalized != "NAO IDENTIFICADO" and normalized not in INVALID_REGIONAL_CODES


def effective_managed_regionals(managed_regional: str | None, managed_regionals: list[str] | None) -> list[str]:
    """Une o campo legado (managed_regional, singular) com o novo (managed_regionals, lista),
    normalizando (granular - ver `normalize_regional`) e removendo duplicatas - permite um gestor
    regional cobrir várias filiais (migration 20260718_0011) sem quebrar contas antigas que só têm
    o campo singular preenchido. Mantém a identidade granular porque este campo também controla o
    escopo da Operação Analítica (`modules/operations/queries.py`), que precisa das filiais
    separadas - quem precisa do agrupamento da gamificação usa `effective_managed_regionals_grouped`."""
    values = list(managed_regionals or [])
    if managed_regional:
        values.append(managed_regional)
    seen: dict[str, str] = {}
    for value in values:
        normalized = normalize_regional(value)
        if normalized != "NAO IDENTIFICADO":
            seen.setdefault(normalized, normalized)
    return list(seen.values())


def effective_managed_regionals_grouped(managed_regional: str | None, managed_regionals: list[str] | None) -> list[str]:
    """Mesma coisa que `effective_managed_regionals`, mas agrupada (São Miguel do Guaporé,
    Seringueiras e São Francisco do Guaporé viram uma só) - para uso exclusivo da gamificação
    (ex.: escopo do portal de um gestor regional), que compara contra linhas já agrupadas."""
    values = list(managed_regionals or [])
    if managed_regional:
        values.append(managed_regional)
    seen: dict[str, str] = {}
    for value in values:
        normalized = normalize_regional_grouped(value)
        if normalized != "NAO IDENTIFICADO":
            seen.setdefault(normalized, normalized)
    return list(seen.values())
