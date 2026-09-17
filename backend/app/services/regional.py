from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import User


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

# Alias textual explícito (mesma filial, grafia divergente) - NÃO é agrupamento de negócio como
# `REGIONAL_GROUP_ALIASES` abaixo, é a mesma regional real com hífen em vez de espaço. Achado da
# auditoria de frontend de 2026-09-14: `operations_responsible_assignments.regional` (atribuição
# manual) tinha 36 registros gravados como "UNI - JI-PARANA", nunca passados pelo
# `REGIONAL_CODE_MAP` (que só normaliza id_filial numérico) - apareciam como uma segunda opção no
# filtro de regional da Gestão Integrada. Chave em `normalize_key()` para pegar variação de
# maiúsculas/acentos também, não só o hífen. Deliberadamente restrito a este caso confirmado -
# não vira uma normalização genérica de texto que arriscaria juntar regionais diferentes.
REGIONAL_NAME_ALIASES: dict[str, str] = {
    "UNI - JI-PARANA": "UNI - JI PARANA",
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
    mapped = REGIONAL_CODE_MAP.get(raw)
    if mapped is not None:
        return mapped
    # id_filial numérico desconhecido (fora do mapa e não marcado como inválido): não deixar
    # vazar como pseudo-regional isolada em filter_options - cai em "NAO IDENTIFICADO" até ser
    # mapeado em REGIONAL_CODE_MAP. Valores não puramente numéricos (ex.: já vindo como nome de
    # regional) continuam passando cru.
    if raw.isdigit():
        return "NAO IDENTIFICADO"
    alias = REGIONAL_NAME_ALIASES.get(normalize_key(raw))
    if alias is not None:
        return alias
    return raw


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


def regional_scope_or_deny(user: "User | None") -> tuple[list[str], bool]:
    """(regionais permitidas, nega_tudo) - mesma regra de escopo regional já aplicada em
    `operations.queries._dimension_conditions`, generalizada aqui pra qualquer função FORA desse
    módulo que também precise respeitar o escopo do usuário (achado P0-2 da auditoria de
    2026-09-15: as consultas de rede - login/ONU/geolocalização - não aplicavam nenhum escopo,
    deixando um gestor regional consultar dado de QUALQUER regional).

    `nega_tudo=True` só para `regional_manager_viewer` sem nenhuma regional configurada - mesmo
    critério de `_dimension_conditions` (não é um acesso amplo por omissão, é ausência de
    configuração). Quando `regionais permitidas` vem não-vazia, o chamador deve SEMPRE aplicar
    `IN (...)` com essa lista (mesmo que também tenha um filtro de regional próprio vindo do
    cliente - os dois combinados via AND já produzem a interseção certa, e nunca ampliam o
    acesso).

    `user=None` é acesso IRRESTRITO deliberado (`([], False)`) - só para chamador de sistema sem
    usuário associado (ex.: monitor de background do `intelligence` varrendo o sistema inteiro
    pra detectar outage coletivo, `monitors/collective_outage.py`/`monitors/rules_engine.py`),
    nunca para uma requisição HTTP/MCP real, que sempre tem um `user` autenticado."""
    if user is None:
        return [], False
    allowed = effective_managed_regionals(user.managed_regional, user.managed_regionals)
    deny_all = not allowed and user.role == "regional_manager_viewer"
    return allowed, deny_all


def _build_grouped_to_granular() -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for granular in dict.fromkeys(REGIONAL_CODE_MAP.values()):
        mapping.setdefault(normalize_regional_grouped(granular), []).append(granular)
    return mapping


# Regional agrupada (filtro "Regional" da Operação Analítica/Visão Geral/IA) -> lista das filiais
# granulares reais que a compõem (o valor guardado em `OperationOrder.regional`). Construído uma
# vez a partir de `REGIONAL_CODE_MAP`/`REGIONAL_GROUP_ALIASES`, que já são a fonte usada pela
# Gamificação - nenhum cadastro novo, só reaproveita a mesma regra.
GROUPED_TO_GRANULAR: dict[str, list[str]] = _build_grouped_to_granular()


def regional_group_options() -> list[str]:
    """Lista as regionais agrupadas distintas (ex.: "UNI - ROLIM DE MOURA" já cobre São Felipe
    D'Oeste) - usada para popular o filtro "Regional" nas telas e na IA."""
    return sorted(GROUPED_TO_GRANULAR, key=str.casefold)


def granular_regionals_for_group(group: str) -> list[str]:
    """Expande uma regional agrupada (valor selecionado no filtro "Regional") para as filiais
    granulares reais que a compõem, para filtrar `OperationOrder.regional` (que guarda a
    identidade granular) via IN(...). Grupo desconhecido devolve lista vazia - o chamador deve
    tratar isso como "nenhuma O.S. corresponde", não como "sem filtro"."""
    normalized_group = normalize_key(group)
    for grouped_name, granular_list in GROUPED_TO_GRANULAR.items():
        if normalize_key(grouped_name) == normalized_group:
            return granular_list
    return []


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
