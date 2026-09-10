"""
SWIPIES Multi-Platform Pre-Flight Verification & E2E Sanity Runner.
Verifies all advertising platforms (Google Ads, Twitter / X Ads) before live key configuration.
"""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from decimal import Decimal
from datetime import datetime, timezone
from tabulate import tabulate

from src.providers.google_ads_service import GoogleAdsService
from src.providers.twitter_ads_service import TwitterAdsService
from src.storage.sqlite_events_repo import SQLiteEventsRepo
from src.core.matcher import SessionMatcher
from src.core.metrics_engine import MetricsEngine
from src.tracker_service import create_app


def run_verification() -> bool:
    print("\n" + "=" * 80)
    print("   S W I P I E S  M U L T I - P L A T F O R M  P R E - K E Y  A U D I T")
    print("=" * 80)

    results_table = []
    all_passed = True

    # ------------------------------------------------------------------
    # 1. Google Ads Verification
    # ------------------------------------------------------------------
    google_service = GoogleAdsService()
    google_creds = google_service.client.check_credentials_status()
    google_camp = google_service.build_default_swipies_campaign(daily_budget_usd=10.0)
    google_res = google_service.validate_and_deploy(google_camp, dry_run=True)

    g_status = "PASS" if google_res.get("status") == "SUCCESS_VALIDATED" else "FAIL"
    if g_status != "PASS":
        all_passed = False

    results_table.append([
        "Google Ads (Search)",
        google_creds["mode"],
        f"${google_camp.daily_budget_usd:.2f}/day",
        f"${google_camp.max_daily_spend_risk_usd:.2f} (200% Pacing)",
        google_camp.status.value,
        "YES ({lpurl} + UTM)",
        g_status
    ])

    # ------------------------------------------------------------------
    # 2. Twitter / X Ads Verification
    # ------------------------------------------------------------------
    twitter_service = TwitterAdsService()
    twitter_creds = twitter_service.client.check_credentials_status()
    twitter_camp = twitter_service.build_default_swipies_campaign(daily_budget_usd=15.0)
    twitter_res = twitter_service.validate_and_deploy(twitter_camp, dry_run=True)

    t_status = "PASS" if twitter_res.get("status") == "SUCCESS_VALIDATED" else "FAIL"
    if t_status != "PASS":
        all_passed = False

    results_table.append([
        "Twitter / X Ads",
        twitter_creds["mode"],
        f"${twitter_camp.daily_budget_usd:.2f}/day",
        "N/A (Standard Caps)",
        twitter_camp.status.value,
        "YES ({website_url} + UTM)",
        t_status
    ])

    headers = ["Platform", "Active Mode", "Budget", "Pacing Risk Cap", "Zero-Trust Status", "Tracking URL", "Pre-Flight Status"]
    print(tabulate(results_table, headers=headers, tablefmt="grid"))

    # ------------------------------------------------------------------
    # 3. Multi-Channel E2E Conversion & ROAS Simulation
    # ------------------------------------------------------------------
    print("\n--- [Multi-Channel Full-Funnel Conversion Verification] ---")
    db_file = "./data/verify_temp.db"
    os.makedirs("./data", exist_ok=True)
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except OSError:
            pass

    app = create_app(db_path=db_file, base_salt="verify_salt_32_chars_long_1234567")
    client = app.test_client()
    repo = SQLiteEventsRepo(db_path=db_file)

    # Ingest Google Visit
    client.post("/api/v1/track/event", json={
        "session_id": "sess_verify_g1",
        "page_path": "/enterprise",
        "utm_source": "google",
        "utm_medium": "cpc",
        "utm_campaign": "swipies_b2b_search",
        "event_type": "pageview",
    }, headers={"X-Forwarded-For": "84.54.70.1"})

    # Ingest Twitter Visit
    client.post("/api/v1/track/event", json={
        "session_id": "sess_verify_t2",
        "page_path": "/enterprise",
        "utm_source": "twitter",
        "utm_medium": "cpc",
        "utm_campaign": "swipies_x_tech_rag",
        "event_type": "pageview",
    }, headers={"X-Forwarded-For": "84.54.70.2"})

    # Simulated Payments
    payments = [
        {
            "payment_id": 1,
            "transaction_id": "tx_g1",
            "payment_time": datetime.now(timezone.utc),
            "amount_uzs": 640000,
            "currency": "UZS",
            "payment_status": "PAID",
            "plan_type": "plus",
            "session_id": "sess_verify_g1",
        },
        {
            "payment_id": 2,
            "transaction_id": "tx_t2",
            "payment_time": datetime.now(timezone.utc),
            "amount_uzs": 1280000,
            "currency": "UZS",
            "payment_status": "PAID",
            "plan_type": "enterprise",
            "session_id": "sess_verify_t2",
        }
    ]

    matcher = SessionMatcher(repo=repo)
    matches = matcher.match_payments_batch(payments, model="first-touch")

    spends = {
        "swipies_b2b_search": 160000,  # $12.50
        "swipies_x_tech_rag": 256000,   # $20.00
    }
    metrics_list = MetricsEngine.aggregate_campaigns(
        raw_events=[{"utm_campaign": "swipies_b2b_search"}, {"utm_campaign": "swipies_x_tech_rag"}],
        attributed_payments=matches,
        ad_spends=spends
    )

    funnel_table = []
    for m in metrics_list:
        funnel_table.append([
            m.campaign_name,
            m.total_visits,
            m.total_conversions,
            f"{m.total_revenue_uzs:,} UZS",
            f"{spends.get(m.campaign_name, 0):,} UZS",
            f"{m.roas}x" if m.roas else "N/A"
        ])

    print(tabulate(funnel_table, headers=["Campaign", "Visits", "Conversions", "Revenue", "Ad Spend", "ROAS"], tablefmt="grid"))

    print("\n" + "=" * 80)
    if all_passed and len(matches) == 2:
        print("   [PASS] A L L  S Y S T E M S  V E R I F I E D  A N D  R E A D Y  F O R  K E Y S")
        print("=" * 80 + "\n")
        return True
    else:
        print("   [FAIL] V E R I F I C A T I O N  F A I L E D")
        print("=" * 80 + "\n")
        return False


if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
