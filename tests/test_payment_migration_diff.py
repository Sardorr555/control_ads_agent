"""
Unit and Schema Regression Tests for Migration V1.5
Verifies additive nature, nullability, and non-breaking schema evolution.
"""
import re
import sqlite3
import pytest
from pathlib import Path

MIGRATION_PATH = Path(__file__).parent.parent / "migrations" / "V1.5__add_attribution_utm_columns.sql"


def test_migration_file_exists():
    assert MIGRATION_PATH.exists(), f"Migration file missing: {MIGRATION_PATH}"


def test_migration_sql_strictly_nullable():
    """Ensure every added column is explicitly NULLABLE to prevent table locks and breakages."""
    content = MIGRATION_PATH.read_text(encoding="utf-8")
    add_lines = [line.strip() for line in content.splitlines() if "ADD COLUMN" in line]
    assert len(add_lines) == 6, f"Expected 6 ADD COLUMN statements, got {len(add_lines)}"
    
    for line in add_lines:
        assert " NULL" in line, f"Column definition must be explicitly NULLABLE: {line}"
        assert "NOT NULL" not in line, f"Column must NOT be NOT NULL: {line}"


def test_migration_additive_on_existing_table():
    """Verify applying the additive schema to existing data does not alter existing rows."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    
    # 1. Create base table matching Track 2 v1.4 DDL
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
            update_date DATETIME NOT NULL
        )
    """)
    
    # 2. Insert existing baseline transaction
    cursor.execute("""
        INSERT INTO payment_transaction (
            transaction_id, user_id, tenant_id, account_email, plan_type,
            duration_months, expected_amount_uzs, paid_amount_uzs, status,
            create_date, update_date
        ) VALUES (
            'tx_legacy_001', 101, 1, 'ceo@bank.uz', 'ENTERPRISE',
            12, 15000000, 15000000, 'PAID', '2026-09-01 10:00:00', '2026-09-01 10:05:00'
        )
    """)
    conn.commit()
    
    # 3. Apply additive migration columns (adapted for SQLite alter syntax)
    cols = [
        ("session_id", "VARCHAR(64) NULL"),
        ("utm_source", "VARCHAR(64) NULL"),
        ("utm_medium", "VARCHAR(64) NULL"),
        ("utm_campaign", "VARCHAR(128) NULL"),
        ("utm_content", "VARCHAR(128) NULL"),
        ("utm_term", "VARCHAR(128) NULL"),
    ]
    for col_name, col_type in cols:
        cursor.execute(f"ALTER TABLE payment_transaction ADD COLUMN {col_name} {col_type}")
    conn.commit()
    
    # 4. Verify existing record has NULL for new columns and untouched original values
    cursor.execute("SELECT id, transaction_id, status, expected_amount_uzs, session_id, utm_source FROM payment_transaction WHERE transaction_id = 'tx_legacy_001'")
    row = cursor.fetchone()
    assert row[0] == 1
    assert row[1] == 'tx_legacy_001'
    assert row[2] == 'PAID'
    assert row[3] == 15000000
    assert row[4] is None  # session_id is NULL
    assert row[5] is None  # utm_source is NULL
