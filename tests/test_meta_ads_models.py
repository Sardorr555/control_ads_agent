"""
Unit tests for Meta (Instagram / Facebook) Ads DTO Models and Financial Zero-Trust Rules.
"""
import pytest
from pydantic import ValidationError
from src.models.meta_ads import (
    MetaTargetingDTO,
    MetaAdCreativeDTO,
    MetaAdSetDTO,
    MetaCampaignDTO,
    MetaEntityStatus,
    MetaCampaignObjective,
    MetaBillingEvent,
    MetaOptimizationGoal,
    MetaAdsSafetyViolation,
)


def test_meta_targeting_dto_defaults_and_custom():
    targeting = MetaTargetingDTO()
    assert "UZ" in targeting.countries
    assert "KZ" in targeting.countries
    assert "Tashkent" in targeting.cities
    assert "instagram" in targeting.publisher_platforms
    assert "facebook" in targeting.publisher_platforms

    custom = MetaTargetingDTO(
        countries=["UZ"],
        cities=["Tashkent", "Samarkand"],
        age_min=25,
        age_max=55,
        interests=["Fintech", "Banking AI"]
    )
    assert custom.countries == ["UZ"]
    assert custom.age_min == 25
    assert custom.age_max == 55
    assert len(custom.interests) == 2


def test_meta_ad_creative_validation():
    creative = MetaAdCreativeDTO(
        name="SWIPIES_B2B_Creative_1",
        headline="SWIPIES: Enterprise RAG",
        primary_text="Secure local knowledge base search with zero hallucination. Built for banks and enterprise.",
        website_url="https://swipies.io/enterprise",
        call_to_action="LEARN_MORE",
    )
    assert creative.headline == "SWIPIES: Enterprise RAG"
    assert "utm_source=meta" in creative.url_tags
    assert "{fbclid}" in creative.url_tags

    with pytest.raises((ValidationError, ValueError), match="Invalid website URL"):
        MetaAdCreativeDTO(
            name="Invalid_URL_Creative",
            headline="Headline",
            primary_text="Body text that has more than ten characters.",
            website_url="ftp://bad-schema.com"
        )

    with pytest.raises((ValidationError, ValueError), match="utm_source=meta"):
        MetaAdCreativeDTO(
            name="Bad_Tracking_Creative",
            headline="Headline",
            primary_text="Body text that has more than ten characters.",
            website_url="https://swipies.io",
            url_tags="utm_source=other&utm_medium=cpc"
        )


def test_meta_campaign_zero_trust_status_guard():
    with pytest.raises((ValidationError, ValueError), match="Financial Zero-Trust Violation"):
        MetaCampaignDTO(
            name="Test_Active_Violation",
            daily_budget_cents=2000,
            status=MetaEntityStatus.ACTIVE,
            allow_live_enabled=False
        )

    camp = MetaCampaignDTO(
        name="Test_Active_Allowed",
        daily_budget_cents=2000,
        status=MetaEntityStatus.ACTIVE,
        allow_live_enabled=True
    )
    assert camp.status == MetaEntityStatus.ACTIVE


def test_meta_campaign_budget_and_summary():
    creative = MetaAdCreativeDTO(
        name="Card_1",
        headline="Enterprise AI",
        primary_text="Secure corporate search engine for enterprise teams.",
        website_url="https://swipies.io",
    )
    adset = MetaAdSetDTO(
        name="Fintech_Execs",
        daily_budget_cents=2500,
        creatives=[creative]
    )
    campaign = MetaCampaignDTO(
        name="SWIPIES_LeadGen_Camp",
        daily_budget_cents=2500,
        status=MetaEntityStatus.PAUSED,
        ad_sets=[adset]
    )

    assert campaign.daily_budget_usd == 25.0
    summary = campaign.get_summary()
    assert summary["name"] == "SWIPIES_LeadGen_Camp"
    assert summary["status"] == "PAUSED"
    assert summary["daily_budget_usd"] == "$25.00"
    assert summary["ad_sets_count"] == 1
    assert summary["creatives_count"] == 1
    assert "instagram" in summary["platforms"]
