"""
Unit and Integration tests for MetaAdsClient in Dry-Run / Zero-Key mode.
"""
import pytest
from src.providers.meta_ads_client import MetaAdsClient
from src.providers.meta_ads_service import MetaAdsService
from src.models.meta_ads import (
    MetaCampaignDTO,
    MetaEntityStatus,
    MetaAdsSafetyViolation,
)


def test_credentials_audit_when_unconfigured():
    client = MetaAdsClient(access_token="", ad_account_id="", app_id="", app_secret="")
    status = client.check_credentials_status()

    assert not status["access_token_present"]
    assert not status["is_ready_for_live"]
    assert status["mode"] == "MOCK_DRY_RUN"


def test_sanitize_ad_account_id():
    assert MetaAdsClient.sanitize_act_id("123456789") == "act_123456789"
    assert MetaAdsClient.sanitize_act_id("act_987654321") == "act_987654321"


def test_build_graph_payloads_construction():
    client = MetaAdsClient(ad_account_id="act_11223344")
    service = MetaAdsService(client=client)
    campaign = service.build_default_swipies_campaign(daily_budget_usd=15.0)

    payloads = client.build_graph_payloads(campaign)

    assert "campaign" in payloads
    assert payloads["campaign"]["name"] == "SWIPIES_B2B_Meta_Instagram_LeadGen"
    assert payloads["campaign"]["status"] == "PAUSED"
    assert payloads["campaign"]["special_ad_categories"] == ["NONE"]

    assert len(payloads["adsets"]) == 1
    adset = payloads["adsets"][0]
    assert adset["name"] == "Directors_and_Founders_Central_Asia"
    assert adset["daily_budget"] == 1500
    assert adset["status"] == "PAUSED"
    assert "geo_locations" in adset["targeting"]
    assert len(adset["creatives"]) == 1
    assert "utm_source=meta" in adset["creatives"][0]["url_tags"]


def test_dry_run_mutation_execution():
    client = MetaAdsClient(ad_account_id="act_99887766")
    service = MetaAdsService(client=client)
    campaign = service.build_default_swipies_campaign(daily_budget_usd=20.0)

    result = client.mutate_campaign(campaign=campaign, dry_run=True)

    assert result["status"] == "SUCCESS_VALIDATED"
    assert result["platform"] == "meta_instagram"
    assert result["mode"] == "DRY_RUN_SIMULATION"
    assert result["is_dry_run"] is True
    assert result["status_applied"] == "PAUSED"
    assert result["daily_budget_usd"] == 20.0
    assert "meta_camp_" in result["created_resources"]["campaign"]
    assert len(result["created_resources"]["adsets"]) == 1
    assert len(result["created_resources"]["ads"]) == 1


def test_live_mutation_without_approval_blocked():
    client = MetaAdsClient(
        access_token="mock_live_token",
        ad_account_id="act_real_12345678"
    )
    service = MetaAdsService(client=client)
    campaign = service.build_default_swipies_campaign(daily_budget_usd=15.0)

    with pytest.raises(MetaAdsSafetyViolation, match="Dual-Key Human Approval required"):
        client.mutate_campaign(campaign=campaign, dry_run=False, approval_token=None)
