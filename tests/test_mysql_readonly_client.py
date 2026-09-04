"""
Unit tests for MySQLReadOnlyClient.
Verifies read-only query validation, session timeout enforcement,
and security isolation.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import pymysql

from src.storage.mysql_readonly_client import (
    MySQLReadOnlyClient,
    ReadOnlySecurityViolation,
    ReadOnlyQueryTimeoutError
)


def test_query_validation_allows_safe_queries():
    client = MySQLReadOnlyClient()
    
    safe_queries = [
        "SELECT * FROM swipies_db.v_attribution_payments",
        "select count(*) from v_attribution_payments where payment_time >= '2026-01-01'",
        "EXPLAIN SELECT * FROM v_attribution_payments",
        "SHOW TABLES",
        "DESCRIBE v_attribution_payments",
        "SET SESSION max_execution_time = 3000;"
    ]
    
    for q in safe_queries:
        # Should not raise exception
        client._validate_read_only_query(q)


def test_query_validation_blocks_modifications():
    client = MySQLReadOnlyClient()
    
    dangerous_queries = [
        "INSERT INTO payment_transaction (id) VALUES (1)",
        "UPDATE payment_transaction SET status='REFUNDED'",
        "DELETE FROM payment_transaction WHERE id=1",
        "DROP TABLE payment_transaction",
        "ALTER TABLE payment_transaction ADD COLUMN hack VARCHAR(10)",
        "TRUNCATE TABLE payment_transaction",
        "CREATE TABLE hack (id INT)",
        "REPLACE INTO payment_transaction VALUES (1)",
        "GRANT ALL PRIVILEGES ON *.* TO 'hacker'@'%'",
        "REVOKE SELECT ON v_attribution_payments FROM 'analytics_ro'",
        # Embedded keywords
        "SELECT * FROM v_attribution_payments; DROP TABLE users;",
        "SELECT * FROM v_attribution_payments WHERE id = 1; UPDATE users SET role='admin'"
    ]
    
    for q in dangerous_queries:
        with pytest.raises(ReadOnlySecurityViolation):
            client._validate_read_only_query(q)


@patch("pymysql.connect")
def test_connect_executes_safeguard_pragmas(mock_connect):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.open = True
    mock_connect.return_value = mock_conn

    client = MySQLReadOnlyClient(
        host="127.0.0.1",
        port=3306,
        user="analytics_ro",
        password="ro_password",
        database="swipies_db",
        max_execution_time_ms=3000
    )
    
    conn = client.connect()
    assert conn == mock_conn
    
    # Verify defense-in-depth commands executed on connect
    mock_cursor.execute.assert_any_call("SET SESSION max_execution_time = 3000;")
    mock_cursor.execute.assert_any_call("SET SESSION TRANSACTION READ ONLY;")


@patch("pymysql.connect")
def test_fetch_attribution_payments_query_construction(mock_connect):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.open = True
    mock_connect.return_value = mock_conn
    
    client = MySQLReadOnlyClient()
    start = datetime(2026, 3, 1, 0, 0, 0)
    end = datetime(2026, 3, 31, 23, 59, 59)
    
    client.fetch_attribution_payments(start_time=start, end_time=end, limit=100)
    
    executed_sql = mock_cursor.execute.call_args[0][0]
    executed_params = mock_cursor.execute.call_args[0][1]
    
    assert "FROM swipies_db.v_attribution_payments" in executed_sql
    assert "WHERE payment_time >= %s AND payment_time <= %s" in executed_sql
    assert executed_params[0] == "2026-03-01 00:00:00"
    assert executed_params[1] == "2026-03-31 23:59:59"
    assert executed_params[2] == 100


@patch("pymysql.connect")
def test_timeout_exception_translation(mock_connect):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    # Allow connection pragmas to succeed, fail on subsequent queries
    def execute_mock(sql, *args, **kwargs):
        if "SELECT" in sql.upper():
            raise pymysql.OperationalError(3024, "Query execution was interrupted, max_statement_time exceeded")
        return None

    mock_cursor.execute.side_effect = execute_mock
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.open = True
    mock_connect.return_value = mock_conn

    client = MySQLReadOnlyClient(max_execution_time_ms=3000)
    
    with pytest.raises(ReadOnlyQueryTimeoutError) as exc_info:
        client.execute_read_query("SELECT * FROM swipies_db.v_attribution_payments")
    
    assert "Query timed out after 3000ms" in str(exc_info.value)

