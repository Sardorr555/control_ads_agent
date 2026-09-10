"""
Meta (Instagram / Facebook) Marketing API DTO Models and Zero-Trust Safeguards.
Enforces Graph API v21.0 structures, targeting rules, ad creatives,
and Track 3 UTM attribution integration.
"""
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class MetaCampaignObjective(str, Enum):
    OUTCOME_TRAFFIC = "OUTCOME_TRAFFIC"
    OUTCOME_LEADS = "OUTCOME_LEADS"
    OUTCOME_SALES = "OUTCOME_SALES"
    OUTCOME_AWARENESS = "OUTCOME_AWARENESS"


class MetaEntityStatus(str, Enum):
    PAUSED = "PAUSED"
    ACTIVE = "ACTIVE"


class MetaBillingEvent(str, Enum):
    IMPRESSIONS = "IMPRESSIONS"
    LINK_CLICKS = "LINK_CLICKS"


class MetaOptimizationGoal(str, Enum):
    LINK_CLICKS = "LINK_CLICKS"
    LEAD_GENERATION = "LEAD_GENERATION"
    LANDING_PAGE_VIEWS = "LANDING_PAGE_VIEWS"


class MetaAdsSafetyViolation(ValueError):
    """Raised when an operation violates financial or security safety constraints for Meta Ads."""
    pass


class MetaTargetingDTO(BaseModel):
    countries: List[str] = Field(default_factory=lambda: ["UZ", "KZ"])
    cities: List[str] = Field(default_factory=lambda: ["Tashkent", "Almaty"])
    age_min: int = Field(default=24, ge=18, le=65)
    age_max: int = Field(default=65, ge=18, le=65)
    interests: List[str] = Field(default_factory=lambda: [
        "Artificial intelligence",
        "Banking",
        "Enterprise software",
        "Financial technology",
        "Management"
    ])
    publisher_platforms: List[str] = Field(default_factory=lambda: ["instagram", "facebook"])
    device_platforms: List[str] = Field(default_factory=lambda: ["mobile", "desktop"])


class MetaAdCreativeDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    primary_text: str = Field(..., min_length=10, max_length=1000, description="Ad copy body")
    headline: str = Field(..., min_length=1, max_length=40, description="Headline on link card")
    description: Optional[str] = Field(default=None, max_length=35, description="Link description")
    website_url: str = Field(..., description="Destination landing page")
    call_to_action: str = Field(default="LEARN_MORE", description="CTA button")
    url_tags: Optional[str] = Field(
        default="utm_source=meta&utm_medium=cpc&utm_campaign={_campaign}&utm_content={_adset}&fbclid={fbclid}"
    )

    @field_validator("website_url")
    @classmethod
    def validate_website_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(f"Invalid website URL: '{v}'. Must start with http:// or https://")
        return v

    @field_validator("url_tags")
    @classmethod
    def validate_url_tags(cls, v: Optional[str]) -> Optional[str]:
        if v and "utm_source=meta" not in v:
            raise ValueError("URL tags must contain 'utm_source=meta' for attribution tracking")
        return v


class MetaAdSetDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    daily_budget_cents: int = Field(default=1500, ge=100, le=50_000, description="Daily budget in cents ($15.00 = 1500)")
    billing_event: MetaBillingEvent = Field(default=MetaBillingEvent.IMPRESSIONS)
    optimization_goal: MetaOptimizationGoal = Field(default=MetaOptimizationGoal.LINK_CLICKS)
    targeting: MetaTargetingDTO = Field(default_factory=MetaTargetingDTO)
    creatives: List[MetaAdCreativeDTO] = Field(default_factory=list)
    status: MetaEntityStatus = Field(default=MetaEntityStatus.PAUSED)


class MetaCampaignDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    objective: MetaCampaignObjective = Field(default=MetaCampaignObjective.OUTCOME_LEADS)
    daily_budget_cents: int = Field(default=1500, ge=100, le=50_000, description="Daily budget in cents")
    status: MetaEntityStatus = Field(default=MetaEntityStatus.PAUSED)
    ad_sets: List[MetaAdSetDTO] = Field(default_factory=list)
    allow_live_enabled: bool = Field(default=False, description="Override for live activation")

    @model_validator(mode="after")
    def enforce_zero_trust_status(self) -> "MetaCampaignDTO":
        if self.status == MetaEntityStatus.ACTIVE and not self.allow_live_enabled:
            raise MetaAdsSafetyViolation(
                "Financial Zero-Trust Violation: Meta campaigns cannot be created in ACTIVE status. "
                "Must be created in PAUSED status to prevent accidental budget consumption."
            )
        return self

    @property
    def daily_budget_usd(self) -> float:
        return self.daily_budget_cents / 100.0

    def get_summary(self) -> Dict[str, Any]:
        total_creatives = sum(len(adset.creatives) for adset in self.ad_sets)
        return {
            "name": self.name,
            "status": self.status.value,
            "daily_budget_usd": f"${self.daily_budget_usd:.2f}",
            "objective": self.objective.value,
            "ad_sets_count": len(self.ad_sets),
            "creatives_count": total_creatives,
            "platforms": self.ad_sets[0].targeting.publisher_platforms if self.ad_sets else ["instagram", "facebook"],
        }
