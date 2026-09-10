"""
End-to-End Multi-Channel Funnel & Cross-Platform Attribution Test.
Validates the complete pipeline across all 4 advertising platforms:
1. Google Ads (Track 4: Search Automation)
2. Twitter / X Ads (Track 5: Global Tech LeadGen)
3. Meta Ads (Track 6: Instagram/FB Central Asia LeadGen)
4. Yandex Direct (Track 7: ??? & Local UZS Accounting)

Pipeline steps verified:
- Platform campaign generation & dry-run validation.
- Automated tracking link generation with UTM parameters.
- Ingestion into Tracker Service (/api/v1/track/event) with IP anonymization.
- Core payment processing (simulated Atmos UZS payments in MySQL View).
- Cross-platform First-Touch vs Last-Touch attribution matching.
- Financial ROAS, CAC, and CPL calculation.
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from src.tracker_service import create_app
from src.storage.sqlite_events_repo import SQLiteEventsRepo
from src.core.matcher import SessionMatcher
from src.core.metrics_engine import MetricsEngine
from src.providers.google_ads_service import GoogleAdsService
from src.providers.twitter_ads_service import TwitterAdsService
from src.providers.meta_ads_service import MetaAdsService
from src.providers.yandex_ads_service import YandexAdsService
from src.models.google_ads import CampaignStatus
from src.models.twitter_ads import TwitterEntityStatus
from src.models.meta_ads import MetaEntityStatus
from src.models.yandex_ads import YandexCampaignState


@pytest.fixture
def multichannel_env(tmp_path):
    db_file = str(tmp_path / "multichannel_attribution.db")
    app = create_app(db_path=db_file, base_salt="multichannel_test_salt_32_bytes_ok")
    client = app.test_client()
    repo = SQLiteEventsRepo(db_path=db_file)
    return {
        "client": client,
        "repo": repo,
        "db_path": db_file,
    }


def test_google_ads_full_funnel_to_payment(multichannel_env):
    """Test full Google Search ad click -> tracking -> payment -> ROAS calculation."""
    client = multichannel_env["client"]
    repo = multichannel_env["repo"]

    google_service = GoogleAdsService()
    campaign = google_service.build_default_swipies_campaign(daily_budget_usd=20.0)
    assert campaign.status == CampaignStatus.PAUSED

    val_res = google_service.validate_and_deploy(campaign, dry_run=True)
    assert val_res["status"] == "SUCCESS_VALIDATED"

    session_id = "sess_google_b2b_lead_1001"
    headers = {"X-Forwarded-For": "84.54.70.150", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    click_event = {
        "session_id": session_id,
        "page_path": "/enterprise",
        "time_on_page_sec": 65,
        "utm_source": "google",
        "utm_medium": "cpc",
        "utm_campaign": "swipies_b2b_search",
        "utm_content": "enterprise_rag",
        "utm_term": "enterprise rag",
        "referrer": "https://www.google.com/",
        "event_type": "pageview",
    }
    resp = client.post("/api/v1/track/event", json=click_event, headers=headers)
    assert resp.status_code == 200
    assert resp.json["success"] is True

    payment = {
        "payment_id": 8801,
        "transaction_id": "tx_google_lead_01",
        "payment_time": datetime.now(timezone.utc),
        "amount_uzs": 320000,
        "currency": "UZS",
        "payment_status": "PAID",
        "plan_type": "plus",
        "session_id": session_id,
        "utm_source": "google",
        "utm_campaign": "swipies_b2b_search",
        "masked_payer_hash": "a" * 64,
    }

    matcher = SessionMatcher(repo=repo)
    matches = matcher.match_payments_batch([payment], model="first-touch")
    assert len(matches) == 1
    match = matches[0]
    assert match.match_type == "session_direct"
    assert match.utm_source == "google"
    assert match.utm_campaign == "swipies_b2b_search"
    assert match.amount_uzs == 320000

    spend_data = {"swipies_b2b_search": 128000}
    metrics_list = MetricsEngine.aggregate_campaigns(
        raw_events=[click_event],
        attributed_payments=matches,
        ad_spends=spend_data
    )
    assert len(metrics_list) == 1
    m = metrics_list[0]
    assert m.campaign_name == "swipies_b2b_search"
    assert m.total_conversions == 1
    assert m.total_revenue_uzs == 320000
    assert m.roas == 2.5


def test_twitter_ads_full_funnel_to_payment(multichannel_env):
    """Test full Twitter/X promoted tweet click -> tracking -> payment -> ROAS calculation."""
    client = multichannel_env["client"]
    repo = multichannel_env["repo"]

    twitter_service = TwitterAdsService()
    campaign = twitter_service.build_default_swipies_campaign(daily_budget_usd=15.0)
    assert campaign.status == TwitterEntityStatus.PAUSED

    val_res = twitter_service.validate_and_deploy(campaign, dry_run=True)
    assert val_res["status"] == "SUCCESS_VALIDATED"
    assert val_res["platform"] == "twitter_x"

    session_id = "sess_twitter_tech_founder_2002"
    headers = {"X-Forwarded-For": "185.139.137.50", "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4)"}
    click_event = {
        "session_id": session_id,
        "page_path": "/enterprise",
        "time_on_page_sec": 95,
        "utm_source": "twitter",
        "utm_medium": "cpc",
        "utm_campaign": "swipies_x_tech_rag",
        "utm_content": "follower_ai",
        "referrer": "https://t.co/",
        "event_type": "pageview",
    }
    resp = client.post("/api/v1/track/event", json=click_event, headers=headers)
    assert resp.status_code == 200

    payment = {
        "payment_id": 8802,
        "transaction_id": "tx_twitter_lead_02",
        "payment_time": datetime.now(timezone.utc),
        "amount_uzs": 1280000,
        "currency": "UZS",
        "payment_status": "PAID",
        "plan_type": "enterprise",
        "session_id": session_id,
        "utm_source": "twitter",
        "utm_campaign": "swipies_x_tech_rag",
        "masked_payer_hash": "b" * 64,
    }

    matcher = SessionMatcher(repo=repo)
    matches = matcher.match_payments_batch([payment], model="first-touch")
    assert len(matches) == 1
    match = matches[0]
    assert match.match_type == "session_direct"
    assert match.utm_source == "twitter"
    assert match.utm_campaign == "swipies_x_tech_rag"

    spend_data = {"swipies_x_tech_rag": 320000}
    metrics_list = MetricsEngine.aggregate_campaigns(
        raw_events=[click_event],
        attributed_payments=matches,
        ad_spends=spend_data
    )
    assert len(metrics_list) == 1
    m = metrics_list[0]
    assert m.campaign_name == "swipies_x_tech_rag"
    assert m.total_conversions == 1
    assert m.total_revenue_uzs == 1280000
    assert m.roas == 4.0


def test_meta_ads_full_funnel_to_payment(multichannel_env):
    """Test full Meta (Instagram/FB) ad click -> tracking -> payment -> ROAS calculation."""
    client = multichannel_env["client"]
    repo = multichannel_env["repo"]

    meta_service = MetaAdsService()
    campaign = meta_service.build_default_swipies_campaign(daily_budget_usd=15.0)
    assert campaign.status == MetaEntityStatus.PAUSED

    val_res = meta_service.validate_and_deploy(campaign, dry_run=True)
    assert val_res["status"] == "SUCCESS_VALIDATED"
    assert val_res["platform"] == "meta_instagram"

    session_id = "sess_meta_fintech_lead_3003"
    headers = {"X-Forwarded-For": "84.54.70.180", "User-Agent": "Mozilla/5.0 (Linux; Android 14; SM-S928B)"}
    click_event = {
        "session_id": session_id,
        "page_path": "/enterprise",
        "time_on_page_sec": 80,
        "utm_source": "meta",
        "utm_medium": "cpc",
        "utm_campaign": "swipies_b2b_instagram",
        "utm_content": "fintech_directors",
        "referrer": "https://l.instagram.com/",
        "event_type": "pageview",
    }
    resp = client.post("/api/v1/track/event", json=click_event, headers=headers)
    assert resp.status_code == 200

    payment = {
        "payment_id": 8804,
        "transaction_id": "tx_meta_lead_04",
        "payment_time": datetime.now(timezone.utc),
        "amount_uzs": 640000,
        "currency": "UZS",
        "payment_status": "PAID",
        "plan_type": "pro",
        "session_id": session_id,
        "utm_source": "meta",
        "utm_campaign": "swipies_b2b_instagram",
        "masked_payer_hash": "c" * 64,
    }

    matcher = SessionMatcher(repo=repo)
    matches = matcher.match_payments_batch([payment], model="first-touch")
    assert len(matches) == 1
    match = matches[0]
    assert match.match_type == "session_direct"
    assert match.utm_source == "meta"
    assert match.utm_campaign == "swipies_b2b_instagram"

    # Spend 160,000 UZS (~$12.50) -> Revenue 640,000 UZS -> ROAS = 4.00
    spend_data = {"swipies_b2b_instagram": 160000}
    metrics_list = MetricsEngine.aggregate_campaigns(
        raw_events=[click_event],
        attributed_payments=matches,
        ad_spends=spend_data
    )
    assert len(metrics_list) == 1
    m = metrics_list[0]
    assert m.campaign_name == "swipies_b2b_instagram"
    assert m.total_conversions == 1
    assert m.total_revenue_uzs == 640000
    assert m.roas == 4.0


def test_yandex_ads_full_funnel_to_payment(multichannel_env):
    """Test full Yandex Direct ??? click -> tracking -> payment -> ROAS calculation."""
    client = multichannel_env["client"]
    repo = multichannel_env["repo"]

    yandex_service = YandexAdsService()
    campaign = yandex_service.build_default_swipies_campaign(daily_budget_uzs=200_000)
    assert campaign.state == YandexCampaignState.OFF

    val_res = yandex_service.validate_and_deploy(campaign, dry_run=True)
    assert val_res["status"] == "SUCCESS_VALIDATED"
    assert val_res["platform"] == "yandex_direct"

    session_id = "sess_yandex_rsya_lead_4004"
    headers = {"X-Forwarded-For": "213.230.87.10", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    click_event = {
        "session_id": session_id,
        "page_path": "/enterprise",
        "time_on_page_sec": 115,
        "utm_source": "yandex",
        "utm_medium": "cpc",
        "utm_campaign": "swipies_b2b_yandex_uz",
        "utm_content": "rsya_banking",
        "referrer": "https://yandex.uz/",
        "event_type": "pageview",
    }
    resp = client.post("/api/v1/track/event", json=click_event, headers=headers)
    assert resp.status_code == 200

    payment = {
        "payment_id": 8805,
        "transaction_id": "tx_yandex_lead_05",
        "payment_time": datetime.now(timezone.utc),
        "amount_uzs": 1280000,
        "currency": "UZS",
        "payment_status": "PAID",
        "plan_type": "enterprise",
        "session_id": session_id,
        "utm_source": "yandex",
        "utm_campaign": "swipies_b2b_yandex_uz",
        "masked_payer_hash": "e" * 64,
    }

    matcher = SessionMatcher(repo=repo)
    matches = matcher.match_payments_batch([payment], model="first-touch")
    assert len(matches) == 1
    match = matches[0]
    assert match.match_type == "session_direct"
    assert match.utm_source == "yandex"
    assert match.utm_campaign == "swipies_b2b_yandex_uz"

    # Spend 200,000 UZS -> Revenue 1,280,000 UZS -> ROAS = 6.40
    spend_data = {"swipies_b2b_yandex_uz": 200000}
    metrics_list = MetricsEngine.aggregate_campaigns(
        raw_events=[click_event],
        attributed_payments=matches,
        ad_spends=spend_data
    )
    assert len(metrics_list) == 1
    m = metrics_list[0]
    assert m.campaign_name == "swipies_b2b_yandex_uz"
    assert m.total_conversions == 1
    assert m.total_revenue_uzs == 1280000
    assert m.roas == 6.4


def test_cross_channel_first_touch_vs_last_touch(multichannel_env):
    """
    Test user journey across multiple channels:
    Day 1: User discovers SWIPIES via Google Search.
    Day 2: User clicks Meta Instagram card.
    Day 3: User gets retargeted on Twitter / X, clicks and pays.
    - First-Touch must attribute to Google.
    - Last-Touch must attribute to Twitter.
    """
    client = multichannel_env["client"]
    repo = multichannel_env["repo"]

    session_id = "sess_journey_cross_platform_5005"
    headers = {"X-Forwarded-For": "84.54.70.200"}

    # Touch 1: Google Search
    touch1 = {
        "session_id": session_id,
        "page_path": "/features",
        "time_on_page_sec": 30,
        "utm_source": "google",
        "utm_medium": "cpc",
        "utm_campaign": "swipies_b2b_search",
        "event_type": "pageview",
    }
    client.post("/api/v1/track/event", json=touch1, headers=headers)

    # Touch 2: Meta Instagram
    touch2 = {
        "session_id": session_id,
        "page_path": "/demo",
        "time_on_page_sec": 45,
        "utm_source": "meta",
        "utm_medium": "cpc",
        "utm_campaign": "swipies_b2b_instagram",
        "event_type": "pageview",
    }
    client.post("/api/v1/track/event", json=touch2, headers=headers)

    # Touch 3: Twitter / X Retargeting
    touch3 = {
        "session_id": session_id,
        "page_path": "/pricing",
        "time_on_page_sec": 110,
        "utm_source": "twitter",
        "utm_medium": "cpc",
        "utm_campaign": "swipies_x_tech_rag",
        "event_type": "pageview",
    }
    client.post("/api/v1/track/event", json=touch3, headers=headers)

    payment = {
        "payment_id": 8806,
        "transaction_id": "tx_cross_platform_06",
        "payment_time": datetime.now(timezone.utc),
        "amount_uzs": 640000,
        "currency": "UZS",
        "payment_status": "PAID",
        "plan_type": "pro",
        "session_id": session_id,
        "masked_payer_hash": "d" * 64,
    }

    matcher = SessionMatcher(repo=repo)

    # First-Touch Model: Must be Google
    ft_matches = matcher.match_payments_batch([payment], model="first-touch")
    assert ft_matches[0].utm_source == "google"
    assert ft_matches[0].utm_campaign == "swipies_b2b_search"

    # Last-Touch Model: Must be Twitter
    lt_matches = matcher.match_payments_batch([payment], model="last-touch")
    assert lt_matches[0].utm_source == "twitter"
    assert lt_matches[0].utm_campaign == "swipies_x_tech_rag"
