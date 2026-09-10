"""
Unit tests for YandexAdsService.
"""
from src.providers.yandex_ads_service import YandexAdsService
from src.models.yandex_ads import YandexCampaignState, YandexBudgetMode


def test_build_default_swipies_campaign():
    service = YandexAdsService()
    campaign = service.build_default_swipies_campaign(daily_budget_uzs=250_000)

    assert campaign.name == "SWIPIES_B2B_Yandex_UZ_RSYA"
    assert campaign.state == YandexCampaignState.OFF
    assert campaign.daily_budget_uzs == 250_000
    assert campaign.budget_mode == YandexBudgetMode.STANDARD
    assert len(campaign.ad_groups) == 1

    ag = campaign.ad_groups[0]
    assert ag.name == "Enterprise_AI_Search_UZ"
    assert 10335 in ag.region_ids  # Tashkent
    assert 171 in ag.region_ids    # Uzbekistan
    assert len(ag.keywords) >= 4
    assert len(ag.ads) == 1

    ad = ag.ads[0]
    assert "SWIPIES" in ad.title
    assert "utm_source=yandex" in ad.tracking_params
    assert "yclid={yclid}" in ad.tracking_params


def test_preview_campaign_summary_output():
    service = YandexAdsService()
    campaign = service.build_default_swipies_campaign(daily_budget_uzs=200_000)
    preview = service.preview_campaign_summary(campaign)

    assert "Y A N D E X  D I R E C T  C A M P A I G N  P R E V I E W" in preview
    assert "200,000 UZS" in preview
    assert "STANDARD mode: Zero overspend" in preview
    assert "Enterprise_AI_Search_UZ" in preview


def test_generate_mock_spend_report():
    service = YandexAdsService()
    spend = service.generate_mock_spend_report(
        campaign_name="swipies_b2b_yandex_uz",
        clicks=180,
        avg_cpc_uzs=5000
    )

    assert spend["campaign_name"] == "swipies_b2b_yandex_uz"
    assert spend["channel"] == "yandex"
    assert spend["clicks"] == 180
    assert spend["avg_cpc_uzs"] == 5000
    assert spend["total_spend_uzs"] == 900_000
    # 900,000 / 12,800 ~= 70.31 USD
    assert spend["total_spend_usd"] == 70.31
    assert spend["currency_reported"] == "UZS"
