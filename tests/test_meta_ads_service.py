"""
Unit tests for MetaAdsService.
"""
from src.providers.meta_ads_service import MetaAdsService
from src.models.meta_ads import MetaEntityStatus, MetaCampaignObjective


def test_build_default_swipies_campaign():
    service = MetaAdsService()
    campaign = service.build_default_swipies_campaign(daily_budget_usd=15.0)

    assert campaign.name == "SWIPIES_B2B_Meta_Instagram_LeadGen"
    assert campaign.status == MetaEntityStatus.PAUSED
    assert campaign.daily_budget_usd == 15.0
    assert campaign.objective == MetaCampaignObjective.OUTCOME_LEADS
    assert len(campaign.ad_sets) == 1

    adset = campaign.ad_sets[0]
    assert adset.name == "Directors_and_Founders_Central_Asia"
    assert "UZ" in adset.targeting.countries
    assert "KZ" in adset.targeting.countries
    assert "Artificial intelligence" in adset.targeting.interests

    assert len(adset.creatives) == 1
    cr = adset.creatives[0]
    assert "SWIPIES" in cr.headline
    assert "utm_source=meta" in cr.url_tags
    assert "fbclid={fbclid}" in cr.url_tags


def test_preview_campaign_summary_output():
    service = MetaAdsService()
    campaign = service.build_default_swipies_campaign(daily_budget_usd=25.0)
    preview = service.preview_campaign_summary(campaign)

    assert "M E T A  ( I N S T A G R A M )  A D S  P R E V I E W" in preview
    assert "$25.00 / day" in preview
    assert "Directors_and_Founders_Central_Asia" in preview
    assert "Artificial intelligence" in preview


def test_generate_mock_spend_report():
    service = MetaAdsService()
    spend = service.generate_mock_spend_report(
        campaign_name="swipies_b2b_instagram",
        clicks=300,
        avg_cpc_usd=0.28
    )

    assert spend["campaign_name"] == "swipies_b2b_instagram"
    assert spend["channel"] == "meta"
    assert spend["clicks"] == 300
    assert spend["total_spend_usd"] == 84.0
    # 84 USD * 12,800 UZS = 1,075,200 UZS
    assert spend["total_spend_uzs"] == 1_075_200
    assert spend["currency_reported"] == "USD"
