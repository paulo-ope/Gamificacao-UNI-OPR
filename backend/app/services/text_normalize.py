"""Normalização de texto livre vindo de cadastro (bairro, endereço) - NÃO confundir com
`app/services/regional.py` (que resolve contra uma lista fechada de regionais conhecidas).
Bairro é texto digitado por atendente/cliente sem padrão - não há tabela de "bairros oficiais"
pra resolver contra, só dá pra normalizar a própria string.
"""

from __future__ import annotations

import re


def normalize_place_name(value: str | None) -> str | None:
    """Colapsa espaço duplicado e padroniza capitalização (Title Case) - suficiente pra unir
    "CENTRO"/"Centro"/"centro" numa linha só no drill-down, sem inventar correspondência entre
    palavras genuinamente diferentes (ex.: "Rural" continua distinto de "Zona Rural" - são textos
    diferentes, não uma normalização de caixa). Não mexe em acentuação: `.title()` do Python só
    reescreve a primeira letra de cada palavra, preserva o caractere acentuado como está digitado
    (achado real, 2026-09-12: várias grafias diferentes do MESMO bairro só por causa de
    maiúscula/minúscula inconsistente no cadastro do IXC, ex. "ZONA RURAL" x "Zona Rural" x
    "zona rural" - eram +100 atendimentos fragmentados em linhas separadas no drill-down por
    bairro)."""
    if not value:
        return None
    collapsed = re.sub(r"\s+", " ", value.strip())
    if not collapsed:
        return None
    return collapsed.title()
