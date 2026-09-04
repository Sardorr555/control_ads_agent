"""
Retention Guard for Traffic Attribution Storage.
Enforces privacy, aggregation, and storage limits:
- Aggregates raw traffic events into daily_attribution_summary before deletion.
- Purges raw traffic events older than 30 days.
- Purges aggregated summaries older than 365 days.
- Prevents unbounded disk growth in high-traffic ingestion.
"""
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any
from ..storage.sqlite_events_repo import SQLiteEventsRepo
from ..models.attribution import AttributionMatchDTO

logger = logging.getLogger("swipies.attribution.retention")


class RetentionGuard:
    def __init__(self, repo: SQLiteEventsRepo):
        self.repo = repo

    def aggregate_and_save_daily_summary(
        self,
        summary_date: date,
        payments: Optional[List[AttributionMatchDTO]] = None
    ) -> int:
        """
        Aggregates raw traffic events for summary_date and idempotently upserts into daily_attribution_summary.
        Returns number of campaign rows upserted.
        """
        start_str = f"{summary_date.isoformat()}T00:00:00"
        end_str = f"{summary_date.isoformat()}T23:59:59.999999"

        # Tally conversions and revenue per campaign from attributed payments if provided
        payment_conversions: Dict[tuple, int] = {}
        payment_revenue: Dict[tuple, int] = {}
        if payments:
            for p in payments:
                p_date = p.payment_time.date() if isinstance(p.payment_time, datetime) else p.payment_time
                if p_date == summary_date:
                    k = (p.utm_source or "(none)", p.utm_medium or "(none)", p.utm_campaign or "(direct)")
                    payment_conversions[k] = payment_conversions.get(k, 0) + 1
                    payment_revenue[k] = payment_revenue.get(k, 0) + p.amount_uzs

        select_query = """
        SELECT 
            COALESCE(utm_source, '(none)') AS utm_source,
            COALESCE(utm_medium, '(none)') AS utm_medium,
            COALESCE(utm_campaign, '(direct)') AS utm_campaign,
            COUNT(*) AS visits_count,
            COUNT(DISTINCT session_id) AS unique_sessions,
            AVG(time_on_page_sec) AS avg_duration_sec
        FROM attribution_raw_events
        WHERE timestamp >= ? AND timestamp <= ?
        GROUP BY 1, 2, 3
        """

        upsert_query = """
        INSERT INTO daily_attribution_summary (
            summary_date, utm_source, utm_medium, utm_campaign,
            visits_count, unique_sessions, conversions_count, revenue_uzs,
            avg_duration_sec, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(summary_date, utm_source, utm_medium, utm_campaign)
        DO UPDATE SET
            visits_count = excluded.visits_count,
            unique_sessions = excluded.unique_sessions,
            conversions_count = excluded.conversions_count,
            revenue_uzs = excluded.revenue_uzs,
            avg_duration_sec = excluded.avg_duration_sec,
            updated_at = CURRENT_TIMESTAMP;
        """

        upserted_rows = 0
        with self.repo.get_connection() as conn:
            cursor = conn.execute(select_query, (start_str, end_str))
            rows = cursor.fetchall()
            
            # Combine all keys (traffic events + any payments without matching traffic)
            campaign_data: Dict[tuple, Dict[str, Any]] = {}
            for r in rows:
                k = (r["utm_source"], r["utm_medium"], r["utm_campaign"])
                campaign_data[k] = {
                    "visits": r["visits_count"],
                    "sessions": r["unique_sessions"],
                    "duration": float(r["avg_duration_sec"] or 0.0),
                    "conversions": payment_conversions.get(k, 0),
                    "revenue": payment_revenue.get(k, 0)
                }

            # Include any payments for campaigns without raw events on this date
            for k, conv_count in payment_conversions.items():
                if k not in campaign_data:
                    campaign_data[k] = {
                        "visits": 0,
                        "sessions": 0,
                        "duration": 0.0,
                        "conversions": conv_count,
                        "revenue": payment_revenue.get(k, 0)
                    }

            for (src, med, camp), d in campaign_data.items():
                conn.execute(
                    upsert_query,
                    (
                        summary_date.isoformat(),
                        src,
                        med,
                        camp,
                        d["visits"],
                        d["sessions"],
                        d["conversions"],
                        d["revenue"],
                        d["duration"]
                    )
                )
                upserted_rows += 1
            conn.commit()

        logger.info(f"[RetentionGuard] Aggregated {upserted_rows} summary rows for {summary_date.isoformat()}")
        return upserted_rows

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

    def archive_and_purge(
        self,
        retention_days: int = 30,
        summary_retention_days: int = 365,
        now: Optional[datetime] = None,
        payments: Optional[List[AttributionMatchDTO]] = None
    ) -> Dict[str, int]:
        """
        Pre-purge aggregation & cleanup:
        1. Identifies expiring dates before cutoff.
        2. Aggregates daily summaries to preserve historical reporting.
        3. Purges raw events older than retention_days (30d).
        4. Purges summaries older than summary_retention_days (365d).
        """
        current_time = now or datetime.now(timezone.utc)
        cutoff_date = current_time - timedelta(days=retention_days)
        cutoff_str = cutoff_date.isoformat()

        find_dates_query = """
        SELECT DISTINCT SUBSTR(timestamp, 1, 10) AS event_date 
        FROM attribution_raw_events 
        WHERE timestamp < ?
        """
        summaries_aggregated = 0
        with self.repo.get_connection() as conn:
            cursor = conn.execute(find_dates_query, (cutoff_str,))
            expiring_dates = [row[0] for row in cursor.fetchall() if row[0]]

        for d_str in expiring_dates:
            target_d = date.fromisoformat(d_str)
            summaries_aggregated += self.aggregate_and_save_daily_summary(target_d, payments=payments)

        raw_purged = self.purge_expired_raw_events(retention_days=retention_days, now=current_time)
        summaries_purged = self.purge_expired_summaries(retention_days=summary_retention_days, now=current_time)

        return {
            "summaries_aggregated": summaries_aggregated,
            "raw_events_purged": raw_purged,
            "summaries_purged": summaries_purged
        }

    def get_raw_events_count(self) -> int:
        query = "SELECT COUNT(*) FROM attribution_raw_events"
        with self.repo.get_connection() as conn:
            cursor = conn.execute(query)
            return cursor.fetchone()[0]

    def get_summaries_count(self) -> int:
        query = "SELECT COUNT(*) FROM daily_attribution_summary"
        with self.repo.get_connection() as conn:
            cursor = conn.execute(query)
            return cursor.fetchone()[0]
