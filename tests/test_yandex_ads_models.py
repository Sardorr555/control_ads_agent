"""
Unit tests for Yandex Direct API v5 DTO Models and Financial Zero-Trust Rules.
"""
import pytest
from pydantic import ValidationError
from src.models.yandex_ads import (
    YandexKeywordDTO,
    YandexTextAdDTO,
    YandexAdGroupDTO,
    YandexCampaignDTO,
    YandexCampaignState,
    YandexBudgetMode,
    YandexAdsSafetyViolation,
)


def test_yandex_keyword_validation():
    # Valid keyword
    kw = YandexKeywordDTO(keyword="?? ??? ??????", bid_uzs=6000)
    assert kw.keyword == "?? ??? ??????"
    assert kw.bid_uzs == 6000

    # Clean whitespace
    kw2 = YandexKeywordDTO(keyword="  ????????????? ?????  ", bid_uzs=5000)
    assert kw2.keyword == "????????????? ?????"

    # Empty keyword
    with pytest.raises((ValidationError, ValueError), match="cannot be empty"):
        YandexKeywordDTO(keyword="   ", bid_uzs=5000)

    # Bid out of range (< 500 UZS)
    with pytest.raises(ValidationError):
        YandexKeywordDTO(keyword="test", bid_uzs=100)


def test_yandex_text_ad_validation():
    # Valid ad
    ad = YandexTextAdDTO(
        title="SWIPIES ? ????????????? ??",
        title2="RAG-????? ??? ????????????",
        text="???????? ??-????? ?? ????????????? ??????????? ?? 1 ????. ???? ??? ??????.",
        href="https://swipies.io/enterprise",
        display_url_path="enterprise",
        tracking_params="utm_source=yandex&utm_medium=cpc&utm_campaign=swipies_b2b_yandex_uz&yclid={yclid}"
    )
    assert ad.title == "SWIPIES ? ????????????? ??"
    assert "utm_source=yandex" in ad.tracking_params

    # Invalid URL
    with pytest.raises((ValidationError, ValueError), match="Invalid URL"):
        YandexTextAdDTO(
            title="Title",
            text="Body text",
            href="bad_url"
        )

    # Missing utm_source=yandex
    with pytest.raises((ValidationError, ValueError), match="utm_source=yandex"):
        YandexTextAdDTO(
            title="Title",
            text="Body text",
            href="https://swipies.io",
            tracking_params="utm_source=google&utm_medium=cpc"
        )


def test_yandex_campaign_zero_trust_state_guard():
    # Attempting to create campaign directly in ON state without override must fail!
    with pytest.raises((ValidationError, ValueError), match="Financial Zero-Trust Violation"):
        YandexCampaignDTO(
            name="Test_ON_Violation",
            daily_budget_uzs=150_000,
            state=YandexCampaignState.ON,  # FORBIDDEN without override
            allow_live_enabled=False
        )

    # Allowed when allow_live_enabled=True
    camp = YandexCampaignDTO(
        name="Test_ON_Allowed",
        daily_budget_uzs=150_000,
        state=YandexCampaignState.ON,
        allow_live_enabled=True
    )
    assert camp.state == YandexCampaignState.ON


def test_yandex_campaign_budget_mode_and_summary():
    ad = YandexTextAdDTO(
        title="SWIPIES RAG",
        text="????????????? ??-?????",
        href="https://swipies.io"
    )
    kw = YandexKeywordDTO(keyword="rag ??? ???????", bid_uzs=6000)
    ag = YandexAdGroupDTO(
        name="Fintech_Search",
        region_ids=[10335, 171],
        keywords=[kw],
        ads=[ad]
    )
    campaign = YandexCampaignDTO(
        name="SWIPIES_Yandex_Camp",
        daily_budget_uzs=200_000,
        budget_mode=YandexBudgetMode.STANDARD,
        state=YandexCampaignState.OFF,
        ad_groups=[ag]
    )

    assert campaign.daily_budget_uzs == 200_000
    assert campaign.budget_mode == YandexBudgetMode.STANDARD
    summary = campaign.get_summary()
    assert summary["name"] == "SWIPIES_Yandex_Camp"
    assert summary["state"] == "OFF"
    assert summary["daily_budget_uzs"] == "200,000 UZS"
    assert summary["budget_mode"] == "STANDARD"
    assert summary["ad_groups_count"] == 1
    assert summary["keywords_count"] == 1
    assert summary["ads_count"] == 1
