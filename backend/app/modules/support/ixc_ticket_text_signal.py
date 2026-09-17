"""Sinal textual sobre a descrição do atendimento (`SupportIxcTicket.report`) - fora do plano
original de 16 seções, pedido explícito do usuário em 2026-09-15 ao revisar a taxonomia (Fase
0/migração `20260915_0099`): eleva ou reduz o peso-base do tema
(`SupportIxcTaxonomyMapping.risk_weight`) por palavra-chave, e infere um "subtema" mais específico
do que o motivo genérico do IXC permite.

Existe porque um motivo genérico como "Registro de Atendimento Operacional" (peso-base baixo de
propósito, mistura Suporte Interno N1/N2 - ver a migração acima) não pode virar sinal de incidente
sozinho; a descrição escrita pelo atendente é o que diferencia "cliente sem conexão, luz vermelha
na ONU" (risco alto) de "cliente pedindo boleto" (risco zero) por trás do MESMO motivo. Citação do
usuário: "Motivo forte pode gerar risco diretamente. Motivo genérico precisa de evidência textual
ou concentração."

Calibração inicial (2026-09-15), validada só visualmente - as listas de palavra-chave e os valores
de ajuste esperam calibração contínua, não são regra de negócio fechada (mesmo aviso de
`ixc_ticket_overview.CRITICAL_DEVIATION_PCT`)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Ordem de prioridade ao avaliar uma descrição: ZERA > SOBE_MUITO > SOBE > REDUZ. Uma descrição
# pode conter palavras de mais de um grupo (ex.: "sem conexão, já reiniciei o roteador") - vence o
# de maior severidade, não o primeiro encontrado nem uma soma linear dos grupos - evita que uma
# menção incidental de "roteador" cancele um "sem conexão" real.
_ZERA_KEYWORDS = ["financeiro", "boleto", "plano", "cancelamento"]
_SOBE_MUITO_KEYWORDS = [
    "sem conexão", "sem conexao", "sem internet", "parou", "offline", "los", "luz vermelha",
    "cto sem sinal", "sem potência", "sem potencia",
]
_SOBE_KEYWORDS = ["lentidão", "lentidao", "oscilação", "oscilacao", "quedas", "intermitente"]
_REDUZ_KEYWORDS = ["roteador", "wi-fi", "wifi", "senha", "dispositivo", "tv", "app"]

# Flag INDEPENDENTE (não participa da escolha do grupo acima) - "concentração geográfica", item
# explícito do modelo do usuário: sinaliza que a descrição menciona escopo coletivo, pra quem for
# cruzar com burst/reach (Fase 4/1) decidir se é um incidente de vários clientes, não de um só.
_COLLECTIVE_KEYWORDS = ["vários clientes", "varios clientes", "região", "regiao", "rua", "bairro", "cto", "pon"]

# Ajuste ADITIVO ao `risk_weight` do tema (não multiplicativo) - somado direto, sempre clampado em
# [0, 100] por `resolve_ticket_risk`.
ZERA_RISK_ADJUSTMENT = -100
SOBE_MUITO_RISK_ADJUSTMENT = 50
SOBE_RISK_ADJUSTMENT = 25
REDUZ_RISK_ADJUSTMENT = -10


def _matches_any(text: str, keywords: list[str]) -> list[str]:
    # `\b` (fronteira de palavra) em vez de substring solta - sem isso, "cto" (palavra-chave de
    # concentração coletiva) casaria dentro de qualquer palavra que contivesse essas 3 letras.
    return [keyword for keyword in keywords if re.search(rf"\b{re.escape(keyword)}\b", text)]


@dataclass
class TextSignal:
    subtema_inferido: str | None
    risk_adjustment: int
    collective_signal: bool
    matched_keywords: list[str] = field(default_factory=list)


def infer_text_signal(report: str | None) -> TextSignal:
    """Analisa `report` (texto livre do atendente) e devolve o ajuste de risco + subtema inferido.
    `report` vazio/`None` -> sinal NEUTRO (ajuste 0, sem subtema, sem coletivo) - ausência de
    descrição não é evidência de nada, nem a favor nem contra."""
    if not report or not report.strip():
        return TextSignal(subtema_inferido=None, risk_adjustment=0, collective_signal=False)

    text = report.lower()
    collective_signal = bool(_matches_any(text, _COLLECTIVE_KEYWORDS))

    zera = _matches_any(text, _ZERA_KEYWORDS)
    if zera:
        return TextSignal(
            subtema_inferido="Financeiro/Administrativo",
            risk_adjustment=ZERA_RISK_ADJUSTMENT,
            collective_signal=collective_signal,
            matched_keywords=zera,
        )

    sobe_muito = _matches_any(text, _SOBE_MUITO_KEYWORDS)
    if sobe_muito:
        return TextSignal(
            subtema_inferido="Sem conexão",
            risk_adjustment=SOBE_MUITO_RISK_ADJUSTMENT,
            collective_signal=collective_signal,
            matched_keywords=sobe_muito,
        )

    sobe = _matches_any(text, _SOBE_KEYWORDS)
    if sobe:
        return TextSignal(
            subtema_inferido="Lentidão/Intermitência",
            risk_adjustment=SOBE_RISK_ADJUSTMENT,
            collective_signal=collective_signal,
            matched_keywords=sobe,
        )

    reduz = _matches_any(text, _REDUZ_KEYWORDS)
    if reduz:
        return TextSignal(
            subtema_inferido="Equipamento do cliente (CPE)",
            risk_adjustment=REDUZ_RISK_ADJUSTMENT,
            collective_signal=collective_signal,
            matched_keywords=reduz,
        )

    return TextSignal(subtema_inferido=None, risk_adjustment=0, collective_signal=collective_signal)


def resolve_ticket_risk(*, base_weight: int, report: str | None) -> dict[str, Any]:
    """Combina o peso-base do tema (`SupportIxcTaxonomyMapping.risk_weight`) com o sinal textual
    da descrição - `risco` final SEMPRE clampado em [0, 100]. Sem descrição, `risco == base_weight`
    (sinal neutro, nenhum ajuste)."""
    signal = infer_text_signal(report)
    risco = max(0, min(100, base_weight + signal.risk_adjustment))
    return {
        "risco": risco,
        "base_weight": base_weight,
        "risk_adjustment": signal.risk_adjustment,
        "subtema_inferido": signal.subtema_inferido,
        "collective_signal": signal.collective_signal,
        "matched_keywords": signal.matched_keywords,
    }
