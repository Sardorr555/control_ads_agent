"""
Unit tests for MetricsEngine verifying strict Decimal precision,
ROUND_HALF_UP banking rounding, and zero float drift.
"""
from decimal import Decimal
import pytest
from datetime import datetime, timezone

from src.core.metrics_engine import MetricsEngine
from src.models.attribution import AttributionMatchDTO


def test_conversion_rate_decimal_rounding():
    # 1 out of 3 conversions = 33.333333333333336% -> must be exactly Decimal("33.33")
    cr1 = MetricsEngine.calculate_cr_percent(1, 3)
    assert cr1 == Decimal("33.33")

    # 2 out of 3 conversions = 66.66666666666666% -> must round half up to Decimal("66.67")
    cr2 = MetricsEngine.calculate_cr_percent(2, 3)
    assert cr2 == Decimal("66.67")

    # 1 out of 8 = 12.5% -> Decimal("12.50")
    cr3 = MetricsEngine.calculate_cr_percent(1, 8)
    assert cr3 == Decimal("12.50")

    # 0 conversions -> Decimal("0.00")
    cr4 = MetricsEngine.calculate_cr_percent(0, 100)
    assert cr4 == Decimal("0.00")

    # Zero sessions/units -> Decimal("0.00")
    cr5 = MetricsEngine.calculate_cr_percent(5, 0)
    assert cr5 == Decimal("0.00")


def test_aov_decimal_precision():
    # 1,000,000 UZS across 3 conversions = 333,333.3333... -> 333,333.33
    aov1 = MetricsEngine.calculate_aov_uzs(1000000, 3)
    assert aov1 == Decimal("333333.33")

    # Single conversion
    aov2 = MetricsEngine.calculate_aov_uzs(500000, 1)
    assert aov2 == Decimal("500000.00")

    # Zero conversions
    aov3 = MetricsEngine.calculate_aov_uzs(500000, 0)
    assert aov3 == Decimal("0.00")


def test_roas_calculation_and_rounding():
    # 5,000,000 UZS revenue on 1,250,000 UZS spend = 4.0000
    roas1 = MetricsEngine.calculate_roas(5000000, 1250000)
    assert roas1 == Decimal("4.0000")

    # 10,000,000 UZS revenue on 3,000,000 UZS spend = 3.3333333... -> 3.3333
    roas2 = MetricsEngine.calculate_roas(10000000, 3000000)
    assert roas2 == Decimal("3.3333")

    # Zero or None spend
    assert MetricsEngine.calculate_roas(1000000, 0) is None
    assert MetricsEngine.calculate_roas(1000000, None) is None


def test_cac_and_cpl_calculation():
    spend = Decimal("2500000.00")
    # 15 leads -> 166,666.6666... -> 166,666.67
    cpl = MetricsEngine.calculate_cpl_uzs(spend, 15)
    assert cpl == Decimal("166666.67")

    # 3 paying customers -> 833,333.333... -> 833,333.33
    cac = MetricsEngine.calculate_cac_uzs(spend, 3)
    assert cac == Decimal("833333.33")

    # Zero customers
    assert MetricsEngine.calculate_cac_uzs(spend, 0) is None
    assert MetricsEngine.calculate_cpl_uzs(spend, 0) is None


def test_campaign_aggregation_metrics():
    raw_events = [
        {"utm_source": "meta", "utm_medium": "cpc", "utm_campaign": "b2b_promo", "session_id": "s1"},
        {"utm_source": "meta", "utm_medium": "cpc", "utm_campaign": "b2b_promo", "session_id": "s1"},
        {"utm_source": "meta", "utm_medium": "cpc", "utm_campaign": "b2b_promo", "session_id": "s2"},
        {"utm_source": "meta", "utm_medium": "cpc", "utm_campaign": "b2b_promo", "session_id": "s3"},
        {"utm_source": "telegram", "utm_medium": "post", "utm_campaign": "channel_ad", "session_id": "s4"},
    ]

    now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    payments = [
        AttributionMatchDTO(
            transaction_id="tx_1",
            session_id="s1",
            payment_time=now,
            amount_uzs=500000,
            currency="UZS",
            plan_type="pro",
            utm_source="meta",
            utm_medium="cpc",
            utm_campaign="b2b_promo",
            match_type="session_direct"
        ),
        AttributionMatchDTO(
            transaction_id="tx_2",
            session_id="s2",
            payment_time=now,
            amount_uzs=750000,
            currency="UZS",
            plan_type="enterprise",
            utm_source="meta",
            utm_medium="cpc",
            utm_campaign="b2b_promo",
            match_type="session_direct"
        )
    ]

    ad_spends = {"b2b_promo": 250000}
    metrics = MetricsEngine.aggregate_campaigns(raw_events, payments, ad_spends=ad_spends)
    
    assert len(metrics) == 2
    
    # Check meta b2b_promo
    meta_m = next(m for m in metrics if m.campaign_name == "b2b_promo")
    assert meta_m.source == "meta"
    assert meta_m.total_visits == 4  # 4 pageviews
    assert meta_m.unique_sessions == 3  # s1, s2, s3
    assert meta_m.total_conversions == 2
    assert meta_m.total_revenue_uzs == 1250000
    # CR = (2 / 3) * 100 = 66.67%
    assert meta_m.cr_percent == 66.67
    # AOV = 1,250,000 / 2 = 625,000.00
    assert meta_m.avg_order_value_uzs == 625000.0
    # ROAS = 1,250,000 / 250,000 = 5.0
    assert meta_m.roas == 5.0

    # Check telegram channel_ad
    tg_m = next(m for m in metrics if m.campaign_name == "channel_ad")
    assert tg_m.total_visits == 1
    assert tg_m.unique_sessions == 1
    assert tg_m.total_conversions == 0
    assert tg_m.total_revenue_uzs == 0
    assert tg_m.cr_percent == 0.0
    assert tg_m.roas is None
