from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.modules.operations.models import OperationOrder
from app.modules.support import feedback_service
from app.modules.support.models import SupportIxcTicket, SupportIxcUser, SupportOpaAttendance, SupportOpaDimension

OPA_ID = "opa-adelaidy"
OTHER_ID = "opa-outra"


def _seed_team(db):
    db.add(SupportOpaDimension(dimension_type="user", source_id=OPA_ID, name="Adelaidy Vitoria"))
    db.add(SupportIxcUser(ixc_user_id="10", name="Adelaidy Vitoria", group_id="105", active=True))


def _attendance(db, source_id, *, attendant, first_human, channel="whatsapp", day=5, rating=None):
    db.add(
        SupportOpaAttendance(
            source_id=source_id,
            attendant_id=attendant,
            first_human_attendant_id=first_human,
            channel=channel,
            opened_at=datetime(2026, 10, day, 15, tzinfo=timezone.utc),
            closed_at=datetime(2026, 10, day, 16, tzinfo=timezone.utc),
            status="F",
            reached_human=True,
            rating=rating,
        )
    )


def test_goal_scale_and_targets():
    assert feedback_service.goal_scale(date(2026, 10, 4), date(2026, 10, 10)) == pytest.approx(1.0)
    assert feedback_service.goal_scale(date(2026, 9, 27), date(2026, 9, 30)) == pytest.approx(4 / 7)
    # 38 * 4/7 = 21,7 -> arredonda para cima
    assert feedback_service._target(38, True, 4 / 7) == 22.0
    assert feedback_service._target(4.30, False, 4 / 7) == 4.30


def test_phone_calls_count_only_pabx_where_collaborator_spoke_first(db_session):
    _seed_team(db_session)
    _attendance(db_session, "C1", attendant=OPA_ID, first_human=OPA_ID, channel="pabx")
    # Atendeu primeiro e transferiu: ainda conta (o atendente atual é outro).
    _attendance(db_session, "C2", attendant=OTHER_ID, first_human=OPA_ID, channel="PABX")
    # Outra pessoa atendeu primeiro: não conta.
    _attendance(db_session, "C3", attendant=OPA_ID, first_human=OTHER_ID, channel="pabx")
    # Não é ligação.
    _attendance(db_session, "C4", attendant=OPA_ID, first_human=OPA_ID, channel="whatsapp")
    db_session.commit()

    from app.modules.support.opa_filters import OpaAttendanceFilters

    filters = OpaAttendanceFilters(date_from=date(2026, 10, 1), date_to=date(2026, 10, 10))
    assert feedback_service.phone_calls_answered(db_session, OPA_ID, filters) == 2


def test_collaborator_feedback_combines_opa_and_ixc(db_session):
    _seed_team(db_session)
    for number, subject in enumerate(["90", "90", "29"], start=1):
        db_session.add(
            SupportIxcTicket(
                source_id=f"T{number}",
                subject_id=subject,
                opened_by_user_id="10",
                created_at=datetime(2026, 10, 5, 10, tzinfo=timezone.utc),
            )
        )
    db_session.add(
        SupportIxcTicket(source_id="T9", subject_id="90", opened_by_user_id="99", created_at=datetime(2026, 10, 5, 10, tzinfo=timezone.utc))
    )
    db_session.add(
        OperationOrder(
            source_order_id="OS1", order_code="OS1", creator=" adelaidy vitoria ", sector="Suporte Externo",
            opened_at=datetime(2026, 10, 6, 10, tzinfo=timezone.utc),
        )
    )
    _attendance(db_session, "A1", attendant=OPA_ID, first_human=OPA_ID, channel="pabx", rating=4.5)
    _attendance(db_session, "A2", attendant=OPA_ID, first_human=OPA_ID, rating=4.0)
    db_session.commit()

    result = feedback_service.collaborator_feedback(db_session, date_from=date(2026, 10, 1), date_to=date(2026, 10, 7), attendant_id=OPA_ID)

    assert result is not None and result["name"] == "Adelaidy Vitoria" and result["ixc_linked"] is True
    by_key = {item["key"]: item for item in result["indicators"]}
    assert (by_key["operational"]["value"], by_key["financial"]["value"], by_key["field"]["value"]) == (2, 1, 1)
    assert by_key["opa_attendances"]["value"] == 2
    assert by_key["calls"]["value"] == 1
    assert by_key["rating"]["value"] == pytest.approx(4.25)
    assert by_key["rating"]["status"] == "attention"  # 4,25 vs 4,30
    assert by_key["operational"]["target"] == 38 and by_key["operational"]["status"] == "critical"
    assert by_key["field"]["status"] == "ok"
    assert result["summary"]["overall"] == "critical"
    assert len(result["daily"]) == 7
    day_five = next(point for point in result["daily"] if point["day"] == date(2026, 10, 5))
    assert (day_five["operational"], day_five["financial"], day_five["opa_attendances"]) == (2, 1, 2)


def test_collaborator_without_ixc_user_has_no_ixc_values(db_session):
    db_session.add(SupportOpaDimension(dimension_type="user", source_id=OPA_ID, name="Adelaidy Vitoria"))
    db_session.commit()

    result = feedback_service.collaborator_feedback(db_session, date_from=date(2026, 10, 1), date_to=date(2026, 10, 7), attendant_id=OPA_ID)

    assert result["ixc_linked"] is False
    by_key = {item["key"]: item for item in result["indicators"]}
    assert by_key["operational"]["value"] is None and by_key["operational"]["status"] == "no_data"


def test_unknown_attendant_returns_none(db_session):
    assert feedback_service.collaborator_feedback(db_session, date_from=date(2026, 10, 1), date_to=date(2026, 10, 7), attendant_id="nao-existe") is None


def test_ixc_user_matches_full_name_inside_n1_groups_only(db_session):
    db_session.add_all(
        [
            SupportIxcUser(ixc_user_id="1", name="Julio Cesar Paula Felix", group_id="105", active=True),
            # Mesmo nome em outro grupo: ignorado.
            SupportIxcUser(ixc_user_id="2", name="Julio Cesar Outro Setor", group_id="32", active=True),
            SupportIxcUser(ixc_user_id="3", name="Anna Clara Oliveira Andrade", group_id="105", active=True),
            SupportIxcUser(ixc_user_id="4", name="Anna Heloisa Pereira da Silva", group_id="105", active=True),
            # Dois candidatos iguais em tamanho: sem desempate, não vincula ninguém.
            SupportIxcUser(ixc_user_id="5", name="Maria Souza Lima", group_id="105", active=True),
            SupportIxcUser(ixc_user_id="6", name="Maria Souza Reis", group_id="117", active=True),
        ]
    )
    db_session.commit()

    assert feedback_service._ixc_user(db_session, "Julio César", "Julio César").ixc_user_id == "1"
    assert feedback_service._ixc_user(db_session, "Anna Andrade", "Anna Andrade").ixc_user_id == "3"
    assert feedback_service._ixc_user(db_session, "Maria Souza", "Maria Souza") is None
    assert feedback_service._ixc_user(db_session, "Pessoa Inexistente", "Pessoa Inexistente") is None
