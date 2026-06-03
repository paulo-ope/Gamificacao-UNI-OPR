from __future__ import annotations

import unicodedata


SAO_FRANCISCO_REGIONAL = "UNI - SAO FRANCISCO DO GUAPORE"
INVALID_REGIONAL_CODES = {"0", "1"}

REGIONAL_CODE_MAP: dict[str, str] = {
    "6": "UNI - JI PARANA",
    "7": "UNI - MACHADINHO DOESTE",
    "8": "UNI - ROLIM DE MOURA",
    "9": "UNI - JARU",
    "10": "UNI - OURO PRETO DOESTE",
    "11": "UNI - NOVA BRASILANDIA DOESTE",
    "12": "UNI - PRESIDENTE MEDICI",
    "13": "UNI - SAO FELIPE DOESTE",
    "14": "UNI - ALVORADA DOESTE",
    "15": "UNI - ALTA FLORESTA DOESTE",
    "16": SAO_FRANCISCO_REGIONAL,
    "17": SAO_FRANCISCO_REGIONAL,
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
}


def normalize_key(value: str | None) -> str:
    if not value:
        return ""
    cleaned = unicodedata.normalize("NFKD", value)
    without_accents = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
    return " ".join(without_accents.upper().strip().split())


def normalize_regional(value: str | None) -> str:
    if not value or not value.strip():
        return "NAO IDENTIFICADO"
    raw = value.strip()
    if raw in INVALID_REGIONAL_CODES:
        return "NAO IDENTIFICADO"
    mapped = REGIONAL_CODE_MAP.get(raw, raw)
    return REGIONAL_GROUP_ALIASES.get(normalize_key(mapped), mapped)


def same_regional(left: str | None, right: str | None) -> bool:
    return normalize_regional(left) == normalize_regional(right)


def is_valid_regional(value: str | None) -> bool:
    normalized = normalize_regional(value)
    return normalized != "NAO IDENTIFICADO" and normalized not in INVALID_REGIONAL_CODES
