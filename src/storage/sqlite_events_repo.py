"""
Thread-safe SQLite Repository for Attribution Events with WAL mode and Busy Retry.
Optimized for high concurrency on port 5001 ingestion.
"""
import os
import sqlite3
import time
import logging
from datetime import datetime, timezone
from typing import List, Optional
from ..models.events import RawTrafficEventDTO


class SQLiteEventsRepo:
    def __init__(self, db_path: str = "./data/attribution_events.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self.init_schema()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        # Enforce WAL mode and concurrency pragmas
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def init_schema(self):
        migration_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "migrations",
            "V1.7__create_attribution_events.sql"
        )
        if os.path.exists(migration_file):
            with open(migration_file, "r", encoding="utf-8") as f:
                ddl = f.read()
            with self.get_connection() as conn:
                conn.executescript(ddl)
        else:
            # Fallback schema if migration file path not resolved
            with self.get_connection() as conn:
                conn.execute("""
                CREATE TABLE IF NOT EXISTS attribution_raw_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id VARCHAR(64) NOT NULL,
                    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    page_path VARCHAR(255) NOT NULL,
                    time_on_page_sec INTEGER NOT NULL DEFAULT 0,
                    utm_source VARCHAR(64) NULL,
                    utm_medium VARCHAR(64) NULL,
                    utm_campaign VARCHAR(128) NULL,
                    utm_content VARCHAR(128) NULL,
                    utm_term VARCHAR(128) NULL,
                    referrer VARCHAR(512) NULL,
                    ip_hash VARCHAR(64) NOT NULL,
                    country VARCHAR(2) NULL,
                    city VARCHAR(64) NULL,
                    user_agent VARCHAR(255) NULL,
                    event_type VARCHAR(32) NOT NULL DEFAULT 'pageview'
                );
                """)
                conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_attribution_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary_date DATE NOT NULL,
                    utm_source VARCHAR(64) NOT NULL DEFAULT '(none)',
                    utm_medium VARCHAR(64) NOT NULL DEFAULT '(none)',
                    utm_campaign VARCHAR(128) NOT NULL DEFAULT '(direct)',
                    visits_count INTEGER NOT NULL DEFAULT 0,
                    unique_sessions INTEGER NOT NULL DEFAULT 0,
                    conversions_count INTEGER NOT NULL DEFAULT 0,
                    revenue_uzs INTEGER NOT NULL DEFAULT 0,
                    avg_duration_sec REAL NOT NULL DEFAULT 0.0,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(summary_date, utm_source, utm_medium, utm_campaign)
                );
                """)

    def save_raw_event(self, event: RawTrafficEventDTO, max_retries: int = 3) -> int:
        query = """
        INSERT INTO attribution_raw_events (
            session_id, timestamp, page_path, time_on_page_sec,
            utm_source, utm_medium, utm_campaign, utm_content, utm_term,
            referrer, ip_hash, country, city, user_agent, event_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            event.session_id,
            event.timestamp.isoformat(),
            event.page_path,
            event.time_on_page_sec,
            event.utm_source,
            event.utm_medium,
            event.utm_campaign,
            event.utm_content,
            event.utm_term,
            event.referrer,
            event.ip_hash,
            event.country,
            event.city,
            event.user_agent,
            event.event_type,
        )

        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    cursor = conn.execute(query, params)
                    conn.commit()
                    return cursor.lastrowid
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    time.sleep(0.05 * (2 ** attempt))
                    continue
                raise

    def get_events_by_session(self, session_id: str, limit: int = 100) -> List[dict]:
        query = """
        SELECT id, session_id, timestamp, page_path, time_on_page_sec,
               utm_source, utm_medium, utm_campaign, utm_content, utm_term,
               referrer, ip_hash, country, city, user_agent, event_type
        FROM attribution_raw_events
        WHERE session_id = ?
        ORDER BY timestamp ASC
        LIMIT ?
        """
        with self.get_connection() as conn:
            cursor = conn.execute(query, (session_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_first_touch_by_session(self, session_id: str) -> Optional[dict]:
        query = """
        SELECT id, session_id, timestamp, page_path, time_on_page_sec,
               utm_source, utm_medium, utm_campaign, utm_content, utm_term,
               referrer, ip_hash, country, city, user_agent, event_type
        FROM attribution_raw_events
        WHERE session_id = ?
        ORDER BY timestamp ASC
        LIMIT 1
        """
        with self.get_connection() as conn:
            cursor = conn.execute(query, (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_recent_events_by_ip_hash(self, ip_hash: str, since: datetime, limit: int = 50) -> List[dict]:
        query = """
        SELECT id, session_id, timestamp, page_path, time_on_page_sec,
               utm_source, utm_medium, utm_campaign, utm_content, utm_term,
               referrer, ip_hash, country, city, user_agent, event_type
        FROM attribution_raw_events
        WHERE ip_hash = ? AND timestamp >= ?
        ORDER BY timestamp DESC
        LIMIT ?
        """
        with self.get_connection() as conn:
            cursor = conn.execute(query, (ip_hash, since.isoformat(), limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_last_touch_by_session(self, session_id: str, before_time: Optional[datetime] = None) -> Optional[dict]:
        if before_time:
            query = """
            SELECT id, session_id, timestamp, page_path, time_on_page_sec,
                   utm_source, utm_medium, utm_campaign, utm_content, utm_term,
                   referrer, ip_hash, country, city, user_agent, event_type
            FROM attribution_raw_events
            WHERE session_id = ? AND timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
            """
            params = (session_id, before_time.isoformat())
        else:
            query = """
            SELECT id, session_id, timestamp, page_path, time_on_page_sec,
                   utm_source, utm_medium, utm_campaign, utm_content, utm_term,
                   referrer, ip_hash, country, city, user_agent, event_type
            FROM attribution_raw_events
            WHERE session_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """
            params = (session_id,)
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_touch_by_ip_hash(
        self,
        ip_hash: str,
        since: datetime,
        before_time: Optional[datetime] = None,
        model: str = "last-touch"
    ) -> Optional[dict]:
        order = "ASC" if model == "first-touch" else "DESC"
        if before_time:
            query = f"""
            SELECT id, session_id, timestamp, page_path, time_on_page_sec,
                   utm_source, utm_medium, utm_campaign, utm_content, utm_term,
                   referrer, ip_hash, country, city, user_agent, event_type
            FROM attribution_raw_events
            WHERE ip_hash = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp {order}
            LIMIT 1
            """
            params = (ip_hash, since.isoformat(), before_time.isoformat())
        else:
            query = f"""
            SELECT id, session_id, timestamp, page_path, time_on_page_sec,
                   utm_source, utm_medium, utm_campaign, utm_content, utm_term,
                   referrer, ip_hash, country, city, user_agent, event_type
            FROM attribution_raw_events
            WHERE ip_hash = ? AND timestamp >= ?
            ORDER BY timestamp {order}
            LIMIT 1
            """
            params = (ip_hash, since.isoformat())
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None

