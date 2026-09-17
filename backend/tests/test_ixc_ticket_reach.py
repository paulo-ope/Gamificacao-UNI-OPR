"""Fase 1 do plano de evolução analítica do Atendimento IXC (2026-09-14): abrangência (clientes
únicos) e reincidência (mesmo cliente voltando a ligar, com ou sem ser pelo mesmo motivo)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.modules.support import ixc_ticket_reach
from app.modules.support.models import SupportIxcTicket

REGIONAL = "UNI - NOVA BRASILANDIA DOESTE"


def _ticket(db, *, source_id, customer_id, created_at, subject_id="90", regional=REGIONAL, **overrides):
    base = dict(
        source_id=source_id,
        customer_id=customer_id,
        regional=regional,
        subject_id=subject_id,
        subject_name="Sem conexão",
        created_at=created_at,
    )
    base.update(overrides)
    row = SupportIxcTicket(**base)
    db.add(row)
    return row


def _dt(y, m, d, h=10):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


def test_unique_customers_count_deduplicates_by_customer(db_session):
    _ticket(db_session, source_id="T1", customer_id="500", created_at=_dt(2026, 9, 1))
    _ticket(db_session, source_id="T2", customer_id="500", created_at=_dt(2026, 9, 2))
    _ticket(db_session, source_id="T3", customer_id="501", created_at=_dt(2026, 9, 3))
    db_session.commit()

    count = ixc_ticket_reach.unique_customers_count(db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))

    assert count == 2


def test_unique_customers_count_ignores_tickets_without_customer(db_session):
    _ticket(db_session, source_id="T1", customer_id=None, created_at=_dt(2026, 9, 1))
    db_session.commit()

    assert ixc_ticket_reach.unique_customers_count(db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30)) == 0


def test_repeat_customers_count_requires_min_tickets(db_session):
    _ticket(db_session, source_id="T1", customer_id="500", created_at=_dt(2026, 9, 1))
    _ticket(db_session, source_id="T2", customer_id="500", created_at=_dt(2026, 9, 2))
    _ticket(db_session, source_id="T3", customer_id="501", created_at=_dt(2026, 9, 3))  # só 1, não conta
    db_session.commit()

    assert ixc_ticket_reach.repeat_customers_count(db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30)) == 1


def test_repeat_contact_counts_pairs_same_customer_same_subject_within_windows(db_session):
    # Cliente 500: dois atendimentos do MESMO motivo (90) com 10h de intervalo -> conta nas 3 janelas.
    _ticket(db_session, source_id="T1", customer_id="500", subject_id="90", created_at=_dt(2026, 9, 1, 8))
    _ticket(db_session, source_id="T2", customer_id="500", subject_id="90", created_at=_dt(2026, 9, 1, 18))
    db_session.commit()

    counts = ixc_ticket_reach.repeat_contact_counts(db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))

    assert counts == {"24h": 1, "72h": 1, "7d": 1}


def test_repeat_contact_counts_respects_window_boundaries(db_session):
    # 30h de intervalo: não entra em 24h, entra em 72h e 7d.
    _ticket(db_session, source_id="T1", customer_id="500", subject_id="90", created_at=_dt(2026, 9, 1, 8))
    _ticket(db_session, source_id="T2", customer_id="500", subject_id="90", created_at=_dt(2026, 9, 2, 14))
    db_session.commit()

    counts = ixc_ticket_reach.repeat_contact_counts(db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))

    assert counts == {"24h": 0, "72h": 1, "7d": 1}


def test_repeat_contact_counts_ignores_different_subjects(db_session):
    """Dois atendimentos do MESMO cliente, mas de motivos DIFERENTES, não são reincidência do
    mesmo problema - não contam em nenhuma janela."""
    _ticket(db_session, source_id="T1", customer_id="500", subject_id="90", created_at=_dt(2026, 9, 1, 8))
    _ticket(db_session, source_id="T2", customer_id="500", subject_id="91", created_at=_dt(2026, 9, 1, 10))
    db_session.commit()

    counts = ixc_ticket_reach.repeat_contact_counts(db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))

    assert counts == {"24h": 0, "72h": 0, "7d": 0}


def test_repeat_contact_counts_counts_consecutive_pairs_not_all_combinations(db_session):
    """3 atendimentos seguidos do mesmo motivo geram 2 pares consecutivos, não 3 (não é
    "todas as combinações", é "quantas vezes ele voltou")."""
    _ticket(db_session, source_id="T1", customer_id="500", subject_id="90", created_at=_dt(2026, 9, 1, 8))
    _ticket(db_session, source_id="T2", customer_id="500", subject_id="90", created_at=_dt(2026, 9, 1, 12))
    _ticket(db_session, source_id="T3", customer_id="500", subject_id="90", created_at=_dt(2026, 9, 1, 16))
    db_session.commit()

    counts = ixc_ticket_reach.repeat_contact_counts(db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))

    assert counts["24h"] == 2


def test_reach_summary_combines_all_metrics(db_session):
    _ticket(db_session, source_id="T1", customer_id="500", subject_id="90", created_at=_dt(2026, 9, 1, 8))
    _ticket(db_session, source_id="T2", customer_id="500", subject_id="90", created_at=_dt(2026, 9, 1, 12))
    _ticket(db_session, source_id="T3", customer_id="501", subject_id="90", created_at=_dt(2026, 9, 2, 8))
    db_session.commit()

    summary = ixc_ticket_reach.reach_summary(db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))

    assert summary["unique_customers"] == 2
    assert summary["tickets_per_customer"] == 1.5  # 3 atendimentos / 2 clientes
    assert summary["repeat_customers"] == 1
    assert summary["repeat_contact"]["24h"] == 1


def test_reach_summary_tickets_per_customer_is_none_without_customers(db_session):
    summary = ixc_ticket_reach.reach_summary(db_session, date_from=date(2026, 9, 1), date_to=date(2026, 9, 30))

    assert summary["unique_customers"] == 0
    assert summary["tickets_per_customer"] is None
