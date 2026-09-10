"""
Twitter / X Ads DTO Models and Financial Zero-Trust Validation Rules.
Conforms to X Ads API v12 specifications, audience targeting,
tweet creative validation, and Track 3 UTM attribution integration.
"""
from enum import Enum
import re
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class TwitterCampaignObjective(str, Enum):
    WEBSITE_CLICKS = "WEBSITE_CLICKS"
    ENGAGEMENTS = "ENGAGEMENTS"
    REACH = "REACH"
    AWARENESS = "AWARENESS"


class TwitterEntityStatus(str, Enum):
    PAUSED = "PAUSED"
    ACTIVE = "ACTIVE"
    DRAFT = "DRAFT"


class TwitterBidType(str, Enum):
    AUTO = "AUTO"
    TARGET = "TARGET"
    MAXIMUM = "MAXIMUM"


class TwitterPlacement(str, Enum):
    ALL_ON_TWITTER = "ALL_ON_TWITTER"
    TWITTER_TIMELINE = "TWITTER_TIMELINE"
    TWITTER_SEARCH = "TWITTER_SEARCH"


class TwitterAdsSafetyViolation(ValueError):
    """Raised when an operation violates financial or security safety constraints for X Ads."""
    pass


class TwitterTargetingDTO(BaseModel):
    keywords: List[str] = Field(default_factory=list, description="Targeting keywords/hashtags")
    follower_lookalikes: List[str] = Field(default_factory=list, description="Handles of accounts to target followers of")
    locations: List[str] = Field(default_factory=lambda: ["US", "GB", "UZ", "KZ", "DE", "AE"])
    languages: List[str] = Field(default_factory=lambda: ["en", "ru"])

    @field_validator("follower_lookalikes")
    @classmethod
    def clean_handles(cls, handles: List[str]) -> List[str]:
        cleaned = []
        for h in handles:
            h_clean = h.strip()
            if not h_clean.startswith("@"):
                h_clean = f"@{h_clean}"
            cleaned.append(h_clean)
        return cleaned


class TwitterPromotedTweetDTO(BaseModel):
    text: str = Field(..., min_length=10, max_length=2000, description="Tweet copy text")
    card_title: Optional[str] = Field(default=None, max_length=70, description="Website Card Title")
    website_url: str = Field(..., description="Target landing page URL")
    call_to_action: str = Field(default="LEARN_MORE", description="Button CTA (LEARN_MORE, SIGN_UP, VISIT_SITE)")
    tracking_url_template: Optional[str] = Field(
        default="{website_url}?utm_source=twitter&utm_medium=cpc&utm_campaign={_campaign}&utm_content={_line_item}&twclid={twclid}"
    )

    @field_validator("website_url")
    @classmethod
    def validate_website_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(f"Invalid website URL: '{v}'. Must start with http:// or https://")
        return v

    @field_validator("tracking_url_template")
    @classmethod
    def validate_tracking_template(cls, v: Optional[str]) -> Optional[str]:
        if v:
            if "{website_url}" not in v:
                raise ValueError("Tracking template must contain '{website_url}' placeholder")
            if "utm_source=twitter" not in v:
                raise ValueError("Tracking template must specify 'utm_source=twitter' for attribution")
        return v


class TwitterLineItemDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    objective: TwitterCampaignObjective = Field(default=TwitterCampaignObjective.WEBSITE_CLICKS)
    bid_amount_local_micro: int = Field(default=400_000, ge=10_000, le=50_000_000, description="Bid in micros ($0.40 = 400,000)")
    bid_type: TwitterBidType = Field(default=TwitterBidType.AUTO)
    placements: List[TwitterPlacement] = Field(
        default_factory=lambda: [TwitterPlacement.TWITTER_TIMELINE, TwitterPlacement.TWITTER_SEARCH]
    )
    targeting: TwitterTargetingDTO = Field(default_factory=TwitterTargetingDTO)
    tweets: List[TwitterPromotedTweetDTO] = Field(default_factory=list)
    status: TwitterEntityStatus = Field(default=TwitterEntityStatus.PAUSED)


class TwitterCampaignDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    daily_budget_amount_local_micro: int = Field(
        default=10_000_000,
        ge=1_000_000,
        le=500_000_000,
        description="Daily budget in micros (1,000,000 = $1.00; max $500.00)"
    )
    total_budget_amount_local_micro: Optional[int] = Field(default=None)
    status: TwitterEntityStatus = Field(default=TwitterEntityStatus.PAUSED)
    objective: TwitterCampaignObjective = Field(default=TwitterCampaignObjective.WEBSITE_CLICKS)
    line_items: List[TwitterLineItemDTO] = Field(default_factory=list)
    allow_live_enabled: bool = Field(default=False, description="Override for live activation")

    @model_validator(mode="after")
    def enforce_zero_trust_status(self) -> "TwitterCampaignDTO":
        if self.status == TwitterEntityStatus.ACTIVE and not self.allow_live_enabled:
            raise TwitterAdsSafetyViolation(
                "Financial Zero-Trust Violation: Twitter/X campaigns cannot be created in ACTIVE status. "
                "Must be created in PAUSED status to prevent accidental budget consumption."
            )
        return self

    @property
    def daily_budget_usd(self) -> float:
        return self.daily_budget_amount_local_micro / 1_000_000.0

    def get_summary(self) -> Dict[str, Any]:
        total_keywords = sum(len(li.targeting.keywords) for li in self.line_items)
        total_lookalikes = sum(len(li.targeting.follower_lookalikes) for li in self.line_items)
        total_tweets = sum(len(li.tweets) for li in self.line_items)
        return {
            "name": self.name,
            "status": self.status.value,
            "daily_budget_usd": f"${self.daily_budget_usd:.2f}",
            "objective": self.objective.value,
            "line_items_count": len(self.line_items),
            "target_keywords_count": total_keywords,
            "follower_lookalikes_count": total_lookalikes,
            "promoted_tweets_count": total_tweets,
        }
