"""
Retention Guard for Traffic Attribution Storage.
Enforces privacy and storage limits:
- Purges raw traffic events older than 30 days.
- Purges aggregated summaries older than 365 days.
- Prevents unbounded disk growth in high-traffic ingestion.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from ..storage.sqlite_events_repo import SQLiteEventsRepo

logger = logging.getLogger("swipies.attribution.retention")


class RetentionGuard:
    def __init__(self, repo: SQLiteEventsRepo):
        self.repo = repo

    def purge_expired_raw_events(
        self,
        retention_days: int = 30,
        now: Optional[datetime] = None
    ) -> int:
        """
        Deletes all rows in attribution_raw_events whose timestamp is older than retention_days.
        Returns the number of rows deleted.
        """
        current_time = now or datetime.now(timezone.utc)
        cutoff_date = current_time - timedelta(days=retention_days)
        cutoff_str = cutoff_date.isoformat()

        query = "DELETE FROM attribution_raw_events WHERE timestamp < ?"
        
        with self.repo.get_connection() as conn:
            cursor = conn.execute(query, (cutoff_str,))
            deleted_count = cursor.rowcount
            conn.commit()

        logger.info(
            f"[RetentionGuard] Purged {deleted_count} raw events older than {cutoff_str} (retention: {retention_days}d)"
        )
        return deleted_count

    def purge_expired_summaries(
        self,
        retention_days: int = 365,
        now: Optional[datetime] = None
    ) -> int:
        """
        Deletes aggregated summaries older than retention_days (default 365 days).
        Returns the number of rows deleted.
        """
        current_time = now or datetime.now(timezone.utc)
        cutoff_date = (current_time - timedelta(days=retention_days)).date()
        cutoff_str = cutoff_date.isoformat()

        query = "DELETE FROM daily_attribution_summary WHERE summary_date < ?"
        
        with self.repo.get_connection() as conn:
            cursor = conn.execute(query, (cutoff_str,))
            deleted_count = cursor.rowcount
            conn.commit()

        logger.info(
            f"[RetentionGuard] Purged {deleted_count} daily summaries older than {cutoff_str} (retention: {retention_days}d)"
        )
        return deleted_count

    def get_raw_events_count(self) -> int:
        query = "SELECT COUNT(*) FROM attribution_raw_events"
        with self.repo.get_connection() as conn:
            cursor = conn.execute(query)
            return cursor.fetchone()[0]
