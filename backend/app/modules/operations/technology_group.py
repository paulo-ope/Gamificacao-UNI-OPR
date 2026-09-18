from __future__ import annotations

from app.services.regional import normalize_key

ACTIVATION_FIBER_URBAN = "Ativação Fibra Urbana"
ACTIVATION_FIBER_RURAL = "Ativação Fibra Rural"
ACTIVATION_RADIO = "Ativação Rádio"
SUPPORT_FIBER_URBAN = "Suporte Fibra Urbana"
SUPPORT_FIBER_RURAL = "Suporte Fibra Rural"
SUPPORT_RADIO = "Suporte Rádio"
OTHER_TECHNOLOGY_GROUP = "Outros"

# Assunto granular de O.S. (`OperationOrder.os_subject`) -> grupo por tecnologia/categoria, para o
# indicador "SLA por tecnologia" da Visão Geral (pedido do usuário em 2026-09-17, baseado na
# tabela de regras que ele já usa em outro sistema - `docs/integracao-uni/
# regras-agrupamento-sla-tecnologia.json`). Chaves na grafia EXATA como o IXC grava hoje (mesmo
# padrão de `app/services/ixc_importer.py:load_historical_os_type_mapping`, que já usa
# comparação exata para os_subject) - variantes de acento/maiúscula conhecidas (ex.: "Instalação
# Rádio" vs "INSTALACAO RADIO") já entram como entradas separadas, não por normalização
# automática. Assuntos fora das 6 categorias do painel (troca de endereço, mudança de tecnologia,
# remoção de equipamento, viabilidade) caem em `OTHER_TECHNOLOGY_GROUP` por decisão explícita do
# usuário - não ficam invisíveis, só não aparecem separados nos dois gráficos principais.
RAW_SUBJECT_TECHNOLOGY_GROUP: dict[str, str] = {
        "Instalação Fibra Urbana": ACTIVATION_FIBER_URBAN,
        "Retorno de Instalação Fibra Urbana": ACTIVATION_FIBER_URBAN,
        "Instalação Evento/Permuta Fibra Urbana": ACTIVATION_FIBER_URBAN,
        "Retorno de Instalação Evento/Permuta Fibra Urbana": ACTIVATION_FIBER_URBAN,
        "Instalação Fibra Urbana com Ativação de Câmeras": ACTIVATION_FIBER_URBAN,
        "Instalação Fibra Rural": ACTIVATION_FIBER_RURAL,
        "Retorno de Instalação Fibra Rural": ACTIVATION_FIBER_RURAL,
        "Instalação Evento/Permuta Fibra Rural": ACTIVATION_FIBER_RURAL,
        "Retorno de Instalação Evento/Permuta Fibra Rural": ACTIVATION_FIBER_RURAL,
        "Instalação Rádio": ACTIVATION_RADIO,
        "Retorno de Instalação Rádio": ACTIVATION_RADIO,
        "INSTALACAO RADIO": ACTIVATION_RADIO,
        "RETORNO DE INSTALACAO RADIO": ACTIVATION_RADIO,
        "Suporte Externo Fibra Urbana": SUPPORT_FIBER_URBAN,
        "Sem Conexão Fibra Urbana": SUPPORT_FIBER_URBAN,
        "Alteração na Rede Interna Fibra Urbana": SUPPORT_FIBER_URBAN,
        "Reincidência de Suporte Fibra Urbana": SUPPORT_FIBER_URBAN,
        "Sem Conexão (Link LOS)": SUPPORT_FIBER_URBAN,
        "Troca de Equipamentos": SUPPORT_FIBER_URBAN,
        "Suporte Streaming/Apps": SUPPORT_FIBER_URBAN,
        "Regulagem de Sinal": SUPPORT_FIBER_URBAN,
        "Suporte Prioritário": SUPPORT_FIBER_URBAN,
        "Manutenção Preventiva Operacional": SUPPORT_FIBER_URBAN,
        "Ativação de Login Presencial": SUPPORT_FIBER_URBAN,
        "Remoção de Flashman": SUPPORT_FIBER_URBAN,
        "Reativação de Suspensão Temporária - Externo": SUPPORT_FIBER_URBAN,
        "Migração de Rede Neutra": SUPPORT_FIBER_URBAN,
        "Suporte Externo Fibra Rural": SUPPORT_FIBER_RURAL,
        "Sem Conexão Fibra Rural": SUPPORT_FIBER_RURAL,
        "Alteração na Rede Interna Fibra Rural": SUPPORT_FIBER_RURAL,
        "Reincidência de Suporte Fibra Rural": SUPPORT_FIBER_RURAL,
        "Suporte Externo Rádio": SUPPORT_RADIO,
        "Sem Conexão Rádio": SUPPORT_RADIO,
        "Alteração na Rede Interna Rádio": SUPPORT_RADIO,
        "Reincidência de Suporte Rádio": SUPPORT_RADIO,
        "Alteração de Endereço Fibra Urbana": OTHER_TECHNOLOGY_GROUP,
        "Retorno de Alteração de Endereço Fibra Urbana": OTHER_TECHNOLOGY_GROUP,
        "Alteração de Endereço Fibra Rural": OTHER_TECHNOLOGY_GROUP,
        "Retorno de Alteração de Endereço Fibra Rural": OTHER_TECHNOLOGY_GROUP,
        "Alteração de Endereço Rádio": OTHER_TECHNOLOGY_GROUP,
        "Retorno de Alteração de Endereço Rádio": OTHER_TECHNOLOGY_GROUP,
        "Alteração da Tecnologia para Fibra": OTHER_TECHNOLOGY_GROUP,
        "Alteração da Tecnologia para Rádio": OTHER_TECHNOLOGY_GROUP,
        "Retorno de Alteração de Tecnologia para Fibra": OTHER_TECHNOLOGY_GROUP,
        "Retorno de Alteração de Tecnologia Rádio para Fibra": OTHER_TECHNOLOGY_GROUP,
        "Retorno de Alteração de Tecnologia Fibra para Rádio": OTHER_TECHNOLOGY_GROUP,
        "Remoção de Equipamentos": OTHER_TECHNOLOGY_GROUP,
        "Recuperação de Equipamento por Cobrança": OTHER_TECHNOLOGY_GROUP,
        "Viabilidade": OTHER_TECHNOLOGY_GROUP,
}

