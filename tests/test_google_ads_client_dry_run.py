"""
Unit and Integration tests for GoogleAdsClient in Dry-Run / Zero-Key mode.
"""
import pytest
from src.providers.google_ads_client import GoogleAdsClient
from src.models.google_ads import (
    GoogleCampaignDTO,
    CampaignStatus,
    GoogleAdsSafetyViolation,
)
from src.providers.google_ads_service import GoogleAdsService


def test_customer_id_sanitization():
    # Strip hyphens
    assert GoogleAdsClient.sanitize_customer_id("123-456-7890") == "1234567890"
    # Clean 10 digits unchanged
    assert GoogleAdsClient.sanitize_customer_id("9876543210") == "9876543210"
    # Invalid length defaults to safe mock
    assert GoogleAdsClient.sanitize_customer_id("123") == "1234567890"


def test_credentials_audit_when_unconfigured():
    client = GoogleAdsClient(developer_token="", client_id="", client_secret="", refresh_token="")
    status = client.check_credentials_status()

    assert not status["developer_token_present"]
    assert not status["client_id_present"]
    assert not status["is_ready_for_live"]
    assert status["mode"] == "MOCK_DRY_RUN"


def test_mutate_operations_payload_construction():
    client = GoogleAdsClient(customer_id="999-888-7777")
    service = GoogleAdsService(client=client)
    campaign = service.build_default_swipies_campaign(daily_budget_usd=12.0)

    operations = client.build_mutate_operations(campaign)
    assert len(operations) > 0

    # Operation 1: Budget
    assert "campaign_budget_operation" in operations[0]
    budget_create = operations[0]["campaign_budget_operation"]["create"]
    assert budget_create["amount_micros"] == 12_000_000

    # Operation 2: Campaign
    assert "campaign_operation" in operations[1]
    campaign_create = operations[1]["campaign_operation"]["create"]
    assert campaign_create["status"] == "PAUSED"
    assert campaign_create["advertising_channel_type"] == "SEARCH"
    assert "{lpurl}" in campaign_create["tracking_url_template"]


def test_dry_run_mutation_execution():
    client = GoogleAdsClient(customer_id="111-222-3333")
    service = GoogleAdsService(client=client)
    campaign = service.build_default_swipies_campaign(daily_budget_usd=10.0)

    result = client.mutate_campaign(campaign=campaign, dry_run=True)

    assert result["status"] == "SUCCESS_VALIDATED"
    assert result["mode"] == "DRY_RUN_SIMULATION"
    assert result["is_dry_run"] is True
    assert result["operations_count"] > 5
    assert result["status_applied"] == "PAUSED"
    assert result["daily_budget_usd"] == 10.0
    assert result["pacing_200pct_risk_usd"] == 20.0
    assert result["tracking_verified"] is True
    assert len(result["created_resources"]) >= 2
    assert any("campaigns" in res for res in result["created_resources"])


def test_live_mutation_without_approval_blocked():
    # If client has credentials but no approval token, live mutation must be strictly blocked
    client = GoogleAdsClient(
        developer_token="dev_tok_test",
        client_id="cid_test",
        client_secret="sec_test",
        refresh_token="ref_test",
        customer_id="555-666-7777"
    )
    service = GoogleAdsService(client=client)
    campaign = service.build_default_swipies_campaign(daily_budget_usd=10.0)

    with pytest.raises(GoogleAdsSafetyViolation, match="Dual-Key Human Approval required"):
        client.mutate_campaign(campaign=campaign, dry_run=False, approval_token=None)
