"""
Unit tests for Twitter / X Ads DTO Models and Financial Zero-Trust Rules.
"""
import pytest
from src.models.twitter_ads import (
    TwitterTargetingDTO,
    TwitterPromotedTweetDTO,
    TwitterLineItemDTO,
    TwitterCampaignDTO,
    TwitterEntityStatus,
    TwitterCampaignObjective,
    TwitterAdsSafetyViolation,
)


def test_twitter_targeting_handle_sanitization():
    targeting = TwitterTargetingDTO(
        follower_lookalikes=["OpenAI", "@AnthropicAI", " LangChainAI "]
    )
    assert targeting.follower_lookalikes == ["@OpenAI", "@AnthropicAI", "@LangChainAI"]


def test_twitter_promoted_tweet_validation():
    # Valid tweet
    tweet = TwitterPromotedTweetDTO(
        text="Build secure enterprise RAG locally with SWIPIES. Zero hallucination retrieval.",
        website_url="https://swipies.io/enterprise",
        card_title="SWIPIES Enterprise RAG",
    )
    assert tweet.website_url == "https://swipies.io/enterprise"
    assert "{website_url}" in tweet.tracking_url_template
    assert "utm_source=twitter" in tweet.tracking_url_template

    # Invalid URL
    with pytest.raises(ValueError, match="Invalid website URL"):
        TwitterPromotedTweetDTO(
            text="Check out our system right now!",
            website_url="not_a_valid_url"
        )

    # Missing {website_url} in tracking template
    with pytest.raises(ValueError, match="{website_url}"):
        TwitterPromotedTweetDTO(
            text="Check out our system right now!",
            website_url="https://swipies.io",
            tracking_url_template="https://analytics.com?utm_source=twitter"
        )


def test_twitter_campaign_zero_trust_status_guard():
    # Attempting to create campaign directly in ACTIVE status without approval must fail!
    with pytest.raises(ValueError, match="Financial Zero-Trust Violation"):
        TwitterCampaignDTO(
            name="Test_Active_Violation",
            daily_budget_amount_local_micro=10_000_000,
            status=TwitterEntityStatus.ACTIVE,  # FORBIDDEN
            allow_live_enabled=False
        )


def test_twitter_campaign_budget_calculation():
    campaign = TwitterCampaignDTO(
        name="Test_Budget_Campaign",
        daily_budget_amount_local_micro=20_000_000,  # $20.00
        status=TwitterEntityStatus.PAUSED
    )
    assert campaign.daily_budget_usd == 20.0
