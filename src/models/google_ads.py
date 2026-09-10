"""
Google Ads DTO Models and Financial Zero-Trust Validation Rules.
Enforces Google Ads Policy constraints, RSA ad limits, budget protections,
and automated UTM tracking template generation for Track 3 integration.
"""
from enum import Enum
import re
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class KeywordMatchType(str, Enum):
    EXACT = "EXACT"
    PHRASE = "PHRASE"
    BROAD = "BROAD"


class CampaignStatus(str, Enum):
    PAUSED = "PAUSED"
    ENABLED = "ENABLED"
    REMOVED = "REMOVED"


class BiddingStrategy(str, Enum):
    MANUAL_CPC = "MANUAL_CPC"
    MAXIMIZE_CLICKS = "MAXIMIZE_CLICKS"
    TARGET_CPA = "TARGET_CPA"


class GoogleAdsSafetyViolation(ValueError):
    """Raised when an operation violates financial or policy safety constraints."""
    pass


class GoogleKeywordDTO(BaseModel):
    text: str = Field(..., min_length=1, max_length=80, description="Keyword phrase")
    match_type: KeywordMatchType = Field(default=KeywordMatchType.EXACT)
    is_negative: bool = Field(default=False, description="Whether this is a negative keyword")
    cpc_bid_micros: Optional[int] = Field(default=None, ge=10_000, le=100_000_000)

    @field_validator("text")
    @classmethod
    def clean_text(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Keyword text cannot be empty or whitespace only")
        # Strip extraneous brackets/quotes if provided by user
        if cleaned.startswith("[") and cleaned.endswith("]"):
            cleaned = cleaned[1:-1].strip()
        elif cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1].strip()
        return cleaned

    def formatted_keyword(self) -> str:
        """Format keyword according to its match type."""
        if self.match_type == KeywordMatchType.EXACT:
            return f"[{self.text}]"
        elif self.match_type == KeywordMatchType.PHRASE:
            return f'"{self.text}"'
        return self.text


