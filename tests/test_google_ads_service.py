"""
Unit tests for GoogleAdsService and SWIPIES campaign generation.
"""
from src.providers.google_ads_service import GoogleAdsService
from src.models.google_ads import CampaignStatus


def test_build_default_swipies_campaign_structure():
    service = GoogleAdsService()
    campaign = service.build_default_swipies_campaign(daily_budget_usd=25.0)

    assert campaign.name == "SWIPIES_B2B_AI_RAG_UZ_CIS"
    assert campaign.status == CampaignStatus.PAUSED
    assert campaign.daily_budget_usd == 25.0
    assert campaign.max_daily_spend_risk_usd == 50.0
    assert len(campaign.ad_groups) == 1

    core_ag = campaign.ad_groups[0]
    assert core_ag.name == "Enterprise_RAG_Search_Core"
    assert len(core_ag.positive_keywords) >= 5
    assert len(core_ag.negative_keywords) >= 5

    # Check that negative keywords block junk traffic
    neg_texts = [kw.text for kw in core_ag.negative_keywords]
    assert "бесплатно" in neg_texts
    assert "скачать торрент" in neg_texts
    assert "вакансии" in neg_texts

    # Check RSA
    assert len(core_ag.ads) == 1
    rsa = core_ag.ads[0]
    assert len(rsa.headlines) >= 3
    assert len(rsa.descriptions) >= 2
    assert "{lpurl}" in rsa.tracking_url_template
    assert "utm_source=google" in rsa.tracking_url_template


def test_preview_campaign_summary_output():
    service = GoogleAdsService()
    campaign = service.build_default_swipies_campaign(daily_budget_usd=10.0)
    preview = service.preview_campaign_summary(campaign)

    assert "SWIPIES_B2B_AI_RAG_UZ_CIS" in preview
    assert "$10.00 / day" in preview
    assert "200% Pacing Risk Cap:    $20.00" in preview
    assert "Enterprise_RAG_Search_Core" in preview
    assert "[NEGATIVE]" in preview


def test_generate_mock_spend_report():
    service = GoogleAdsService()
    spend = service.generate_mock_spend_report(
        campaign_name="swipies_b2b_search",
        clicks=100,
        avg_cpc_usd=0.50
    )

    assert spend["campaign_name"] == "swipies_b2b_search"
    assert spend["clicks"] == 100
    assert spend["total_spend_usd"] == 50.0
    # 50 USD * 12,800 UZS = 640,000 UZS
    assert spend["total_spend_uzs"] == 640_000
