"""Sinal textual sobre a descrição do atendimento (`ixc_ticket_text_signal.py`) - fora do plano
original, pedido do usuário em 2026-09-15 ao corrigir a taxonomia (motivo genérico como "Registro
de Atendimento Operacional" não deve virar sinal de incidente sozinho; a descrição decide)."""

from __future__ import annotations

from app.modules.support import ixc_ticket_text_signal as text_signal


def test_infer_text_signal_is_neutral_without_report():
    signal = text_signal.infer_text_signal(None)

    assert signal.subtema_inferido is None
    assert signal.risk_adjustment == 0
    assert signal.collective_signal is False
    assert signal.matched_keywords == []


def test_infer_text_signal_is_neutral_for_blank_report():
    signal = text_signal.infer_text_signal("   ")

    assert signal.risk_adjustment == 0


def test_infer_text_signal_sobe_muito_for_connection_keywords():
    signal = text_signal.infer_text_signal("Cliente relata que está sem conexão desde ontem à noite.")

    assert signal.subtema_inferido == "Sem conexão"
    assert signal.risk_adjustment == text_signal.SOBE_MUITO_RISK_ADJUSTMENT
    assert "sem conexão" in signal.matched_keywords


def test_infer_text_signal_sobe_for_instability_keywords():
    signal = text_signal.infer_text_signal("Reclama de lentidão no período da noite.")

    assert signal.subtema_inferido == "Lentidão/Intermitência"
    assert signal.risk_adjustment == text_signal.SOBE_RISK_ADJUSTMENT


def test_infer_text_signal_reduz_for_customer_equipment_keywords():
    signal = text_signal.infer_text_signal("Orientado a reiniciar o roteador, aguardando retorno.")

    assert signal.subtema_inferido == "Equipamento do cliente (CPE)"
    assert signal.risk_adjustment == text_signal.REDUZ_RISK_ADJUSTMENT


def test_infer_text_signal_zera_overrides_everything_else():
    """"Financeiro"/"boleto"/"plano"/"cancelamento" zeram o risco mesmo que a descrição também
    mencione uma palavra de "sobe muito" - pedido do usuário: motivo comercial disfarçado de
    registro operacional não pode virar sinal de incidente."""
    signal = text_signal.infer_text_signal("Cliente sem conexão, mas o motivo real é dúvida sobre o boleto.")

    assert signal.subtema_inferido == "Financeiro/Administrativo"
    assert signal.risk_adjustment == text_signal.ZERA_RISK_ADJUSTMENT


def test_infer_text_signal_ignores_unrelated_text():
    signal = text_signal.infer_text_signal("Atendimento realizado conforme procedimento padrão.")

    assert signal.subtema_inferido is None
    assert signal.risk_adjustment == 0


def test_infer_text_signal_word_boundary_avoids_false_positive_substring():
    """"cto" (concentração coletiva) não pode casar dentro de outra palavra - "aspecto" contém as
    letras "cto" mas não é a palavra "CTO" (caixa de terminação óptica)."""
    signal = text_signal.infer_text_signal("Nenhum aspecto fora do padrão foi observado.")

    assert signal.collective_signal is False


def test_infer_text_signal_collective_flag_is_independent_of_severity_group():
    signal = text_signal.infer_text_signal("Vários clientes do bairro reclamando de lentidão na mesma rua.")

    assert signal.collective_signal is True
    assert signal.subtema_inferido == "Lentidão/Intermitência"


def test_resolve_ticket_risk_without_report_equals_base_weight():
    result = text_signal.resolve_ticket_risk(base_weight=15, report=None)

    assert result["risco"] == 15
    assert result["risk_adjustment"] == 0


def test_resolve_ticket_risk_elevates_generic_theme_with_strong_description():
    """O caso central do pedido do usuário: "Registro de Atendimento Operacional" (peso-base 15)
    com descrição de queda de conexão deve subir bem mais perto de um tema forte."""
    result = text_signal.resolve_ticket_risk(base_weight=15, report="Sem internet desde hoje de manhã, luz vermelha na ONU.")

    assert result["risco"] == 65  # 15 + 50
    assert result["subtema_inferido"] == "Sem conexão"


def test_resolve_ticket_risk_clamps_at_zero_and_hundred():
    zero = text_signal.resolve_ticket_risk(base_weight=10, report="Dúvida sobre o boleto em aberto.")
    cem = text_signal.resolve_ticket_risk(base_weight=95, report="Cliente sem conexão total, ONU com luz vermelha.")

    assert zero["risco"] == 0
    assert cem["risco"] == 100
