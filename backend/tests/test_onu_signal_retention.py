from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.modules.operations.onu_signal_snapshot import purge_old_onu_signal_snapshots
from app.modules.operations.models import OperationOnuSignalSnapshot


def _snapshot(db_session, *, login_id: int, captured_at: datetime):
    db_session.add(
        OperationOnuSignalSnapshot(
            captured_at=captured_at,
            login_id=login_id,
        )
    )


def test_purge_removes_only_rows_older_than_retention(db_session):
    now = datetime.now(timezone.utc)
    _snapshot(db_session, login_id=1, captured_at=now - timedelta(days=60))
    _snapshot(db_session, login_id=2, captured_at=now - timedelta(days=1))
    db_session.commit()

    deleted = purge_old_onu_signal_snapshots(db_session, retention_days=30)

    assert deleted == 1
    remaining = db_session.scalars(select(OperationOnuSignalSnapshot.login_id)).all()
    assert remaining == [2]


def test_purge_batches_across_multiple_pages(db_session):
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=60)
    for login_id in range(5):
        _snapshot(db_session, login_id=login_id, captured_at=old)
    db_session.commit()

    deleted = purge_old_onu_signal_snapshots(db_session, retention_days=30, batch_size=2)

    assert deleted == 5
    assert db_session.scalar(select(OperationOnuSignalSnapshot.id)) is None


def test_purge_keeps_everything_when_nothing_is_old_enough(db_session):
    now = datetime.now(timezone.utc)
    _snapshot(db_session, login_id=1, captured_at=now - timedelta(hours=1))
    db_session.commit()

    deleted = purge_old_onu_signal_snapshots(db_session, retention_days=30)

    assert deleted == 0
    assert db_session.scalar(select(OperationOnuSignalSnapshot.id)) is not None