class GoogleAdHeadlineDTO(BaseModel):
    text: str = Field(..., min_length=1, max_length=30, description="Headline text (max 30 chars)")
    pinned_position: Optional[int] = Field(default=None, ge=1, le=3)

    @field_validator("text")
    @classmethod
    def validate_headline_policy(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Headline cannot be empty")
        if len(cleaned) > 30:
            raise ValueError(f"Headline exceeds 30 characters limit: '{cleaned}' ({len(cleaned)} chars)")
        # Google Ads Policy: Headlines cannot end with exclamation mark '!'
        if cleaned.endswith("!"):
            raise ValueError(f"Google Ads Policy violation: Headline cannot end with exclamation mark: '{cleaned}'")
        # Capitalization check: cannot be ALL CAPS if word length > 4 (unless known acronyms/brands)
        ALLOWED_ACRONYMS = {"SWIPIES", "RAG", "AI", "LLM", "API", "B2B", "UZ", "CIS", "SAAS", "IT"}
        words = cleaned.split()
        for w in words:
            clean_word = re.sub(r"[^\w]", "", w)
            if len(clean_word) > 4 and clean_word.isupper() and clean_word not in ALLOWED_ACRONYMS:
                raise ValueError(f"Google Ads Policy violation: Excessive capitalization in '{w}'")
        return cleaned


class GoogleAdDescriptionDTO(BaseModel):
    text: str = Field(..., min_length=1, max_length=90, description="Description text (max 90 chars)")
    pinned_position: Optional[int] = Field(default=None, ge=1, le=2)

    @field_validator("text")
    @classmethod
    def validate_description_policy(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Description cannot be empty")
        if len(cleaned) > 90:
            raise ValueError(f"Description exceeds 90 characters limit: '{cleaned}' ({len(cleaned)} chars)")
        # Google Ads Policy: Max 1 exclamation mark in description, cannot have repeated punctuation '!!'
        if "!!" in cleaned or "??" in cleaned:
            raise ValueError("Google Ads Policy violation: Repeated punctuation is forbidden")
        return cleaned


class GoogleResponsiveSearchAdDTO(BaseModel):
    headlines: List[GoogleAdHeadlineDTO] = Field(..., min_length=3, max_length=15)
    descriptions: List[GoogleAdDescriptionDTO] = Field(..., min_length=2, max_length=4)
    final_urls: List[str] = Field(..., min_length=1)
    path1: Optional[str] = Field(default=None, max_length=15)
    path2: Optional[str] = Field(default=None, max_length=15)
    tracking_url_template: Optional[str] = Field(
        default="{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign={_campaign}&utm_content={_adgroup}&utm_term={keyword}&gclid={gclid}"
    )

    @field_validator("final_urls")
    @classmethod
    def validate_final_urls(cls, urls: List[str]) -> List[str]:
        for u in urls:
            if not (u.startswith("http://") or u.startswith("https://")):
                raise ValueError(f"Invalid URL format: '{u}'. Must start with http:// or https://")
        return urls

    @field_validator("tracking_url_template")
    @classmethod
    def validate_tracking_template(cls, template: Optional[str]) -> Optional[str]:
        if template:
            if "{lpurl}" not in template:
                raise ValueError("Tracking URL template must contain '{lpurl}' parameter placeholder")
            if "utm_source" not in template:
                raise ValueError("Tracking URL template must contain 'utm_source' for attribution")
        return template


class GoogleAdGroupDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    cpc_bid_micros: int = Field(default=500_000, ge=10_000, le=100_000_000, description="Bid in micros ($0.50 = 500,000)")
    keywords: List[GoogleKeywordDTO] = Field(default_factory=list)
    ads: List[GoogleResponsiveSearchAdDTO] = Field(default_factory=list)

    @property
    def positive_keywords(self) -> List[GoogleKeywordDTO]:
        return [k for k in self.keywords if not k.is_negative]

    @property
    def negative_keywords(self) -> List[GoogleKeywordDTO]:
        return [k for k in self.keywords if k.is_negative]


class GoogleCampaignDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    daily_budget_micros: int = Field(
        default=10_000_000,
        ge=1_000_000,
        le=500_000_000,
        description="Daily budget in micros (1,000,000 micros = $1.00; max $500.00)"
    )
    status: CampaignStatus = Field(default=CampaignStatus.PAUSED)
    bidding_strategy: BiddingStrategy = Field(default=BiddingStrategy.MANUAL_CPC)
    target_locations: List[str] = Field(default_factory=lambda: ["Uzbekistan", "Kazakhstan"])
    target_languages: List[str] = Field(default_factory=lambda: ["ru", "en"])
    ad_groups: List[GoogleAdGroupDTO] = Field(default_factory=list)
    tracking_url_template: Optional[str] = Field(
        default="{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign={_campaign}&utm_content={_adgroup}&utm_term={keyword}&gclid={gclid}"
    )
    url_custom_parameters: Dict[str, str] = Field(default_factory=dict)
    allow_live_enabled: bool = Field(default=False, description="Override for live activation")

    @model_validator(mode="after")
    def enforce_zero_trust_status(self) -> "GoogleCampaignDTO":
        # Hard Zero-Trust Security Rule: A campaign must NEVER be instantiated with ENABLED status
        # unless explicitly authorized via allow_live_enabled=True.
        if self.status == CampaignStatus.ENABLED and not self.allow_live_enabled:
            raise GoogleAdsSafetyViolation(
                "Financial Zero-Trust Violation: Google campaigns cannot be created in ENABLED status. "
                "Must be created in PAUSED status to prevent accidental budget consumption."
            )
        return self

    @property
    def daily_budget_usd(self) -> float:
        """Daily budget in USD."""
        return self.daily_budget_micros / 1_000_000.0

    @property
    def max_daily_spend_risk_usd(self) -> float:
        """
        Maximum possible daily spend under Google Ads 200% Pacing Rule.
        Google Ads may spend up to 2x daily budget in high traffic periods.
        """
        return (self.daily_budget_micros * 2) / 1_000_000.0

    def get_summary(self) -> Dict[str, Any]:
        total_keywords = sum(len(ag.positive_keywords) for ag in self.ad_groups)
        total_negatives = sum(len(ag.negative_keywords) for ag in self.ad_groups)
        total_ads = sum(len(ag.ads) for ag in self.ad_groups)
        return {
            "name": self.name,
            "status": self.status.value,
            "daily_budget_usd": f"${self.daily_budget_usd:.2f}",
            "pacing_200pct_max_risk_usd": f"${self.max_daily_spend_risk_usd:.2f}",
            "bidding_strategy": self.bidding_strategy.value,
            "locations": self.target_locations,
            "ad_groups_count": len(self.ad_groups),
            "positive_keywords_count": total_keywords,
            "negative_keywords_count": total_negatives,
            "ads_count": total_ads,
        }