# Versão normalizada (maiúsculo, sem acento, via `normalize_key`) do mapa acima - usada pelo
# helper Python `normalize_technology_group` como rede de segurança contra variação de
# acentuação/capitalização que ainda não tenha uma entrada própria em `RAW_SUBJECT_TECHNOLOGY_GROUP`.
SUBJECT_TECHNOLOGY_GROUP: dict[str, str] = {
    normalize_key(subject): group for subject, group in RAW_SUBJECT_TECHNOLOGY_GROUP.items()
}

# Ordem fixa de exibição nos dois gráficos da Visão Geral (Ativação e Suporte, 3 tecnologias
# cada) - não inclui `OTHER_TECHNOLOGY_GROUP` porque os dois gráficos são só essas 6 categorias;
# "Outros" fica disponível na resposta da API para quem quiser somar o restante, mas não é uma das
# 6 barras/gauges do painel.
ACTIVATION_TECHNOLOGY_GROUPS = (ACTIVATION_FIBER_URBAN, ACTIVATION_FIBER_RURAL, ACTIVATION_RADIO)
SUPPORT_TECHNOLOGY_GROUPS = (SUPPORT_FIBER_URBAN, SUPPORT_FIBER_RURAL, SUPPORT_RADIO)


def normalize_technology_group(subject: str | None) -> str:
    """Assunto granular de O.S. -> grupo por tecnologia/categoria. Assunto vazio ou não mapeado
    (taxonomia nova do IXC ainda não catalogada aqui) cai em `OTHER_TECHNOLOGY_GROUP` - nunca
    devolve o assunto cru, pois ele quebraria a garantia de só 7 valores possíveis que os gráficos
    da Visão Geral esperam."""
    if not subject:
        return OTHER_TECHNOLOGY_GROUP
    return SUBJECT_TECHNOLOGY_GROUP.get(normalize_key(subject), OTHER_TECHNOLOGY_GROUP)
