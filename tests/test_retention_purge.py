"""
Tests for Retention Guard and SQLite Events Repository (Block 1).
Validates:
1. SQLite WAL mode, busy timeout, and connection pragmas.
2. Raw events ingestion with strict Pydantic validation.
3. Accurate 30-day retention purge (deleting expired, keeping fresh).
4. Edge cases (empty database, boundary timestamps).
"""
import os
import pytest
from datetime import datetime, timedelta, timezone
from src.models.events import RawTrafficEventDTO
from src.storage.sqlite_events_repo import SQLiteEventsRepo
from src.core.retention_guard import RetentionGuard


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_attribution.db")
    repo = SQLiteEventsRepo(db_file)
    guard = RetentionGuard(repo)
    return repo, guard


def test_sqlite_wal_pragmas(temp_db):
    repo, _ = temp_db
    with repo.get_connection() as conn:
        cursor = conn.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        assert mode.upper() == "WAL"

        cursor = conn.execute("PRAGMA busy_timeout;")
        timeout = cursor.fetchone()[0]
        assert timeout >= 5000


def test_raw_event_storage_and_retrieval(temp_db):
    repo, _ = temp_db
    event = RawTrafficEventDTO(
        session_id="sess_test_12345678",
        page_path="/pricing",
        time_on_page_sec=45,
        utm_source="meta",
        utm_medium="cpc",
        utm_campaign="spring_sale",
        ip_hash="a" * 64,
        country="UZ",
        city="Tashkent",
    )
    
    event_id = repo.save_raw_event(event)
    assert event_id > 0

    events = repo.get_events_by_session("sess_test_12345678")
    assert len(events) == 1
    assert events[0]["page_path"] == "/pricing"
    assert events[0]["utm_source"] == "meta"
    assert events[0]["utm_campaign"] == "spring_sale"
    assert events[0]["ip_hash"] == "a" * 64


def test_retention_purge_exact_boundary(temp_db):
    repo, guard = temp_db
    now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)

    # Insert 4 events with different ages:
    # 1. 40 days old (should be purged)
    # 2. 31 days old (should be purged)
    # 3. 29 days old (should be preserved)
    # 4. Today (should be preserved)
    timestamps = [
        now - timedelta(days=40),
        now - timedelta(days=31),
        now - timedelta(days=29),
        now,
    ]

    for idx, ts in enumerate(timestamps):
        ev = RawTrafficEventDTO(
            session_id=f"sess_retention_{idx}",
            timestamp=ts,
            page_path=f"/page_{idx}",
            ip_hash="b" * 64,
        )
        repo.save_raw_event(ev)

    assert guard.get_raw_events_count() == 4

    # Run purge with cutoff at 30 days
    deleted = guard.purge_expired_raw_events(retention_days=30, now=now)
    assert deleted == 2

    # Remaining events must be 2
    assert guard.get_raw_events_count() == 2

    remaining_s29 = repo.get_events_by_session("sess_retention_2")
    remaining_today = repo.get_events_by_session("sess_retention_3")
    purged_s40 = repo.get_events_by_session("sess_retention_0")
    purged_s31 = repo.get_events_by_session("sess_retention_1")

    assert len(remaining_s29) == 1
    assert len(remaining_today) == 1
    assert len(purged_s40) == 0
    assert len(purged_s31) == 0


def test_retention_purge_empty_db(temp_db):
    _, guard = temp_db
    deleted = guard.purge_expired_raw_events(retention_days=30)
    assert deleted == 0
