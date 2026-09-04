"""
Integration tests for RetentionGuard daily aggregation:
Verifies raw events are summarized into daily_attribution_summary
before purging expired records (>30 days).
"""
import pytest
from datetime import datetime, date, timedelta, timezone

from src.storage.sqlite_events_repo import SQLiteEventsRepo
from src.core.retention_guard import RetentionGuard
from src.models.events import RawTrafficEventDTO
from src.models.attribution import AttributionMatchDTO


@pytest.fixture
def temp_repo(tmp_path):
    db_file = tmp_path / "test_aggregation.db"
    return SQLiteEventsRepo(db_path=str(db_file))


def test_aggregate_and_save_daily_summary(temp_repo):
    guard = RetentionGuard(repo=temp_repo)
    target_date = date(2026, 2, 1)
    ip_hash = "e" * 64

    # Seed events for target_date
    t1 = datetime(2026, 2, 1, 9, 30, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 2, 1, 14, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 2, 1, 16, 45, 0, tzinfo=timezone.utc)

    temp_repo.save_raw_event(
        RawTrafficEventDTO(
            session_id="session_agg_1",
            timestamp=t1,
            page_path="/home",
            time_on_page_sec=30,
            utm_source="meta",
            utm_campaign="feb_launch",
            ip_hash=ip_hash
        )
    )
    temp_repo.save_raw_event(
        RawTrafficEventDTO(
            session_id="session_agg_1",
            timestamp=t2,
            page_path="/pricing",
            time_on_page_sec=60,
            utm_source="meta",
            utm_campaign="feb_launch",
            ip_hash=ip_hash
        )
    )
    temp_repo.save_raw_event(
        RawTrafficEventDTO(
            session_id="session_agg_2",
            timestamp=t3,
            page_path="/pricing",
            time_on_page_sec=45,
            utm_source="meta",
            utm_campaign="feb_launch",
            ip_hash=ip_hash
        )
    )

    # Attribution payments on this day
    payments = [
        AttributionMatchDTO(
            transaction_id="tx_feb_1",
            session_id="session_agg_1",
            payment_time=datetime(2026, 2, 1, 15, 0, 0, tzinfo=timezone.utc),
            amount_uzs=500000,
            currency="UZS",
            plan_type="pro",
            utm_source="meta",
            utm_medium="(none)",
            utm_campaign="feb_launch",
            match_type="session_direct"
        )
    ]

    upserted = guard.aggregate_and_save_daily_summary(target_date, payments=payments)
    assert upserted == 1

    # Verify summary table row
    with temp_repo.get_connection() as conn:
        cursor = conn.execute("SELECT * FROM daily_attribution_summary WHERE summary_date = ?", (target_date.isoformat(),))
        row = dict(cursor.fetchone())
        
        assert row["utm_source"] == "meta"
        assert row["utm_campaign"] == "feb_launch"
        assert row["visits_count"] == 3
        assert row["unique_sessions"] == 2
        assert row["conversions_count"] == 1
        assert row["revenue_uzs"] == 500000
        # Avg duration: (30 + 60 + 45) / 3 = 45.0
        assert row["avg_duration_sec"] == 45.0


def test_archive_and_purge_full_cycle(temp_repo):
    guard = RetentionGuard(repo=temp_repo)
    now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    
    # Event 40 days old (should be aggregated then purged)
    old_date = (now - timedelta(days=40)).date()
    old_time = now - timedelta(days=40)
    temp_repo.save_raw_event(
        RawTrafficEventDTO(
            session_id="session_old_1",
            timestamp=old_time,
            page_path="/blog",
            time_on_page_sec=20,
            utm_source="google",
            utm_campaign="seo_article",
            ip_hash="f" * 64
        )
    )

    # Event 10 days old (should remain untouched)
    recent_time = now - timedelta(days=10)
    temp_repo.save_raw_event(
        RawTrafficEventDTO(
            session_id="session_recent_1",
            timestamp=recent_time,
            page_path="/blog",
            time_on_page_sec=15,
            utm_source="google",
            utm_campaign="seo_article",
            ip_hash="f" * 64
        )
    )


    assert guard.get_raw_events_count() == 2
    assert guard.get_summaries_count() == 0

    # Run archive_and_purge
    result = guard.archive_and_purge(retention_days=30, now=now)
    
    assert result["summaries_aggregated"] >= 1
    assert result["raw_events_purged"] == 1  # only the 40-day-old event purged
    assert result["summaries_purged"] == 0

    # Exactly 1 recent event remains in raw events
    assert guard.get_raw_events_count() == 1
    # Summary for the 40-day-old date preserved in daily_attribution_summary
    assert guard.get_summaries_count() >= 1

    with temp_repo.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM daily_attribution_summary WHERE summary_date = ?",
            (old_date.isoformat(),)
        )
        summary = dict(cursor.fetchone())
        assert summary["utm_source"] == "google"
        assert summary["utm_campaign"] == "seo_article"
        assert summary["visits_count"] == 1
