"""
Unit tests for TwitterAdsService.
"""
from src.providers.twitter_ads_service import TwitterAdsService
from src.models.twitter_ads import TwitterEntityStatus, TwitterCampaignObjective


def test_build_default_swipies_campaign():
    service = TwitterAdsService()
    campaign = service.build_default_swipies_campaign(daily_budget_usd=15.0)

    assert campaign.name == "SWIPIES_X_Global_B2B_Tech_RAG"
    assert campaign.status == TwitterEntityStatus.PAUSED
    assert campaign.daily_budget_usd == 15.0
    assert campaign.objective == TwitterCampaignObjective.WEBSITE_CLICKS
    assert len(campaign.line_items) == 1

    li = campaign.line_items[0]
    assert li.name == "AI_Founders_and_Tech_Leads"
    assert "@OpenAI" in li.targeting.follower_lookalikes
    assert "@AnthropicAI" in li.targeting.follower_lookalikes
    assert "Enterprise RAG" in li.targeting.keywords

    assert len(li.tweets) == 1
    tw = li.tweets[0]
    assert "SWIPIES" in tw.text
    assert "utm_source=twitter" in tw.tracking_url_template


def test_preview_campaign_summary_output():
    service = TwitterAdsService()
    campaign = service.build_default_swipies_campaign(daily_budget_usd=20.0)
    preview = service.preview_campaign_summary(campaign)

    assert "T W I T T E R  /  X  A D S  C A M P A I G N  P R E V I E W" in preview
    assert "$20.00 / day" in preview
    assert "AI_Founders_and_Tech_Leads" in preview
    assert "@OpenAI" in preview


def test_generate_mock_spend_report():
    service = TwitterAdsService()
    spend = service.generate_mock_spend_report(
        campaign_name="swipies_x_tech_rag",
        clicks=200,
        avg_cpc_usd=0.35
    )

    assert spend["campaign_name"] == "swipies_x_tech_rag"
    assert spend["channel"] == "twitter"
    assert spend["clicks"] == 200
    assert spend["total_spend_usd"] == 70.0
    # 70 USD * 12,800 UZS = 896,000 UZS
    assert spend["total_spend_uzs"] == 896_000
