"""Regression tests for backend/app/services/leadership_bonus.py."""
from app.services.leadership_bonus import _distribute_cents_exactly, apply_leadership_bonus_to_cost_by_regional


def test_distribute_cents_exactly_never_loses_or_gains_a_cent():
    """Regression: dividir um valor em N fatias e arredondar CADA fatia isoladamente pode perder
    (ou ganhar) 1 centavo no total - ex.: R$10,00 / 3 = R$3,33 cada, soma R$9,99, nao R$10,00.
    Isso importa de verdade: e dinheiro de empresa, nao pode sobrar nem faltar 1 centavo."""
    shares = _distribute_cents_exactly(10.0, 3)
    assert round(sum(shares), 2) == 10.0
    assert sorted(shares, reverse=True) == [3.34, 3.33, 3.33]

    shares_even = _distribute_cents_exactly(9.0, 3)
    assert shares_even == [3.0, 3.0, 3.0]
    assert round(sum(shares_even), 2) == 9.0


def test_apply_leadership_bonus_multi_regional_split_never_loses_a_cent():
    """Regression: um bonus que nao divide igualmente entre as regionais do perfil (ex.:
    R$100,01 / 3) nao pode perder 1 centavo na soma final de 'por regional' - isso e dinheiro
    real de colaborador/lideranca, precisa bater exato, nao 'quase'."""
    cost_by_regional = [{"regional": "UNI SUL", "orders": 1, "estimated_payment": 0.0}]
    leadership_summary = {
        "results": [
            {"role_type": "regional_manager", "regionals": ["UNI SUL", "UNI NORTE", "UNI LESTE"], "bonus_amount": 100.01},
        ]
    }

    merged = apply_leadership_bonus_to_cost_by_regional(cost_by_regional, leadership_summary)

    total = round(sum(float(item["estimated_payment"]) for item in merged), 2)
    assert total == 100.01


def test_apply_leadership_bonus_divides_amount_equally_across_linked_regionals():
    """Regression: 'Valor a ser pago por regional' so somava O.S (tecnico), nunca o bonus de
    lideranca - nunca batia com o Total a pagar (que ja soma os dois). Supervisor/Gerente da
    unidade tem regional(is) vinculada(s) no perfil - quando o perfil cobre mais de uma filial, o
    bonus e DIVIDIDO igualmente entre elas (nao somado por inteiro em cada uma), pra soma total
    de 'por regional' sempre bater com o Total a pagar, mesmo com lider multi-regional."""
    cost_by_regional = [
        {"regional": "UNI SUL", "orders": 10, "estimated_payment": 100.0},
        {"regional": "UNI NORTE", "orders": 5, "estimated_payment": 50.0},
    ]
    leadership_summary = {
        "results": [
            {"role_type": "supervisor", "regionals": ["UNI SUL"], "bonus_amount": 20.0},
            {"role_type": "regional_manager", "regionals": ["UNI SUL", "UNI NORTE"], "bonus_amount": 30.0},
        ]
    }

    merged = apply_leadership_bonus_to_cost_by_regional(cost_by_regional, leadership_summary)
    by_regional = {item["regional"]: item for item in merged}

    assert by_regional["UNI SUL"]["estimated_payment"] == 135.0, "100 (tecnico) + 20 (supervisor) + 15 (gerente, metade de 30)"
    assert by_regional["UNI NORTE"]["estimated_payment"] == 65.0, "50 (tecnico) + 15 (gerente, a outra metade)"


def test_apply_leadership_bonus_creates_regional_entry_when_leader_has_no_orders_there():
    """Uma regional que so tem lider vinculado (sem nenhuma O.S no periodo) ainda precisa
    aparecer no detalhamento - senao o bonus dela some silenciosamente do total."""
    cost_by_regional: list[dict] = []
    leadership_summary = {"results": [{"role_type": "supervisor", "regionals": ["UNI LESTE"], "bonus_amount": 15.0}]}

    merged = apply_leadership_bonus_to_cost_by_regional(cost_by_regional, leadership_summary)

    assert len(merged) == 1
    assert merged[0]["regional"] == "UNI LESTE"
    assert merged[0]["estimated_payment"] == 15.0


def test_apply_leadership_bonus_puts_portfolio_manager_in_a_separate_unassigned_bucket():
    """Gerente de pasta cobre TODAS as regionais ao mesmo tempo por definicao (ignora filial) -
    nao da pra atribuir o bonus dele a uma unica regional sem inflar todas elas. Vira uma linha
    separada em vez de silenciosamente sumir do total quando comparado com o card do topo."""
    cost_by_regional = [{"regional": "UNI SUL", "orders": 10, "estimated_payment": 100.0}]
    leadership_summary = {
        "results": [
            {"role_type": "portfolio_manager", "regionals": ["UNI SUL", "UNI NORTE"], "bonus_amount": 40.0},
        ]
    }

    merged = apply_leadership_bonus_to_cost_by_regional(cost_by_regional, leadership_summary)
    by_regional = {item["regional"]: item for item in merged}

    assert by_regional["UNI SUL"]["estimated_payment"] == 100.0, "gerente de pasta nao deve inflar uma regional especifica"
    assert by_regional["Liderança sem regional"]["estimated_payment"] == 40.0


def test_apply_leadership_bonus_total_matches_technicians_plus_leadership():
    """A soma final de 'por regional' deve bater exatamente com tecnicos + lideranca do card do
    topo, mesmo com um lider cobrindo mais de uma filial - o motivo real de dividir em vez de
    somar o valor cheio (achado real: com valor cheio, 2 lideres multi-regional infla a soma em
    ~R$1.125 num fechamento de producao real)."""
    cost_by_regional = [
        {"regional": "UNI SUL", "orders": 10, "estimated_payment": 100.0},
        {"regional": "UNI NORTE", "orders": 5, "estimated_payment": 50.0},
    ]
    leadership_summary = {
        "results": [
            {"role_type": "supervisor", "regionals": ["UNI SUL"], "bonus_amount": 20.0},
            {"role_type": "regional_manager", "regionals": ["UNI SUL", "UNI NORTE"], "bonus_amount": 30.0},
            {"role_type": "portfolio_manager", "regionals": ["UNI SUL", "UNI NORTE"], "bonus_amount": 10.0},
        ]
    }

    merged = apply_leadership_bonus_to_cost_by_regional(cost_by_regional, leadership_summary)

    total = round(sum(float(item["estimated_payment"]) for item in merged), 2)
    tecnicos = 150.0
    lideranca = 60.0
    assert total == tecnicos + lideranca
