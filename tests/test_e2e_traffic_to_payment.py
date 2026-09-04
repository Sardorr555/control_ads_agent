"""
End-to-End Integration Test: Traffic Acquisition -> Tracker Service -> SQLite Ingestion -> MySQL Payment View -> Attribution Engine -> CLI Report.
Validates Gate 4 full-funnel flow.
"""
import os
import json
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from src.tracker_service import create_app
from src.storage.sqlite_events_repo import SQLiteEventsRepo
from src.core.matcher import SessionMatcher
from src.core.metrics_engine import MetricsEngine
from src.core.retention_guard import RetentionGuard


@pytest.fixture
def e2e_env(tmp_path):
    db_file = str(tmp_path / "e2e_attribution.db")
    app = create_app(db_path=db_file, base_salt="e2e_test_secret_salt_32_bytes_long_ok")
    client = app.test_client()
    repo = SQLiteEventsRepo(db_path=db_file)
    return {
        "client": client,
        "repo": repo,
        "db_path": db_file
    }


def test_full_traffic_to_payment_funnel(e2e_env):
    client = e2e_env["client"]
    repo = e2e_env["repo"]

    session_id = "swp_e2e_meta_user_987654"
    client_ip = "84.54.70.100"  # Uzbekistan IP (Tashkent)
    headers = {
        "X-Forwarded-For": client_ip,
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
    }

    # Step 1: User arrives via Meta Instagram Ad
    event_visit = {
        "session_id": session_id,
        "page_path": "/pricing",
        "time_on_page_sec": 45,
        "utm_source": "meta",
        "utm_medium": "cpc",
        "utm_campaign": "b2b_fintech",
        "utm_content": "carousel_v1",
        "utm_term": "invoice_automation",
        "referrer": "https://l.instagram.com/",
        "event_type": "pageview"
    }

    resp1 = client.post("/api/v1/track/event", json=event_visit, headers=headers)
    assert resp1.status_code == 200
    assert resp1.json["success"] is True
    assert resp1.json["saved"] == 1


    # Step 2: User spends time and navigates to checkout
    event_checkout = {
        "session_id": session_id,
        "page_path": "/checkout",
        "time_on_page_sec": 120,
        "utm_source": "meta",
        "utm_medium": "cpc",
        "utm_campaign": "b2b_fintech",
        "event_type": "heartbeat"
    }
    resp2 = client.post("/api/v1/track/event", json=event_checkout, headers=headers)
    assert resp2.status_code == 200

    # Step 3: Verify SQLite raw events stored with irreversible ip_hash and without raw IP
    events = repo.get_events_by_session(session_id)
    assert len(events) == 2
    for ev in events:
        assert ev["session_id"] == session_id
        assert ev["country"] == "UZ"
        assert len(ev["ip_hash"]) == 64
        # Verify raw IP was NEVER stored in any column
        assert client_ip not in str(ev.values())

    # Step 4: User completes payment in core system (simulating v_attribution_payments record)
    payment_time = datetime.now(timezone.utc)
    mock_payments = [
        {
            "payment_id": 9991,
            "transaction_id": "tx_e2e_uzs_1500000",
            "payment_time": payment_time,
            "amount_uzs": 1500000,
            "currency": "UZS",
            "payment_status": "PAID",
            "plan_type": "b2b_corporate",
            "session_id": session_id,
            "utm_source": "meta",
            "utm_campaign": "b2b_fintech",
            "masked_payer_hash": "c" * 64
        }
    ]

    # Step 5: Run Attribution Matcher
    matcher = SessionMatcher(repo=repo)
    matches = matcher.match_payments_batch(mock_payments, model="first-touch")
    assert len(matches) == 1
    m = matches[0]
    
    assert m.transaction_id == "tx_e2e_uzs_1500000"
    assert m.match_type == "session_direct"
    assert m.utm_source == "meta"
    assert m.utm_campaign == "b2b_fintech"
    assert m.amount_uzs == 1500000

    # Step 6: Compute Financial Metrics & ROAS with Ad Spend
    ad_spends = {"b2b_fintech": 300000}  # Spent 300,000 UZS on Meta Ads
    all_raw = repo.get_events_by_session(session_id)
    metrics = MetricsEngine.aggregate_campaigns(all_raw, matches, ad_spends=ad_spends)

    assert len(metrics) == 1
    metric = metrics[0]
    assert metric.campaign_name == "b2b_fintech"
    assert metric.source == "meta"
    assert metric.total_visits == 2
    assert metric.unique_sessions == 1
    assert metric.total_conversions == 1
    assert metric.total_revenue_uzs == 1500000
    assert metric.cr_percent == 100.0
    assert metric.avg_order_value_uzs == 1500000.0
    # ROAS: 1,500,000 / 300,000 = 5.0x
    assert metric.roas == 5.0

    # Step 7: Aggregate and roll up to daily_attribution_summary
    guard = RetentionGuard(repo=repo)
    upserted = guard.aggregate_and_save_daily_summary(payment_time.date(), payments=matches)
    assert upserted >= 1
    assert guard.get_summaries_count() >= 1

    with repo.get_connection() as conn:
        cursor = conn.execute("SELECT * FROM daily_attribution_summary WHERE utm_campaign = 'b2b_fintech'")
        summary = dict(cursor.fetchone())
        assert summary["visits_count"] == 2
        assert summary["unique_sessions"] == 1
        assert summary["conversions_count"] == 1
        assert summary["revenue_uzs"] == 1500000
