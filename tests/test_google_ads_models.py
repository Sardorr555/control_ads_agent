"""
Unit tests for Google Ads DTO Models and Financial Zero-Trust Rules.
"""
import pytest
from src.models.google_ads import (
    GoogleKeywordDTO,
    GoogleAdHeadlineDTO,
    GoogleAdDescriptionDTO,
    GoogleResponsiveSearchAdDTO,
    GoogleAdGroupDTO,
    GoogleCampaignDTO,
    KeywordMatchType,
    CampaignStatus,
    GoogleAdsSafetyViolation,
)


def test_keyword_match_type_formatting():
    exact_kw = GoogleKeywordDTO(text="[enterprise rag]", match_type=KeywordMatchType.EXACT)
    assert exact_kw.text == "enterprise rag"
    assert exact_kw.formatted_keyword() == "[enterprise rag]"

    phrase_kw = GoogleKeywordDTO(text='"ии для банков"', match_type=KeywordMatchType.PHRASE)
    assert phrase_kw.text == "ии для банков"
    assert phrase_kw.formatted_keyword() == '"ии для банков"'

    broad_kw = GoogleKeywordDTO(text="корпоративный ии", match_type=KeywordMatchType.BROAD)
    assert broad_kw.formatted_keyword() == "корпоративный ии"


def test_keyword_empty_text_rejected():
    with pytest.raises(ValueError, match="cannot be empty"):
        GoogleKeywordDTO(text="   ")


def test_headline_policy_exclamation_mark_rejected():
    # Google Ads strictly forbids exclamation mark in headlines
    with pytest.raises(ValueError, match="exclamation mark"):
        GoogleAdHeadlineDTO(text="Купить софт прямо сейчас!")


def test_headline_policy_length_limit():
    with pytest.raises(ValueError, match="(30 characters|exceeds 30)"):
        GoogleAdHeadlineDTO(text="Это слишком длинный заголовок для Google Ads")


def test_headline_policy_excessive_capitalization():
    with pytest.raises(ValueError, match="Excessive capitalization"):
        GoogleAdHeadlineDTO(text="КУПИТЬ СИСТЕМУ")


def test_description_policy_length_and_punctuation():
    # Valid description
    desc = GoogleAdDescriptionDTO(text="Защищенный ИИ-поиск по корпоративным базам документов. Закажите демо.")
    assert desc.text.startswith("Защищенный")

    # Exceeds 90 chars
    with pytest.raises(ValueError, match="(90 characters|exceeds 90)"):
        GoogleAdDescriptionDTO(
            text="Это невероятно длинное описание корпоративного продукта для поисковой рекламы Google, которое точно превышает девяносто знаков!"
        )

    # Repeated punctuation
    with pytest.raises(ValueError, match="Repeated punctuation"):
        GoogleAdDescriptionDTO(text="Лучший софт для банков!!")


def test_rsa_ad_validation():
    headlines = [
        GoogleAdHeadlineDTO(text="Заголовок 1"),
        GoogleAdHeadlineDTO(text="Заголовок 2"),
        GoogleAdHeadlineDTO(text="Заголовок 3"),
    ]
    descriptions = [
        GoogleAdDescriptionDTO(text="Описание номер один для проверки рекламы."),
        GoogleAdDescriptionDTO(text="Описание номер два для проверки рекламы."),
    ]

    # Valid RSA
    ad = GoogleResponsiveSearchAdDTO(
        headlines=headlines,
        descriptions=descriptions,
        final_urls=["https://swipies.io/enterprise"],
    )
    assert len(ad.headlines) == 3
    assert len(ad.descriptions) == 2

    # Less than 3 headlines rejected
    with pytest.raises(ValueError):
        GoogleResponsiveSearchAdDTO(
            headlines=headlines[:2],
            descriptions=descriptions,
            final_urls=["https://swipies.io"],
        )

    # Tracking template missing {lpurl} rejected
    with pytest.raises(ValueError, match="{lpurl}"):
        GoogleResponsiveSearchAdDTO(
            headlines=headlines,
            descriptions=descriptions,
            final_urls=["https://swipies.io"],
            tracking_url_template="https://analytics.com?utm_source=google"
        )


def test_campaign_zero_trust_status_guard():
    # Attempting to create campaign directly in ENABLED status without approval must fail!
    with pytest.raises(ValueError, match="Financial Zero-Trust Violation"):
        GoogleCampaignDTO(
            name="Test_Enabled_Violation",
            daily_budget_micros=10_000_000,
            status=CampaignStatus.ENABLED,  # FORBIDDEN!
            allow_live_enabled=False
        )


def test_campaign_pacing_200pct_risk_calculation():
    campaign = GoogleCampaignDTO(
        name="Test_Safe_Campaign",
        daily_budget_micros=15_000_000,  # $15.00
        status=CampaignStatus.PAUSED
    )
    assert campaign.daily_budget_usd == 15.0
    # 200% Pacing rule calculation
    assert campaign.max_daily_spend_risk_usd == 30.0
