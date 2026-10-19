from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.modules.support import occurrences_service
from app.modules.support.models import SupportIxcTicket

ROLIM = "UNI - ROLIM DE MOURA"
SAO_FRANCISCO = "UNI - SAO FRANCISCO DO GUAPORE"


def _ticket(db, source_id, *, subject="211", regional=ROLIM, day=5, report="Relato", protocol=None):
    db.add(
        SupportIxcTicket(
            source_id=source_id,
            protocol=protocol or f"P{source_id}",
            subject_id=subject,
            regional=regional,
            report=report,
            created_at=datetime(2026, 10, day, 12, tzinfo=timezone.utc),
        )
    )


def test_lists_only_subject_211_with_report_and_regional(db_session):
    _ticket(db_session, "1", report="Queda de energia no bairro")
    _ticket(db_session, "2", subject="90", report="Outro assunto")
    db_session.commit()

    page = occurrences_service.list_occurrences(db_session)

    assert page["total"] == 1
    assert page["items"][0]["report"] == "Queda de energia no bairro"
    assert page["items"][0]["regional"] == ROLIM


def test_counts_by_regional_ignore_the_regional_filter(db_session):
    _ticket(db_session, "1", regional=ROLIM)
    _ticket(db_session, "2", regional=ROLIM)
    _ticket(db_session, "3", regional=SAO_FRANCISCO)
    db_session.commit()

    page = occurrences_service.list_occurrences(db_session, regional=SAO_FRANCISCO)

    assert page["total"] == 1
    assert {row["regional"]: row["count"] for row in page["by_regional"]} == {ROLIM: 2, SAO_FRANCISCO: 1}


def test_period_and_search_filters(db_session):
    _ticket(db_session, "1", day=2, report="Fibra rompida")
    _ticket(db_session, "2", day=9, report="Fibra rompida")
    _ticket(db_session, "3", day=9, report="Cliente sem acesso")
    db_session.commit()

    page = occurrences_service.list_occurrences(
        db_session, date_from=date(2026, 10, 5), date_to=date(2026, 10, 10), search="fibra"
    )

    assert [item["source_id"] for item in page["items"]] == ["2"]


def test_missing_regional_is_labelled(db_session):
    _ticket(db_session, "1", regional=None)
    db_session.commit()

    page = occurrences_service.list_occurrences(db_session)

    assert page["items"][0]["regional"] == occurrences_service.NO_REGIONAL_LABEL


def test_regional_scope_limits_and_deny_all(db_session):
    _ticket(db_session, "1", regional=ROLIM)
    _ticket(db_session, "2", regional=SAO_FRANCISCO)
    db_session.commit()

    scoped = occurrences_service.list_occurrences(db_session, allowed_regionals=[ROLIM])
    assert [item["source_id"] for item in scoped["items"]] == ["1"]
    assert [row["regional"] for row in scoped["by_regional"]] == [ROLIM]

    denied = occurrences_service.list_occurrences(db_session, deny_all=True)
    assert denied["total"] == 0 and denied["items"] == []


def test_pagination_orders_newest_first(db_session):
    for number in range(1, 4):
        _ticket(db_session, str(number), day=number)
    db_session.commit()

    page = occurrences_service.list_occurrences(db_session, limit=2, offset=0)

    assert page["total"] == 3
    assert [item["source_id"] for item in page["items"]] == ["3", "2"]


from app.modules.support.models import SupportOccurrenceDetail  # noqa: E402


def _detail(db, source_id, *, diagnosis=None, finalized_day=None, finalized_hour=14, report=None, status=None):
    db.add(
        SupportOccurrenceDetail(
            source_id=source_id,
            diagnosis_id="449" if diagnosis else None,
            diagnosis_name=diagnosis,
            ticket_status=status or ("S" if finalized_day else "EP"),
            finalized_at=datetime(2026, 10, finalized_day, finalized_hour, tzinfo=timezone.utc) if finalized_day else None,
            finalization_report=report,
        )
    )


def _seed_overview(db):
    _ticket(db, "1", regional=ROLIM, day=5)
    _detail(db, "1", diagnosis="CTO Off", finalized_day=5, report="Fibra emendada")
    _ticket(db, "2", regional=ROLIM, day=6)
    _detail(db, "2", diagnosis="CTO Off", finalized_day=6, finalized_hour=18, report="Trocado splitter")
    _ticket(db, "3", regional=SAO_FRANCISCO, day=6)
    _detail(db, "3", diagnosis="Rompimento", finalized_day=7, report="Cabo reconectado")
    _ticket(db, "4", regional=ROLIM, day=7)  # sem detalhe sincronizado: em aberto
    db.commit()


def test_overview_ranks_regional_and_diagnosis_and_splits_open(db_session):
    _seed_overview(db_session)

    result = occurrences_service.overview(db_session, date_from=date(2026, 10, 1), date_to=date(2026, 10, 10))

    assert result["kpis"]["total"] == 4
    assert result["kpis"]["open"] == 1
    assert result["kpis"]["finalized"] == 3
    assert result["kpis"]["finalization_rate_pct"] == 75.0
    assert result["top_regional"]["regional"] == ROLIM
    assert result["top_regional"]["total"] == 3 and result["top_regional"]["open"] == 1
    assert result["top_open_regional"]["regional"] == ROLIM
    assert result["top_diagnosis"]["name"] == "CTO Off"
    assert result["top_diagnosis"]["total"] == 2
    # A em aberto (ticket 4) não conta como "sem diagnóstico": o diagnóstico só nasce na finalização.
    assert result["kpis"]["without_diagnosis"] == 0
    assert [row["name"] for row in result["by_diagnosis"]] == ["CTO Off", "Rompimento"]
    assert result["top_diagnosis"]["share_pct"] == pytest.approx(66.7, abs=0.1)
    assert {(c["regional"], c["diagnosis"]): c["count"] for c in result["matrix"]}[(ROLIM, "CTO Off")] == 2


