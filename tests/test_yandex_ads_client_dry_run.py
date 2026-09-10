"""
Unit and Integration tests for YandexAdsClient in Dry-Run / Zero-Key mode.
"""
import pytest
from src.providers.yandex_ads_client import YandexAdsClient
from src.providers.yandex_ads_service import YandexAdsService
from src.models.yandex_ads import (
    YandexCampaignDTO,
    YandexCampaignState,
    YandexAdsSafetyViolation,
)


def test_credentials_audit_when_unconfigured():
    client = YandexAdsClient(token="", client_login="")
    status = client.check_credentials_status()

    assert not status["token_present"]
    assert not status["is_ready_for_live"]
    assert status["mode"] == "MOCK_DRY_RUN"


def test_build_direct_payloads_construction():
    client = YandexAdsClient(token="mock_token")
    service = YandexAdsService(client=client)
    campaign = service.build_default_swipies_campaign(daily_budget_uzs=200_000)

    payloads = client.build_direct_payloads(campaign)

    assert "campaign" in payloads
    camp_item = payloads["campaign"]["params"]["Campaigns"][0]
    assert camp_item["Name"] == "SWIPIES_B2B_Yandex_UZ_RSYA"
    assert camp_item["DailyBudget"]["Amount"] == 200_000 * 1_000_000
    assert camp_item["DailyBudget"]["Mode"] == "STANDARD"

    assert len(payloads["adgroups"]) == 1
    ag = payloads["adgroups"][0]
    assert ag["Name"] == "Enterprise_AI_Search_UZ"
    assert 10335 in ag["RegionIds"]

    assert len(payloads["ads"]) == 1
    text_ad = payloads["ads"][0]["TextAd"]
    assert "utm_source=yandex" in text_ad["Href"]


def test_dry_run_mutation_execution():
    client = YandexAdsClient(token="mock_token")
    service = YandexAdsService(client=client)
    campaign = service.build_default_swipies_campaign(daily_budget_uzs=200_000)

    result = client.mutate_campaign(campaign=campaign, dry_run=True)

    assert result["status"] == "SUCCESS_VALIDATED"
    assert result["platform"] == "yandex_direct"
    assert result["mode"] == "DRY_RUN_SIMULATION"
    assert result["is_dry_run"] is True
    assert result["state_applied"] == "OFF"
    assert result["daily_budget_uzs"] == 200_000
    assert result["budget_mode"] == "STANDARD"
    assert "yand_camp_" in result["created_resources"]["campaign"]
    assert len(result["created_resources"]["ad_groups"]) == 1
    assert len(result["created_resources"]["ads"]) == 1


def test_live_mutation_without_approval_blocked():
    client = YandexAdsClient(token="mock_live_token")
    service = YandexAdsService(client=client)
    campaign = service.build_default_swipies_campaign(daily_budget_uzs=100_000)

    with pytest.raises(YandexAdsSafetyViolation, match="Dual-Key Human Approval required"):
        client.mutate_campaign(campaign=campaign, dry_run=False, approval_token=None)
