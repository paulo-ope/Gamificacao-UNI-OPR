from __future__ import annotations


# Primeira cobertura histórica confirmada para o backfill de três meses.
# O catálogo completo fica disponível no filtro; os demais setores serão
# carregados em uma fase posterior sem mudar o contrato da interface.
PRIMARY_IXC_SECTOR_IDS = ("7", "8", "9")
PRIMARY_SECTOR_NAMES = (
    "Suporte Externo",
    "Suporte Externo Rádio",
    "Suporte Externo Fibra",
)

# Catálogo ativo retornado por `empresa_setor` em 21/07/2026. Ele permanece
# local para que abrir um dropdown nunca gere consulta ao IXC.
IXC_SECTORS = (
    ("1", "Comercial"),
    ("2", "Pós Venda"),
    ("3", "Retenção"),
    ("4", "Financeiro"),
    ("5", "Cobrança"),
    ("6", "Faturamento"),
    ("7", "Suporte Externo"),
    ("8", "Suporte Externo Rádio"),
    ("9", "Suporte Externo Fibra"),
    ("10", "Suporte Interno"),
    ("11", "Homologação de Ordem de Serviço"),
    ("12", "Pesquisa de Satisfação"),
    ("13", "Agendamento"),
    ("14", "Técnico Infraestrutura"),
    ("15", "Noc"),
    ("17", "Processos e Parametrizações"),
    ("18", "Estoque"),
    ("19", "Operacional"),
    ("20", "Integração IClass"),
    ("21", "teste"),
    ("23", "Desenvolvimento"),
)
ALL_SECTOR_NAMES = tuple(name for _, name in IXC_SECTORS)
ALL_IXC_SECTOR_IDS = tuple(sector_id for sector_id, _ in IXC_SECTORS)
IXC_SECTOR_NAME_BY_ID = dict(IXC_SECTORS)
IXC_SECTOR_ID_BY_NAME = {name: sector_id for sector_id, name in IXC_SECTORS}

MAX_FILTER_VALUES_PER_FIELD = 100


def normalize_ixc_sector_ids(sector_ids: list[str] | tuple[str, ...] | None) -> list[str]:
    selected = [str(value).strip() for value in sector_ids or [] if str(value).strip()]
    selected = list(dict.fromkeys(selected))
    if not selected:
        return list(PRIMARY_IXC_SECTOR_IDS)
    allowed = set(ALL_IXC_SECTOR_IDS)
    invalid = [sector_id for sector_id in selected if sector_id not in allowed]
    if invalid:
        raise ValueError(f"Setor(es) IXC invalido(s): {', '.join(invalid)}.")
    return selected


def ixc_sector_scope_label(sector_ids: list[str] | tuple[str, ...] | None) -> str:
    selected = normalize_ixc_sector_ids(sector_ids)
    if set(selected) == set(ALL_IXC_SECTOR_IDS):
        return f"Todos os setores ({len(ALL_IXC_SECTOR_IDS)})"
    if set(selected) == set(PRIMARY_IXC_SECTOR_IDS):
        return "3 setores principais: Suporte Externo, Radio e Fibra"
    names = [IXC_SECTOR_NAME_BY_ID.get(sector_id, sector_id) for sector_id in selected]
    if len(names) <= 3:
        return ", ".join(names)
    return f"{len(names)} setores: {', '.join(names[:3])}..."


def transmitter_display_name(transmitter_id: str | None) -> str | None:
    """Nome de exibição do transmissor/OLT - investigado antes de implementar (F5): a única fonte
    real hoje é o ID cru vindo do IXC (`id_transmissor`, tabela `radpop_radio_cliente_fibra` via
    `OperationOnuSignalCurrent.transmitter_id`). Não existe, em nenhuma fonte já capturada, nome,
    site, localidade ou descrição de transmissor/OLT - só o identificador numérico.

    Por isso esta função NÃO inventa um nome amigável - só formata o ID cru de forma consistente
    ("TX 408"), para que toda tela (collective_outage, intelligence_alerts, cockpit, contexto MCP)
    mostre exatamente o mesmo texto em vez de cada uma montar a própria string. Se um catálogo de
    nomes de transmissor for importado no futuro, só esta função precisa mudar."""
    if not transmitter_id:
        return None
    return f"TX {transmitter_id}"
