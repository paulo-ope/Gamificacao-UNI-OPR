"""Caracterizacao da identidade de cliente usada na reincidencia/garantia
(auditoria financeira 2026-08-26, achado C3).

Estes testes NAO corrigem nada: eles fixam por escrito o comportamento atual e deixam explicito
o risco, porque trocar a identidade muda quantos pontos foram anulados em todo periodo ja
calculado e depende de decisao de produto (Etapa 5 do plano de correcao).

O problema medido na base real: `recurrence_identity_fields` esta configurado como `contract`, e
`contract_id` (o `id_contrato` do IXC) NAO identifica um cliente - um mesmo contrato agrupa ate 20
logins distintos. 509 contratos tem mais de um login, cobrindo 1.868 O.S. (2,52% da base), e ha
1.757 pares de O.S. de clientes DIFERENTES dentro da janela de 30 dias que a engine hoje trata
como o mesmo cliente.
"""
from datetime import datetime, timezone

import pytest

from app.models import AppSetting, ServiceOrder
from app.services import scoring_detail


def _os(collaborator, code, login, contract, opened):
    return ServiceOrder(
        os_code=code,
        contract_id=contract,
        customer_login=login,
        customer_name=f"Cliente {login}",
        collaborator_id=collaborator.id,
        regional=collaborator.regional,
        os_type="Manutencao",
        os_subject="Reparo",
        diagnosis="Falha",
        status="Concluida",
        opened_at=opened,
        closed_at=opened,
    )


@pytest.fixture()
def two_customers_one_contract(db_session, make_collaborator):
    """Dois clientes reais (logins distintos) sob o mesmo `id_contrato` - o padrao que a base de
    producao tem em 509 contratos."""
    technician = make_collaborator(name="Tecnico Um")
    first = _os(technician, "OS-A", "cliente.alfa", "12371", datetime(2026, 7, 5, tzinfo=timezone.utc))
    second = _os(technician, "OS-B", "cliente.beta", "12371", datetime(2026, 7, 20, tzinfo=timezone.utc))
    db_session.add_all([first, second])
    db_session.flush()
    return first, second


def _set_identity_fields(db_session, value: str) -> None:
    setting = db_session.query(AppSetting).filter(AppSetting.key == "recurrence_identity_fields").one_or_none()
    if setting:
        setting.value = value
    else:
        db_session.add(AppSetting(key="recurrence_identity_fields", value=value))
    db_session.flush()


def test_default_identity_separates_two_logins_under_the_same_contract(db_session, two_customers_one_contract):
    """Com o padrao de codigo (`login,contract`), o login vence e dois clientes distintos NAO sao
    tratados como o mesmo - e o comportamento correto."""
    first, second = two_customers_one_contract
    fields = scoring_detail._configured_recurrence_identity_fields(db_session)
    assert fields == ["login", "contract"], "sem a configuracao gravada, o padrao do codigo e login primeiro"

    assert scoring_detail._recurrence_identity_for_fields(first, fields) == "login:cliente.alfa"
    assert scoring_detail._recurrence_identity_for_fields(second, fields) == "login:cliente.beta"
    assert scoring_detail._recurrence_identity_for_fields(first, fields) != scoring_detail._recurrence_identity_for_fields(
        second, fields
    )


def test_contract_only_identity_merges_two_different_customers(db_session, two_customers_one_contract):
    """RISCO DOCUMENTADO (nao corrigido): com `recurrence_identity_fields = contract` - que e a
    configuracao ATIVA em producao - dois clientes diferentes viram a mesma identidade, e uma O.S
    de um cliente pode anular os pontos de uma O.S de outro cliente."""
    first, second = two_customers_one_contract
    _set_identity_fields(db_session, "contract")

    fields = scoring_detail._configured_recurrence_identity_fields(db_session)
    assert fields == ["contract"]

    identity_first = scoring_detail._recurrence_identity_for_fields(first, fields)
    identity_second = scoring_detail._recurrence_identity_for_fields(second, fields)
    assert identity_first == identity_second == "contract:12371"


def test_contract_only_identity_pairs_orders_of_different_customers_as_recurrence(
    db_session, two_customers_one_contract, recurrence_setup, scoring_setup
):
    """O efeito financeiro do risco acima: a engine de reincidencia pareia as duas O.S e anula os
    pontos da primeira, mesmo elas sendo de clientes diferentes."""
    first, second = two_customers_one_contract
    _set_identity_fields(db_session, "contract")

    penalties = scoring_detail.recurrence_penalties(
        db_session,
        [first, second],
        scoring_detail.build_scoring_rule_lookup(scoring_detail.active_scoring_rules(db_session)),
    )

    assert first.id in penalties, "com identidade por contrato, a O.S do cliente alfa e penalizada pela do beta"
    assert penalties[first.id]["related_os_code"] == second.os_code
    assert penalties[first.id]["points"] > 0


def test_login_identity_does_not_pair_orders_of_different_customers(
    db_session, two_customers_one_contract, recurrence_setup, scoring_setup
):
    """Contraprova: com a identidade por login, o mesmo par nao gera nenhuma penalidade. E a
    diferenca exata que a decisao da Etapa 5 vai definir."""
    first, second = two_customers_one_contract
    _set_identity_fields(db_session, "login,contract")

    penalties = scoring_detail.recurrence_penalties(
        db_session,
        [first, second],
        scoring_detail.build_scoring_rule_lookup(scoring_detail.active_scoring_rules(db_session)),
    )

    assert penalties == {}


def test_contract_identity_is_ignored_when_it_is_not_a_real_identifier(db_session, make_collaborator):
    """Trava que ja funciona e nao deve ser perdida: `NAO IDENTIFICADO` (1.112 O.S. na base real)
    nao tem digito, entao nunca vira identidade - essas O.S. ficam fora da reincidencia em vez de
    virarem um unico cliente gigante."""
    technician = make_collaborator(name="Tecnico Dois")
    order = _os(technician, "OS-C", None, "NAO IDENTIFICADO", datetime(2026, 7, 5, tzinfo=timezone.utc))
    db_session.add(order)
    db_session.flush()

    assert scoring_detail._recurrence_identity_for_fields(order, ["contract"]) == ""
    assert scoring_detail._recurrence_identity_for_fields(order, ["login", "contract"]) == ""