def test_overview_lists_open_items_and_finalizations_with_time_and_report(db_session):
    _seed_overview(db_session)

    result = occurrences_service.overview(db_session, date_from=date(2026, 10, 1), date_to=date(2026, 10, 10))

    assert [item["source_id"] for item in result["open_items"]] == ["4"]
    assert result["open_items"][0]["open_minutes"] is not None
    latest = result["recent_finalizations"][0]
    assert latest["source_id"] == "3"
    assert latest["finalization_report"] == "Cabo reconectado"
    assert latest["finalized_at"].day == 7
    assert latest["resolution_minutes"] == pytest.approx(26 * 60)
    assert result["kpis"]["avg_resolution_minutes"] == pytest.approx((2 * 60 + 6 * 60 + 26 * 60) / 3, abs=0.1)
    assert sum(point["finalized"] for point in result["daily"]) == 3
    assert sum(point["count"] for point in result["by_hour"]) == 4


def test_ticket_marked_solved_without_message_counts_as_finalized(db_session):
    _ticket(db_session, "1")
    _detail(db_session, "1", status="S")
    db_session.commit()

    result = occurrences_service.overview(db_session, date_from=date(2026, 10, 1), date_to=date(2026, 10, 10))

    assert result["kpis"]["finalized"] == 1 and result["kpis"]["open"] == 0
    assert result["kpis"]["avg_resolution_minutes"] is None
    # Finalizada sem diagnóstico, essa sim conta como "sem diagnóstico".
    assert result["kpis"]["without_diagnosis"] == 1
    assert [row["name"] for row in result["by_diagnosis"]] == ["Sem diagnóstico"]


def test_list_filters_by_status_and_diagnosis(db_session):
    _seed_overview(db_session)

    open_page = occurrences_service.list_occurrences(db_session, status="open")
    assert [item["source_id"] for item in open_page["items"]] == ["4"]

    page = occurrences_service.list_occurrences(db_session, diagnosis="CTO Off")
    assert page["total"] == 2
    assert all(item["diagnosis_name"] == "CTO Off" for item in page["items"])

    by_report = occurrences_service.list_occurrences(db_session, search="splitter")
    assert [item["source_id"] for item in by_report["items"]] == ["2"]


def test_sync_stores_diagnosis_and_latest_finalization(db_session, monkeypatch):
    from app.modules.support import occurrences_sync

    monkeypatch.setattr(
        occurrences_sync,
        "fetch_diagnosticos",
        lambda client: iter([{"id": "449", "descricao": "CTO Off"}, {"id": "465", "descricao": "Rompimento"}]),
    )
    monkeypatch.setattr(
        occurrences_sync,
        "fetch_ticket_finalization_messages",
        lambda client, ids: iter(
            [
                {"id_ticket": "10", "data": "2026-10-17 09:00:00", "mensagem": "primeira", "operador": "0417", "id_su_diagnostico": "449"},
                {"id_ticket": "10", "data": "2026-10-17 11:30:00", "mensagem": "final", "operador": "0417", "id_su_diagnostico": "465"},
            ]
        ),
    )
    records = [
        {"id": "10", "id_assunto": "211", "su_status": "S", "id_su_diagnostico": "465"},
        {"id": "11", "id_assunto": "211", "su_status": "EP", "id_su_diagnostico": "0"},
        {"id": "12", "id_assunto": "90", "su_status": "S", "id_su_diagnostico": "449"},
    ]

    result = occurrences_sync.sync_occurrence_details(db_session, object(), records)

    assert result == {"tickets": 2, "finalized": 1, "open": 1}
    done = db_session.query(SupportOccurrenceDetail).filter_by(source_id="10").one()
    assert done.diagnosis_name == "Rompimento"
    assert done.finalization_report == "final"
    assert done.finalized_at.hour == 11 and done.finalized_by_id == "417"
    pending = db_session.query(SupportOccurrenceDetail).filter_by(source_id="11").one()
    assert pending.diagnosis_id is None and pending.finalized_at is None


def test_list_filters_by_opening_hour(db_session):
    _ticket(db_session, "1", day=5)  # criado às 12h
    db_session.add(
        SupportIxcTicket(
            source_id="2", subject_id="211", regional=ROLIM, created_at=datetime(2026, 10, 5, 9, 30, tzinfo=timezone.utc)
        )
    )
    db_session.commit()

    page = occurrences_service.list_occurrences(db_session, hour=9)

    assert [item["source_id"] for item in page["items"]] == ["2"]


def test_daily_series_carries_open_and_average_resolution(db_session):
    _seed_overview(db_session)

    result = occurrences_service.overview(db_session, date_from=date(2026, 10, 5), date_to=date(2026, 10, 7))
    by_day = {point["day"]: point for point in result["daily"]}

    assert by_day[date(2026, 10, 7)]["open"] == 1
    assert by_day[date(2026, 10, 5)]["avg_resolution_minutes"] == pytest.approx(120.0)
    assert by_day[date(2026, 10, 7)]["avg_resolution_minutes"] is None


def test_without_diagnosis_filter_excludes_open_occurrences(db_session):
    _ticket(db_session, "1")
    _detail(db_session, "1", status="S")  # finalizada sem diagnóstico
    _ticket(db_session, "2")  # em aberto
    db_session.commit()

    page = occurrences_service.list_occurrences(db_session, diagnosis="Sem diagnóstico")

    assert [item["source_id"] for item in page["items"]] == ["1"]
