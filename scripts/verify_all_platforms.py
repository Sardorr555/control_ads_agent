"""
SWIPIES Multi-Platform Pre-Flight Verification & E2E Sanity Runner.
Verifies all 4 advertising platforms before live key configuration:
1. Google Ads (Search)
2. Twitter / X Ads (B2B Tech)
3. Meta Ads (Instagram / FB Central Asia)
4. Yandex Direct (RSYA / Search Local UZS)
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
from src.providers.meta_ads_service import MetaAdsService
from src.providers.yandex_ads_service import YandexAdsService
from src.storage.sqlite_events_repo import SQLiteEventsRepo
from src.core.matcher import SessionMatcher
from src.core.metrics_engine import MetricsEngine
from src.tracker_service import create_app


def run_verification() -> bool:
    print("\n" + "=" * 80)
    print("   S W I P I E S  4 - P L A T F O R M  P R E - K E Y  A U D I T")
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

    # ------------------------------------------------------------------
    # 3. Meta (Instagram / Facebook) Verification
    # ------------------------------------------------------------------
    meta_service = MetaAdsService()
    meta_creds = meta_service.client.check_credentials_status()
    meta_camp = meta_service.build_default_swipies_campaign(daily_budget_usd=15.0)
    meta_res = meta_service.validate_and_deploy(meta_camp, dry_run=True)

    m_status = "PASS" if meta_res.get("status") == "SUCCESS_VALIDATED" else "FAIL"
    if m_status != "PASS":
        all_passed = False

    results_table.append([
        "Meta (Instagram / FB)",
        meta_creds["mode"],
        f"${meta_camp.daily_budget_usd:.2f}/day",
        "N/A (Standard Cents)",
        meta_camp.status.value,
        "YES (url_tags + fbclid)",
        m_status
    ])

    # ------------------------------------------------------------------
    # 4. Yandex Direct (RSYA / Search) Verification
    # ------------------------------------------------------------------
    yandex_service = YandexAdsService()
    yandex_creds = yandex_service.client.check_credentials_status()
    yandex_camp = yandex_service.build_default_swipies_campaign(daily_budget_uzs=200_000)
    yandex_res = yandex_service.validate_and_deploy(yandex_camp, dry_run=True)

    y_status = "PASS" if yandex_res.get("status") == "SUCCESS_VALIDATED" else "FAIL"
    if y_status != "PASS":
        all_passed = False

    results_table.append([
        "Yandex Direct (RSYA)",
        yandex_creds["mode"],
        f"{yandex_camp.daily_budget_uzs:,} UZS/day",
        "STANDARD (0 Overspend)",
        yandex_camp.state.value,
        "YES (Href + yclid)",
        y_status
    ])

    headers = ["Platform", "Active Mode", "Budget", "Pacing Risk Cap", "Zero-Trust Status", "Tracking URL", "Pre-Flight Status"]
    print(tabulate(results_table, headers=headers, tablefmt="grid"))

    # ------------------------------------------------------------------
    # 5. Multi-Channel 4-Platform E2E Conversion & ROAS Simulation
    # ------------------------------------------------------------------
    print("\n--- [4-Channel Full-Funnel Conversion & Attribution Verification] ---")
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

    # Ingest visits from all 4 channels
    visits = [
        ("sess_verify_g1", "google", "swipies_b2b_search", "84.54.70.1"),
        ("sess_verify_t2", "twitter", "swipies_x_tech_rag", "84.54.70.2"),
        ("sess_verify_m3", "meta", "swipies_b2b_instagram", "84.54.70.3"),
        ("sess_verify_y4", "yandex", "swipies_b2b_yandex_uz", "84.54.70.4"),
    ]

    for sess_id, src, camp, ip in visits:
        client.post("/api/v1/track/event", json={
            "session_id": sess_id,
            "page_path": "/enterprise",
            "utm_source": src,
            "utm_medium": "cpc",
            "utm_campaign": camp,
            "event_type": "pageview",
        }, headers={"X-Forwarded-For": ip})

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
        },
        {
            "payment_id": 3,
            "transaction_id": "tx_m3",
            "payment_time": datetime.now(timezone.utc),
            "amount_uzs": 640000,
            "currency": "UZS",
            "payment_status": "PAID",
            "plan_type": "plus",
            "session_id": "sess_verify_m3",
        },
        {
            "payment_id": 4,
            "transaction_id": "tx_y4",
            "payment_time": datetime.now(timezone.utc),
            "amount_uzs": 1280000,
            "currency": "UZS",
            "payment_status": "PAID",
            "plan_type": "enterprise",
            "session_id": "sess_verify_y4",
        },
    ]

    matcher = SessionMatcher(repo=repo)
    matches = matcher.match_payments_batch(payments, model="first-touch")

    spends = {
        "swipies_b2b_search": 160000,     # Google ($12.50)
        "swipies_x_tech_rag": 256000,     # Twitter ($20.00)
        "swipies_b2b_instagram": 160000,  # Meta ($12.50)
        "swipies_b2b_yandex_uz": 200000,  # Yandex (200,000 UZS)
    }
    raw_campaign_events = [
        {"session_id": sess_id, "utm_source": src, "utm_medium": "cpc", "utm_campaign": camp}
        for sess_id, src, camp, _ in visits
    ]
    metrics_list = MetricsEngine.aggregate_campaigns(
        raw_events=raw_campaign_events,
        attributed_payments=matches,
        ad_spends=spends
    )

    funnel_table = []
    for m in metrics_list:
        funnel_table.append([
            m.campaign_name,
            m.source,
            m.total_visits,
            m.total_conversions,
            f"{m.total_revenue_uzs:,} UZS",
            f"{spends.get(m.campaign_name, 0):,} UZS",
            f"{m.roas}x" if m.roas else "N/A"
        ])

    print(tabulate(funnel_table, headers=["Campaign", "Source", "Visits", "Conversions", "Revenue", "Ad Spend", "ROAS"], tablefmt="grid"))

    print("\n" + "=" * 80)
    if all_passed and len(matches) == 4:
        print("   [PASS] A L L  4  P L A T F O R M S  V E R I F I E D  &  R E A D Y  F O R  K E Y S")
        print("=" * 80 + "\n")
        return True
    else:
        print("   [FAIL] V E R I F I C A T I O N  F A I L E D")
        print("=" * 80 + "\n")
        return False


if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
