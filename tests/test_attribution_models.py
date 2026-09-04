"""
Unit & Integration Tests for Attribution Matching Models:
- First-Touch Attribution
- Last-Touch Attribution
- 30-Day Attribution Window Boundary
- Payment Parameter Fallback
- IP-Hash Lookback Window Fallback
- Direct / Organic Fallback
"""
import os
import pytest
from datetime import datetime, timedelta, timezone

from src.storage.sqlite_events_repo import SQLiteEventsRepo
from src.core.matcher import SessionMatcher
from src.models.events import RawTrafficEventDTO


@pytest.fixture
def temp_repo(tmp_path):
    db_file = tmp_path / "test_attribution_matching.db"
    return SQLiteEventsRepo(db_path=str(db_file))


def test_first_touch_and_last_touch_journey(temp_repo):
    matcher = SessionMatcher(repo=temp_repo)
    session_id = "sess_journey_123"
    base_time = datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc)
    ip_hash = "a" * 64

    # Event 1: First visit from Instagram (Day 1)
    ev1 = RawTrafficEventDTO(
        session_id=session_id,
        timestamp=base_time,
        page_path="/pricing",
        time_on_page_sec=45,
        utm_source="instagram",
        utm_medium="cpc",
        utm_campaign="spring_sale",
        ip_hash=ip_hash
    )
    temp_repo.save_raw_event(ev1)

    # Event 2: Middle visit from Organic/Direct (Day 2)
    ev2 = RawTrafficEventDTO(
        session_id=session_id,
        timestamp=base_time + timedelta(days=1),
        page_path="/features",
        time_on_page_sec=60,
        utm_source=None,
        utm_medium=None,
        utm_campaign=None,
        ip_hash=ip_hash
    )
    temp_repo.save_raw_event(ev2)

    # Event 3: Final visit from Telegram channel (Day 4)
    ev3 = RawTrafficEventDTO(
        session_id=session_id,
        timestamp=base_time + timedelta(days=3),
        page_path="/checkout",
        time_on_page_sec=120,
        utm_source="telegram",
        utm_medium="social",
        utm_campaign="tg_vip_channel",
        ip_hash=ip_hash
    )
    temp_repo.save_raw_event(ev3)

    # Payment occurs on Day 4 (1 hour after checkout)
    payment_time = base_time + timedelta(days=3, hours=1)
    payment_record = {
        "transaction_id": "tx_pay_999",
        "payment_id": 101,
        "session_id": session_id,
        "payment_time": payment_time,
        "amount_uzs": 450000,
        "currency": "UZS",
        "plan_type": "pro_monthly",
        "masked_payer_hash": "b" * 64
    }

    # 1. Verify First-Touch: should credit Instagram / spring_sale
    ft_match = matcher.match_payment(payment_record, model="first-touch")
    assert ft_match.transaction_id == "tx_pay_999"
    assert ft_match.match_type == "session_direct"
    assert ft_match.utm_source == "instagram"
    assert ft_match.utm_medium == "cpc"
    assert ft_match.utm_campaign == "spring_sale"
    assert ft_match.amount_uzs == 450000
    # Time to convert: 3 days and 1 hour = 262800 seconds
    assert ft_match.time_to_convert_sec == int(timedelta(days=3, hours=1).total_seconds())

    # 2. Verify Last-Touch: should credit Telegram / tg_vip_channel
    lt_match = matcher.match_payment(payment_record, model="last-touch")
    assert lt_match.transaction_id == "tx_pay_999"
    assert lt_match.match_type == "session_direct"
    assert lt_match.utm_source == "telegram"
    assert lt_match.utm_medium == "social"
    assert lt_match.utm_campaign == "tg_vip_channel"
    assert lt_match.amount_uzs == 450000
    # Time to convert from last touch: 1 hour = 3600 seconds
    assert lt_match.time_to_convert_sec == 3600


def test_attribution_window_cutoff(temp_repo):
    matcher = SessionMatcher(repo=temp_repo, attribution_window_days=30)
    session_id = "sess_expired_window"
    ip_hash = "c" * 64

    # Event 35 days ago (outside 30-day window)
    event_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    ev = RawTrafficEventDTO(
        session_id=session_id,
        timestamp=event_time,
        page_path="/landing",
        utm_source="facebook_ads",
        utm_campaign="old_campaign",
        ip_hash=ip_hash
    )
    temp_repo.save_raw_event(ev)

    # Payment 35 days later
    payment_time = event_time + timedelta(days=35)
    payment_record = {
        "transaction_id": "tx_expired_1",
        "session_id": session_id,
        "payment_time": payment_time,
        "amount_uzs": 150000,
        "plan_type": "basic"
    }

    match = matcher.match_payment(payment_record, model="first-touch")
    # Should not credit expired campaign (>30d), falls back to direct
    assert match.match_type == "organic_unmatched"
    assert match.utm_source == "(direct)"
    assert match.utm_campaign == "(direct)"


def test_payment_utm_fallback_when_event_absent(temp_repo):
    matcher = SessionMatcher(repo=temp_repo)
    
    # Payment row has utm parameters recorded directly from session init
    payment_record = {
        "transaction_id": "tx_direct_params_1",
        "session_id": "sess_not_in_sqlite",
        "payment_time": datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
        "amount_uzs": 300000,
        "plan_type": "pro",
        "utm_source": "meta_retargeting",
        "utm_medium": "cpc",
        "utm_campaign": "march_retargeting"
    }

    match = matcher.match_payment(payment_record, model="first-touch")
    assert match.match_type == "session_direct"
    assert match.utm_source == "meta_retargeting"
    assert match.utm_campaign == "march_retargeting"


def test_ip_fallback_matching_when_session_id_absent(temp_repo):
    matcher = SessionMatcher(repo=temp_repo, ip_fallback_window_hours=24)
    ip_hash = "d" * 64
    base_time = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)

    # Traffic event without payment session, but with known ip_hash
    ev = RawTrafficEventDTO(
        session_id="sess_guest_browser",
        timestamp=base_time,
        page_path="/pricing",
        utm_source="meta_instagram",
        utm_campaign="lead_magnet",
        ip_hash=ip_hash
    )
    temp_repo.save_raw_event(ev)

    # Payment arrives 4 hours later with matching IP hash and NO session_id
    payment_time = base_time + timedelta(hours=4)
    payment_record = {
        "transaction_id": "tx_ip_fallback_1",
        "session_id": None,
        "ip_hash": ip_hash,
        "payment_time": payment_time,
        "amount_uzs": 600000,
        "plan_type": "annual"
    }

    match = matcher.match_payment(payment_record, model="last-touch")
    assert match.match_type == "ip_time_window"
    assert match.utm_source == "meta_instagram"
    assert match.utm_campaign == "lead_magnet"
    assert match.time_to_convert_sec == 4 * 3600


def test_organic_unmatched_fallback(temp_repo):
    matcher = SessionMatcher(repo=temp_repo)
    
    payment_record = {
        "transaction_id": "tx_unknown_buyer",
        "session_id": None,
        "ip_hash": "unseen_ip_hash" * 4,
        "payment_time": datetime(2026, 3, 15, 15, 0, 0, tzinfo=timezone.utc),
        "amount_uzs": 250000,
        "plan_type": "starter"
    }

    match = matcher.match_payment(payment_record, model="first-touch")
    assert match.match_type == "organic_unmatched"
    assert match.utm_source == "(direct)"
    assert match.utm_medium == "(none)"
    assert match.utm_campaign == "(direct)"
    assert match.time_to_convert_sec is None
