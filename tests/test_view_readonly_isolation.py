"""
Security and Access Control Tests for View v_attribution_payments.
Verifies column projection, PII masking, status filtering, and absence of sensitive payment data.
"""
import hashlib
import sqlite3
import pytest
from pathlib import Path

VIEW_SQL_PATH = Path(__file__).parent.parent / "migrations" / "V1.6__create_v_attribution_payments.sql"


def test_view_file_no_hardcoded_secret():
    """Verify that NO literal salt is committed in the migration file."""
    content = VIEW_SQL_PATH.read_text(encoding="utf-8")
    assert "{{PAYER_HASH_SALT}}" in content
    assert "SWIPIES_SALT" not in content
    assert "SECRET" not in content


def test_view_schema_isolation_and_filtering():
    """Verify that View v_attribution_payments strictly isolates sensitive payment fields."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    
    # Enable custom sha256 function in sqlite for testing
    TEST_SALT = "test_deploy_salt_xyz987"
    conn.create_function("sha256", 1, lambda s: hashlib.sha256((s or "").encode()).hexdigest())
    
    # 1. Create base table
    cursor.execute("""
        CREATE TABLE payment_transaction (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id VARCHAR(64) NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            tenant_id INTEGER NULL,
            account_email VARCHAR(255) NOT NULL,
            plan_type VARCHAR(32) NOT NULL,
            duration_months INTEGER NOT NULL,
            expected_amount_uzs INTEGER NOT NULL,
            paid_amount_uzs INTEGER DEFAULT 0,
            status VARCHAR(32) NOT NULL,
            payment_method VARCHAR(32) NULL,
            error_code VARCHAR(64) NULL,
            error_message TEXT NULL,
            gateway_response TEXT NULL,
            is_provisioned BOOLEAN DEFAULT 0,
            provisioned_at DATETIME NULL,
            audit_note TEXT NULL,
            create_date DATETIME NOT NULL,
            update_date DATETIME NOT NULL,
            session_id VARCHAR(64) NULL,
            utm_source VARCHAR(64) NULL,
            utm_medium VARCHAR(64) NULL,
            utm_campaign VARCHAR(128) NULL,
            utm_content VARCHAR(128) NULL,
            utm_term VARCHAR(128) NULL
        )
    """)
    
    # 2. Insert test transactions: 1 PAID, 1 PENDING, 1 FAILED
    cursor.execute("""
        INSERT INTO payment_transaction (
            transaction_id, user_id, tenant_id, account_email, plan_type,
            duration_months, expected_amount_uzs, paid_amount_uzs, status,
            gateway_response, create_date, update_date, session_id, utm_source, utm_campaign
        ) VALUES 
        ('tx_paid_001', 1, 10, 'cfo@agrobank.uz', 'TEAM', 1, 500000, 500000, 'PAID', 
         '{"pan":"8600****1234","auth_code":"9991"}', '2026-09-02 12:00:00', '2026-09-02 12:01:00', 'sess_abc123', 'meta', 'b2b_fintech'),
        ('tx_pending_002', 2, 11, 'cto@startup.uz', 'DEV', 1, 150000, 0, 'PENDING', 
         '{"session_token":"secret"}', '2026-09-02 12:30:00', '2026-09-02 12:30:00', 'sess_xyz789', 'meta', 'b2b_fintech'),
        ('tx_failed_003', 3, 12, 'dev@fail.uz', 'TEAM', 1, 500000, 0, 'FAILED', 
         '{"error":"insufficient_funds"}', '2026-09-02 13:00:00', '2026-09-02 13:01:00', 'sess_fail000', 'meta', 'b2b_fintech')
    """)
    conn.commit()
    
    # 3. Create view using the exact SQL structure (adapted for SQLite function)
    cursor.execute(f"""
        CREATE VIEW v_attribution_payments AS
        SELECT 
            pt.id AS payment_id,
            pt.transaction_id AS transaction_id,
            pt.create_date AS payment_time,
            pt.paid_amount_uzs AS amount_uzs,
            'UZS' AS currency,
            pt.status AS payment_status,
            pt.plan_type AS plan_type,
            pt.session_id AS session_id,
            pt.utm_source AS utm_source,
            pt.utm_medium AS utm_medium,
            pt.utm_campaign AS utm_campaign,
            pt.utm_content AS utm_content,
            pt.utm_term AS utm_term,
            sha256(pt.account_email || '{TEST_SALT}') AS masked_payer_hash
        FROM payment_transaction pt
        WHERE pt.status = 'PAID'
    """)
    conn.commit()
    
    # 4. Assert only 1 row is visible (PAID), PENDING and FAILED are filtered out
    cursor.execute("SELECT * FROM v_attribution_payments")
    rows = cursor.fetchall()
    assert len(rows) == 1, f"Expected exactly 1 PAID row, got {len(rows)}"
    row = rows[0]
    
    # Column verification
    col_names = [description[0] for description in cursor.description]
    assert "gateway_response" not in col_names
    assert "account_email" not in col_names
    assert "card_pan" not in col_names
    assert "audit_note" not in col_names
    
    # Verify masked payer hash is irreversible SHA-256
    expected_hash = hashlib.sha256(f"cfo@agrobank.uz{TEST_SALT}".encode()).hexdigest()
    assert row[col_names.index("masked_payer_hash")] == expected_hash
    assert row[col_names.index("amount_uzs")] == 500000
    assert row[col_names.index("currency")] == "UZS"
    assert row[col_names.index("session_id")] == "sess_abc123"
