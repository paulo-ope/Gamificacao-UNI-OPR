from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.modules.operations.login_status_snapshot import purge_old_login_status_snapshots
from app.modules.operations.models import OperationLoginStatusSnapshot


def _snapshot(db_session, *, login_id: int, captured_at: datetime):
    db_session.add(
        OperationLoginStatusSnapshot(
            captured_at=captured_at,
            login_id=login_id,
            online="S",
        )
    )


def test_purge_removes_only_rows_older_than_retention(db_session):
    now = datetime.now(timezone.utc)
    _snapshot(db_session, login_id=1, captured_at=now - timedelta(days=30))
    _snapshot(db_session, login_id=2, captured_at=now - timedelta(days=1))
    db_session.commit()

    deleted = purge_old_login_status_snapshots(db_session, retention_days=14)

    assert deleted == 1
    remaining = db_session.scalars(select(OperationLoginStatusSnapshot.login_id)).all()
    assert remaining == [2]


def test_purge_batches_across_multiple_pages(db_session):
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=30)
    for login_id in range(5):
        _snapshot(db_session, login_id=login_id, captured_at=old)
    db_session.commit()

    deleted = purge_old_login_status_snapshots(db_session, retention_days=14, batch_size=2)

    assert deleted == 5
    assert db_session.scalar(select(OperationLoginStatusSnapshot.id)) is None


def test_purge_keeps_everything_when_nothing_is_old_enough(db_session):
    now = datetime.now(timezone.utc)
    _snapshot(db_session, login_id=1, captured_at=now - timedelta(hours=1))
    db_session.commit()

    deleted = purge_old_login_status_snapshots(db_session, retention_days=14)

    assert deleted == 0
    assert db_session.scalar(select(OperationLoginStatusSnapshot.id)) is not None
