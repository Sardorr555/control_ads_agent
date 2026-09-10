"""
Unit and Integration tests for TwitterAdsClient in Dry-Run / Zero-Key mode.
"""
import pytest
from src.providers.twitter_ads_client import TwitterAdsClient
from src.providers.twitter_ads_service import TwitterAdsService
from src.models.twitter_ads import (
    TwitterCampaignDTO,
    TwitterEntityStatus,
    TwitterAdsSafetyViolation,
)


def test_credentials_audit_when_unconfigured():
    client = TwitterAdsClient(ads_account_id="", api_key="", bearer_token="")
    status = client.check_credentials_status()

    assert not status["ads_account_id_present"]
    assert not status["api_key_present"]
    assert not status["is_ready_for_live"]
    assert status["mode"] == "MOCK_DRY_RUN"


def test_build_api_payloads_construction():
    client = TwitterAdsClient(ads_account_id="mock_acc_123")
    service = TwitterAdsService(client=client)
    campaign = service.build_default_swipies_campaign(daily_budget_usd=15.0)

    payloads = client.build_api_payloads(campaign)

    assert "campaign" in payloads
    assert payloads["campaign"]["name"] == "SWIPIES_X_Global_B2B_Tech_RAG"
    assert payloads["campaign"]["entity_status"] == "PAUSED"
    assert payloads["campaign"]["daily_budget_amount_local_micro"] == 15_000_000

    assert len(payloads["line_items"]) == 1
    assert len(payloads["targeting"]) > 0
    assert len(payloads["promoted_tweets"]) == 1


def test_dry_run_mutation_execution():
    client = TwitterAdsClient(ads_account_id="mock_acc_456")
    service = TwitterAdsService(client=client)
    campaign = service.build_default_swipies_campaign(daily_budget_usd=18.0)

    result = client.mutate_campaign(campaign=campaign, dry_run=True)

    assert result["status"] == "SUCCESS_VALIDATED"
    assert result["platform"] == "twitter_x"
    assert result["mode"] == "DRY_RUN_SIMULATION"
    assert result["is_dry_run"] is True
    assert result["status_applied"] == "PAUSED"
    assert result["daily_budget_usd"] == 18.0
    assert "camp_" in result["created_resources"]["campaign"]
    assert len(result["created_resources"]["line_items"]) == 1
    assert len(result["created_resources"]["promoted_tweets"]) == 1


def test_live_mutation_without_approval_blocked():
    client = TwitterAdsClient(
        ads_account_id="real_acc_789",
        bearer_token="mock_live_bearer_token"
    )
    service = TwitterAdsService(client=client)
    campaign = service.build_default_swipies_campaign(daily_budget_usd=10.0)

    with pytest.raises(TwitterAdsSafetyViolation, match="Dual-Key Human Approval required"):
        client.mutate_campaign(campaign=campaign, dry_run=False, approval_token=None)
