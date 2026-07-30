from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from app.modules.operations.models import OperationOrder
from app.modules.operations.period import OPERATIONS_TIMEZONE, current_month_bounds


def _utc_at(day, hour=12):
    return datetime.combine(day, time(hour=hour), tzinfo=OPERATIONS_TIMEZONE).astimezone(timezone.utc)


def _order(**overrides):
    date_from, _ = current_month_bounds()
    base = {
        "source": "ixc",
        "source_order_id": overrides.get("source_order_id") or overrides["order_code"],
        "opened_at": _utc_at(date_from),
        "raw_payload": {},
    }
    base.update(overrides)
    return OperationOrder(**base)


def test_maintenance_within_30_days_counts_as_warranty(client, db_session):
    date_from, date_to = current_month_bounds()
    origin_closed = _utc_at(date_from)
    db_session.add_all(
        [
            _order(
                order_code="ORIGIN-1",
                contract_id="C1",
                os_type="Ativação",
                opened_at=origin_closed - timedelta(days=2),
                closed_at=origin_closed,
            ),
            _order(
                order_code="RETURN-1",
                contract_id="C1",
                os_type="Manutenção",
                opened_at=origin_closed + timedelta(days=30),
                diagnosis="Sem sinal",
            ),
        ]
    )
    db_session.flush()

    response = client.get(
        "/api/operations/warranty",
        params={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["numerator"] == 1
    assert body["items"][0]["return_order_code"] == "RETURN-1"
    assert body["items"][0]["origin_order_code"] == "ORIGIN-1"
    assert body["items"][0]["diagnosis"] == "Sem sinal"


def test_maintenance_after_30_days_is_not_a_warranty(client, db_session):
    date_from, date_to = current_month_bounds()
    origin_closed = _utc_at(date_from)
    db_session.add_all(
        [
            _order(
                order_code="ORIGIN-2",
                contract_id="C2",
                os_type="Ativação",
                opened_at=origin_closed - timedelta(days=2),
                closed_at=origin_closed,
            ),
            _order(
                order_code="RETURN-2",
                contract_id="C2",
                os_type="Manutenção",
                opened_at=origin_closed + timedelta(days=31),
            ),
        ]
    )
    db_session.flush()

    response = client.get(
        "/api/operations/warranty",
        params={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["numerator"] == 0


def test_most_recent_origin_wins_when_contract_has_several(client, db_session):
    date_from, date_to = current_month_bounds()
    older_closed = _utc_at(date_from)
    newer_closed = older_closed + timedelta(days=5)
    db_session.add_all(
        [
            _order(
                order_code="ORIGIN-OLD",
                contract_id="C3",
                os_type="Ativação",
                opened_at=older_closed - timedelta(days=2),
                closed_at=older_closed,
            ),
            _order(
                order_code="ORIGIN-NEW",
                contract_id="C3",
                os_type="Mud. de Endereço",
                opened_at=newer_closed - timedelta(days=1),
                closed_at=newer_closed,
            ),
            _order(
                order_code="RETURN-3",
                contract_id="C3",
                os_type="Manutenção",
                opened_at=newer_closed + timedelta(days=3),
            ),
        ]
    )
    db_session.flush()

    response = client.get(
        "/api/operations/warranty",
        params={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["numerator"] == 1
    assert body["items"][0]["origin_order_code"] == "ORIGIN-NEW"


def test_maintenance_on_a_different_contract_does_not_count(client, db_session):
    date_from, date_to = current_month_bounds()
    origin_closed = _utc_at(date_from)
    db_session.add_all(
        [
            _order(
                order_code="ORIGIN-4",
                contract_id="C4",
                os_type="Ativação",
                opened_at=origin_closed - timedelta(days=2),
                closed_at=origin_closed,
            ),
            _order(
                order_code="RETURN-4",
                contract_id="C4-OTHER",
                os_type="Manutenção",
                opened_at=origin_closed + timedelta(days=1),
            ),
        ]
    )
    db_session.flush()

    response = client.get(
        "/api/operations/warranty",
        params={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
    )

    assert response.status_code == 200
    assert response.json()["numerator"] == 0


def test_diagnosis_filter_restricts_by_the_maintenance_diagnosis(client, db_session):
    date_from, date_to = current_month_bounds()
    origin_closed = _utc_at(date_from)
    db_session.add_all(
        [
            _order(
                order_code="ORIGIN-5",
                contract_id="C5",
                os_type="Ativação",
                opened_at=origin_closed - timedelta(days=2),
                closed_at=origin_closed,
                diagnosis="Origem com outro diagnóstico",
            ),
            _order(
                order_code="RETURN-5",
                contract_id="C5",
                os_type="Manutenção",
                opened_at=origin_closed + timedelta(days=1),
                diagnosis="Sem sinal",
            ),
        ]
    )
    db_session.flush()

    matching = client.get(
        "/api/operations/warranty",
        params={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "diagnoses": "Sem sinal",
        },
    )
    not_matching = client.get(
        "/api/operations/warranty",
        params={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "diagnoses": "Outro diagnóstico qualquer",
        },
    )

    assert matching.status_code == 200
    assert matching.json()["numerator"] == 1
    assert not_matching.status_code == 200
    assert not_matching.json()["numerator"] == 0


def test_regional_filter_also_restricts_the_denominator_origins(client, db_session):
    date_from, date_to = current_month_bounds()
    origin_closed = _utc_at(date_from)
    db_session.add_all(
        [
            _order(
                order_code="ORIGIN-JARU",
                contract_id="C9",
                os_type="Ativação",
                regional="UNI - JARU",
                opened_at=origin_closed - timedelta(days=2),
                closed_at=origin_closed,
            ),
            _order(
                order_code="RETURN-JARU",
                contract_id="C9",
                os_type="Manutenção",
                regional="UNI - JARU",
                opened_at=origin_closed + timedelta(days=1),
            ),
            _order(
                order_code="ORIGIN-OUTRA",
                contract_id="C10",
                os_type="Ativação",
                regional="UNI - MACHADINHO DOESTE",
                opened_at=origin_closed - timedelta(days=2),
                closed_at=origin_closed,
            ),
            _order(
                order_code="RETURN-OUTRA",
                contract_id="C10",
                os_type="Manutenção",
                regional="UNI - MACHADINHO DOESTE",
                opened_at=origin_closed + timedelta(days=1),
            ),
        ]
    )
    db_session.flush()

    response = client.get(
        "/api/operations/warranty",
        params={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "denominator": "active_origins",
            "regionals": "UNI - JARU",
        },
    )

    assert response.status_code == 200
    body = response.json()
    # Só a origem de JARU deve compor o denominador quando o filtro de Regional está ativo.
    assert body["denominator_count"] == 1
    assert body["numerator"] == 1
    assert body["items"][0]["return_order_code"] == "RETURN-JARU"


def test_by_regional_ranking_uses_each_branchs_own_denominator(client, db_session):
    """UNI - JARU tem mais garantias em número absoluto (2), mas UNI - MACHADINHO DOESTE tem a pior
    taxa (100% das origens viraram garantia, contra 50% de JARU) - o ranking deve refletir a taxa de
    cada filial sobre o próprio denominador, não a fatia de cada uma sobre o total de garantias."""
    date_from, date_to = current_month_bounds()
    origin_closed = _utc_at(date_from)

    def _origin_and_maybe_return(order_code_prefix, contract_id, regional, with_return):
        rows = [
            _order(
                order_code=f"{order_code_prefix}-ORIGIN",
                contract_id=contract_id,
                os_type="Ativação",
                regional=regional,
                opened_at=origin_closed - timedelta(days=2),
                closed_at=origin_closed,
            )
        ]
        if with_return:
            rows.append(
                _order(
                    order_code=f"{order_code_prefix}-RETURN",
                    contract_id=contract_id,
                    os_type="Manutenção",
                    regional=regional,
                    opened_at=origin_closed + timedelta(days=1),
                )
            )
        return rows

    db_session.add_all(
        [
            *_origin_and_maybe_return("JARU-1", "C11", "UNI - JARU", with_return=True),
            *_origin_and_maybe_return("JARU-2", "C12", "UNI - JARU", with_return=True),
            *_origin_and_maybe_return("JARU-3", "C14", "UNI - JARU", with_return=False),
            *_origin_and_maybe_return("JARU-4", "C15", "UNI - JARU", with_return=False),
            *_origin_and_maybe_return("MACH-1", "C13", "UNI - MACHADINHO DOESTE", with_return=True),
        ]
    )
    db_session.flush()

    response = client.get(
        "/api/operations/warranty",
        params={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["numerator"] == 3
    assert body["by_regional"][0] == {
        "label": "UNI - MACHADINHO DOESTE",
        "quantity": 1,
        "denominator_count": 1,
        "percentage": 100.0,
    }
    assert body["by_regional"][1] == {
        "label": "UNI - JARU",
        "quantity": 2,
        "denominator_count": 4,
        "percentage": 50.0,
    }


def test_four_denominator_options(client, db_session):
    date_from, date_to = current_month_bounds()
    origin_closed_in_period = _utc_at(date_from)
    # Origem fechada 10 dias antes do início do período (ainda dentro da janela de 30 dias).
    origin_closed_before_period = origin_closed_in_period - timedelta(days=10)
    db_session.add_all(
        [
            _order(
                order_code="ORIGIN-IN-PERIOD",
                contract_id="C6",
                os_type="Ativação",
                opened_at=origin_closed_in_period - timedelta(days=2),
                closed_at=origin_closed_in_period,
            ),
            _order(
                order_code="ORIGIN-BEFORE-PERIOD",
                contract_id="C7",
                os_type="Mud. de Tecnologia",
                opened_at=origin_closed_before_period - timedelta(days=2),
                closed_at=origin_closed_before_period,
            ),
            _order(
                order_code="RETURN-6",
                contract_id="C6",
                os_type="Manutenção",
                opened_at=origin_closed_in_period + timedelta(days=1),
            ),
            _order(
                order_code="MAINTENANCE-NO-ORIGIN",
                contract_id="C8",
                os_type="Manutenção",
                opened_at=origin_closed_in_period + timedelta(days=1),
            ),
        ]
    )
    db_session.flush()

    def count_for(denominator):
        response = client.get(
            "/api/operations/warranty",
            params={
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "denominator": denominator,
            },
        )
        assert response.status_code == 200
        return response.json()

    closed_origins = count_for("closed_origins")
    assert closed_origins["denominator_count"] == 1  # só a origem fechada dentro do período

    active_origins = count_for("active_origins")
    assert active_origins["denominator_count"] == 2  # inclui a origem de fora cuja janela ainda cruza o período

    maintenance_total = count_for("maintenance_total")
    assert maintenance_total["denominator_count"] == 2  # RETURN-6 e MAINTENANCE-NO-ORIGIN

    activation_closed = count_for("activation_closed")
    assert activation_closed["denominator_count"] == 1  # só ORIGIN-IN-PERIOD é Ativação fechada no período
