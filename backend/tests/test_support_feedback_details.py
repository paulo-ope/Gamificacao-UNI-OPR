from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.modules.operations.models import OperationOrder
from app.modules.support import feedback_details
from app.modules.support.models import SupportIxcUser, SupportOpaAttendance, SupportOpaDimension

OPA_ID = "opa-adelaidy"
PERIOD = {"date_from": date(2026, 10, 1), "date_to": date(2026, 10, 7)}


def _seed_team(db):
    db.add(SupportOpaDimension(dimension_type="user", source_id=OPA_ID, name="Adelaidy Vitoria"))
    db.add(SupportIxcUser(ixc_user_id="10", name="Adelaidy Vitoria", group_id="105", active=True))


def _order(db, code, *, customer, day, hour=10, diagnosis=None, creator="Adelaidy Vitoria"):
    db.add(
        OperationOrder(
            source_order_id=code, order_code=code, creator=creator, sector="Suporte Externo", customer_id=customer,
            customer_name=f"Cliente {customer}", diagnosis=diagnosis, status="Finalizada",
            opened_at=datetime(2026, 10, day, hour, tzinfo=timezone.utc),
        )
    )


def _rated(db, source_id, rating, *, channel="whatsapp", day=5):
    db.add(
        SupportOpaAttendance(
            source_id=source_id, attendant_id=OPA_ID, first_human_attendant_id=OPA_ID, channel=channel, rating=rating,
            opened_at=datetime(2026, 10, day, 15, tzinfo=timezone.utc), closed_at=datetime(2026, 10, day, 16, tzinfo=timezone.utc),
            status="F", reached_human=True,
        )
    )


def test_improper_orders_flag_diagnosis_and_duplicates(db_session):
    _seed_team(db_session)
    _order(db_session, "OS1", customer="c1", day=2)
    _order(db_session, "OS2", customer="c1", day=3, diagnosis="Desistência da Solicitação")  # diagnóstico + duplicada de OS1
    _order(db_session, "OS3", customer="c2", day=4, diagnosis="Atendimento com Assunto Errado")
    _order(db_session, "OS4", customer="c3", day=4, diagnosis="SUP: Cabo Rompido ou Danificado (Fibra)")  # válida
    _order(db_session, "OS5", customer="c4", day=1)
    _order(db_session, "OS6", customer="c4", day=6)  # mesmo cliente, mas fora da janela de 72 h
    _order(db_session, "OS7", customer="c5", day=3, diagnosis="Desistência da Solicitação", creator="Outra Pessoa")  # de outro colaborador
    db_session.commit()

    result = feedback_details.collaborator_details(db_session, attendant_id=OPA_ID, **PERIOD)

    orders = result["improper_orders"]
    assert orders["total_orders"] == 6 and orders["improper_count"] == 2
    by_code = {item["order_code"]: item["reasons"] for item in orders["orders"]}
    assert by_code["OS2"] == ["Desistência da solicitação", feedback_details.DUPLICATE_REASON]
    assert by_code["OS3"] == ["Assunto errado"]
    assert orders["improper_percent"] == pytest.approx(33.3)
    assert {item["reason"] for item in orders["by_reason"]} == {"Desistência da solicitação", feedback_details.DUPLICATE_REASON, "Assunto errado"}


def test_improper_orders_is_none_without_ixc_user(db_session):
    db_session.add(SupportOpaDimension(dimension_type="user", source_id=OPA_ID, name="Adelaidy Vitoria"))
    db_session.commit()

    result = feedback_details.collaborator_details(db_session, attendant_id=OPA_ID, **PERIOD)

    assert result["ixc_linked"] is False and result["improper_orders"] is None


def test_rating_bands_and_breakdowns(db_session):
    _seed_team(db_session)
    for number, (rating, channel, day) in enumerate([(5, "whatsapp", 5), (4, "whatsapp", 5), (3, "pabx", 6), (2, "whatsapp", 6), (1, "pabx", 6)]):
        _rated(db_session, f"A{number}", rating, channel=channel, day=day)
    db_session.commit()

    ratings = feedback_details.collaborator_details(db_session, attendant_id=OPA_ID, **PERIOD)["ratings"]

    assert ratings["rated_count"] == 5 and ratings["average"] == 3.0
    assert (ratings["good"]["count"], ratings["neutral"]["count"], ratings["bad"]["count"]) == (2, 1, 2)
    assert ratings["good"]["percent"] == 40.0
    assert [point["day"] for point in ratings["by_day"]] == [date(2026, 10, 5), date(2026, 10, 6)]
    assert ratings["by_day"][1] == {"day": date(2026, 10, 6), "good": 0, "neutral": 1, "bad": 2}
    assert ratings["by_channel"][0]["channel"] == "whatsapp"
    assert {item["band"] for item in ratings["attendances"]} == {"good", "neutral", "bad"}


def test_details_none_for_unknown_collaborator(db_session):
    assert feedback_details.collaborator_details(db_session, attendant_id="nao-existe", **PERIOD) is None


@pytest.mark.parametrize("rating,band", [(5, "good"), (4, "good"), (3.5, "neutral"), (3, "neutral"), (2, "bad"), (1, "bad")])
def test_rating_band_cutoffs(rating, band):
    assert feedback_details.rating_band(rating) == band


def test_orders_group_remote_review_and_repeat_customers(db_session):
    _seed_team(db_session)
    _order(db_session, "OS1", customer="c1", day=2, diagnosis="SUP: Equipamentos travados (Fibra)")
    _order(db_session, "OS2", customer="c2", day=2, diagnosis="SUP: Equipamento resetado (Fibra)")
    _order(db_session, "OS3", customer="c3", day=3, diagnosis="SUP: Procedimento Organizacional")
    _order(db_session, "OS4", customer="c4", day=1, diagnosis="SUP: Atualização de configuração de equipamento ((Fibra))")
    _order(db_session, "OS5", customer="c5", day=4, diagnosis="SUP: Problemas na rede interna do cliente (Rádio)")
    _order(db_session, "OS6", customer="c6", day=4)  # finalizada sem diagnóstico
    _order(db_session, "OS7", customer="c7", day=5, diagnosis="Desistência da Solicitação")
    _order(db_session, "OS8", customer="c4", day=6, diagnosis="SUP: Atualização de configuração de equipamento ((Fibra))")  # c4 repete
    db_session.commit()

    orders = feedback_details.collaborator_details(db_session, attendant_id=OPA_ID, **PERIOD)["improper_orders"]

    assert orders["improper_count"] == 1
    assert orders["remote_resolvable"]["count"] == 3
    assert {item["reason"] for item in orders["remote_resolvable"]["by_reason"]} == {"Equipamento travado", "Equipamento resetado", "Procedimento organizacional"}
    assert orders["to_review"]["count"] == 4
    assert {"Finalizada sem diagnóstico", "Atualização de configuração", "Problema na rede interna do cliente"} == {item["reason"] for item in orders["to_review"]["by_reason"]}
    assert orders["repeat_customers"] == [{"customer_name": "Cliente c4", "count": 2}]
