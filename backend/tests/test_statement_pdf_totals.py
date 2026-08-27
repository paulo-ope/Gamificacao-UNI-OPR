"""Regressao da auditoria financeira 2026-08-26 (achado A8): a coluna "Valor" de cada O.S. no
extrato de pagamento era `net_points * point_value`, IGNORANDO o multiplicador de saude da
regional.

Efeito medido no fechamento pago #1601: para ANDRE PERES DA SILVA (multiplicador 0,30), a soma da
coluna dava ~R$ 432,60 (1.236 pts x R$ 0,35) contra "Valor a pagar: R$ 129,78" no resumo do MESMO
documento - 3,3x de diferenca num papel chamado "Extrato de Pagamento - Conferencia Individual".
O pagamento nunca esteve errado; o documento que o explica e que nao fechava.

A correcao reparte o valor a pagar entre as O.S. proporcionalmente aos pontos liquidos (com o
valor do ponto de cada uma, porque assunto/grupo podem ter valor proprio), pelo metodo do maior
resto, de modo que a soma seja exatamente o valor a pagar.
"""
import pytest

from app.services.statement_pdf import distribute_amount_by_weight


def test_slices_sum_exactly_to_the_total():
    """A soma das fatias tem que ser o total, nao 'quase' - e dinheiro num documento de
    conferencia."""
    amounts = distribute_amount_by_weight(129.78, [15.0, 15.0, 8.0, 6.0])
    assert round(sum(amounts), 2) == 129.78


def test_slices_are_proportional_to_the_weight():
    total = 100.0
    amounts = distribute_amount_by_weight(total, [30.0, 10.0, 10.0])
    assert round(sum(amounts), 2) == total
    assert amounts[0] > amounts[1]
    assert amounts[1] == amounts[2]
    assert amounts[0] == pytest.approx(60.0, abs=0.01)


def test_indivisible_cents_are_distributed_without_losing_or_gaining():
    """R$ 10,00 em 3 partes iguais: arredondar cada fatia isoladamente daria R$ 9,99."""
    amounts = distribute_amount_by_weight(10.0, [1.0, 1.0, 1.0])
    assert round(sum(amounts), 2) == 10.0
    assert sorted(amounts, reverse=True) == [3.34, 3.33, 3.33]


def test_multiplier_is_respected_because_the_total_already_includes_it():
    """O cenario real do #1601: 1.236 pontos liquidos, valor do ponto R$ 0,35, multiplicador 0,30.

    A conta ingenua (`net_points * point_value`) daria R$ 432,60. O valor a pagar de verdade e
    R$ 129,78 (1.236 x 0,30 x 0,35). Como a distribuicao parte do valor a pagar, a coluna soma
    R$ 129,78 - nao os R$ 432,60 do defeito antigo.
    """
    valor_a_pagar = 129.78
    pesos = [1236.0 * 0.35]  # uma unica O.S. concentrando os pontos
    assert round(sum(distribute_amount_by_weight(valor_a_pagar, pesos)), 2) == valor_a_pagar
    assert round(1236.0 * 0.35, 2) == 432.60, "a conta antiga daria isso - 3,3x o valor real"


def test_no_scored_order_produces_no_value():
    """Colaborador sem nenhuma O.S. pontuada: nao ha peso para distribuir, e nao se inventa
    valor - todas as linhas ficam zeradas."""
    assert distribute_amount_by_weight(50.0, [0.0, 0.0]) == [0.0, 0.0]


def test_unregistered_collaborator_with_zero_payment_gets_zero_everywhere():
    """Colaborador nao cadastrado sai com `estimated_payment = 0` em toda a cadeia - a coluna do
    extrato tem que acompanhar, sem sobra de centavo."""
    amounts = distribute_amount_by_weight(0.0, [15.0, 8.0, 6.0])
    assert amounts == [0.0, 0.0, 0.0]


def test_empty_order_list_is_safe():
    assert distribute_amount_by_weight(100.0, []) == []


def test_distribution_is_deterministic():
    """O mesmo extrato gerado duas vezes precisa sair identico - o desempate do maior resto e
    estavel, nao depende de ordem de dicionario nem de hash."""
    weights = [7.0, 7.0, 7.0, 5.0, 3.0]
    first = distribute_amount_by_weight(83.33, weights)
    second = distribute_amount_by_weight(83.33, weights)
    assert first == second
    assert round(sum(first), 2) == 83.33
