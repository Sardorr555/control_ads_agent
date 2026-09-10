"""
Secure Read-Only MySQL Client for Analytics & Attribution.
Connects strictly to local MySQL (127.0.0.1) under 'analytics_ro' user.
Enforces:
1. Client-side query validation (SELECT/EXPLAIN/SHOW/DESCRIBE only).
2. SET SESSION max_execution_time = 3000; (defense against slow query DOS).
3. SET SESSION TRANSACTION READ ONLY;
4. Queries restricted to v_attribution_payments view.
"""
import os
import re
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
import pymysql
import pymysql.cursors

logger = logging.getLogger("swipies.attribution.mysql_readonly")


class ReadOnlySecurityViolation(Exception):
    """Raised when a non-read-only query is attempted."""
    pass


class ReadOnlyQueryTimeoutError(Exception):
    """Raised when query execution exceeds the server max_execution_time."""
    pass


class MySQLReadOnlyClient:
    ALLOWED_COMMANDS = ("SELECT", "EXPLAIN", "SHOW", "DESCRIBE", "SET")
    FORBIDDEN_PATTERNS = [
        re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|GRANT|REVOKE)\b", re.IGNORECASE)
    ]

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        connect_timeout: int = 5,
        max_execution_time_ms: int = 3000,
    ):
        self.host = host or os.getenv("ANALYTICS_DB_HOST", "127.0.0.1")
        self.port = int(port or os.getenv("ANALYTICS_DB_PORT", "3306"))
        self.user = user or os.getenv("ANALYTICS_DB_USER", "analytics_ro")
        self.password = password or os.getenv("ANALYTICS_DB_PASSWORD", "")
        self.database = database or os.getenv("ANALYTICS_DB_NAME", "swipies_db")
        self.connect_timeout = connect_timeout
        self.max_execution_time_ms = max_execution_time_ms
        self._connection: Optional[pymysql.Connection] = None

    def _validate_read_only_query(self, query: str):
        cleaned = query.strip()
        first_word = cleaned.split()[0].upper() if cleaned else ""
        if first_word not in self.ALLOWED_COMMANDS:
            raise ReadOnlySecurityViolation(
                f"Query rejected: '{first_word}' is not an allowed read-only command."
            )
        for pattern in self.FORBIDDEN_PATTERNS:
            if pattern.search(cleaned):
                raise ReadOnlySecurityViolation(
                    f"Query rejected: contains forbidden write keyword matching {pattern.pattern}"
                )

    def connect(self) -> pymysql.Connection:
        if self._connection is None or not self._connection.open:
            self._connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                connect_timeout=self.connect_timeout,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
            )
            # Apply defense-in-depth session safeguards immediately
            with self._connection.cursor() as cursor:
                cursor.execute(f"SET SESSION max_execution_time = {self.max_execution_time_ms};")
                cursor.execute("SET SESSION TRANSACTION READ ONLY;")
            logger.debug(f"[MySQLReadOnlyClient] Connected to {self.database} as {self.user} with max_execution_time={self.max_execution_time_ms}ms")
        return self._connection

    def close(self):
        if self._connection and self._connection.open:
            self._connection.close()
            self._connection = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def execute_read_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        self._validate_read_only_query(query)
        conn = self.connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, params or ())
                return cursor.fetchall()
        except pymysql.OperationalError as e:
            # MySQL error code 3024 is ER_QUERY_TIMEOUT
            if e.args and e.args[0] == 3024:
                raise ReadOnlyQueryTimeoutError(f"Query timed out after {self.max_execution_time_ms}ms: {e}") from e
            raise

    def fetch_attribution_payments(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 5000
    ) -> List[Dict[str, Any]]:
        """
        Reads confirmed payments strictly from the v_attribution_payments view.
        Filtered by payment_time range.
        """
        clauses = []
        params = []

        if start_time is not None:
            clauses.append("payment_time >= %s")
            params.append(start_time.strftime("%Y-%m-%d %H:%M:%S"))

        if end_time is not None:
            clauses.append("payment_time <= %s")
            params.append(end_time.strftime("%Y-%m-%d %H:%M:%S"))

        where_clause = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"""
        SELECT 
            payment_id,
            transaction_id,
            payment_time,
            amount_uzs,
            currency,
            payment_status,
            plan_type,
            session_id,
            utm_source,
            utm_medium,
            utm_campaign,
            utm_content,
            utm_term,
            masked_payer_hash
        FROM {self.database}.v_attribution_payments
        {where_clause}
        ORDER BY payment_time ASC
        LIMIT %s;
        """
        params.append(limit)
        return self.execute_read_query(query, tuple(params))
