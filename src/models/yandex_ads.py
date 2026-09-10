"""
Yandex Direct API v5 DTO Models and Local UZS Zero-Trust Safeguards.
Enforces Direct API v5 JSON schemas, STANDARD budget limits (no overspend),
and Track 3 UTM attribution integration.
"""
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class YandexCampaignType(str, Enum):
    TEXT_CAMPAIGN = "TEXT_CAMPAIGN"


class YandexCampaignState(str, Enum):
    OFF = "OFF"
    ON = "ON"
    SUSPENDED = "SUSPENDED"


class YandexBudgetMode(str, Enum):
    STANDARD = "STANDARD"  # Strict daily stop without overspend
    DISTRIBUTED = "DISTRIBUTED"


class YandexAdsSafetyViolation(ValueError):
    """Raised when an operation violates financial or security safety constraints for Yandex Direct."""
    pass


class YandexKeywordDTO(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=100)
    bid_uzs: int = Field(default=5_000, ge=500, le=500_000, description="Bid in UZS (e.g. 5,000 UZS)")

    @field_validator("keyword")
    @classmethod
    def clean_keyword(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Keyword cannot be empty")
        return cleaned


class YandexTextAdDTO(BaseModel):
    title: str = Field(..., min_length=1, max_length=56, description="Title 1 (max 56 chars)")
    title2: Optional[str] = Field(default=None, max_length=35, description="Title 2 (max 35 chars)")
    text: str = Field(..., min_length=1, max_length=81, description="Ad copy text (max 81 chars)")
    href: str = Field(..., description="Destination landing page")
    display_url_path: Optional[str] = Field(default=None, max_length=20)
    tracking_params: Optional[str] = Field(
        default="utm_source=yandex&utm_medium=cpc&utm_campaign={campaign_name}&utm_content={adgroup_id}&utm_term={keyword}&yclid={yclid}"
    )

    @field_validator("href")
    @classmethod
    def validate_href(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(f"Invalid URL: '{v}'. Must start with http:// or https://")
        return v

    @field_validator("tracking_params")
    @classmethod
    def validate_tracking(cls, v: Optional[str]) -> Optional[str]:
        if v and "utm_source=yandex" not in v:
            raise ValueError("Tracking parameters must specify 'utm_source=yandex'")
        return v


class YandexAdGroupDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    region_ids: List[int] = Field(default_factory=lambda: [10335, 171])  # 10335: Tashkent, 171: Uzbekistan
    negative_keywords: List[str] = Field(default_factory=list)
    keywords: List[YandexKeywordDTO] = Field(default_factory=list)
    ads: List[YandexTextAdDTO] = Field(default_factory=list)


class YandexCampaignDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    daily_budget_uzs: int = Field(
        default=200_000,
        ge=50_000,
        le=10_000_000,
        description="Daily budget in UZS (e.g. 200,000 UZS ~ $15.60)"
    )
    budget_mode: YandexBudgetMode = Field(default=YandexBudgetMode.STANDARD)
    state: YandexCampaignState = Field(default=YandexCampaignState.OFF)
    ad_groups: List[YandexAdGroupDTO] = Field(default_factory=list)
    negative_keywords: List[str] = Field(default_factory=lambda: ["бесплатно", "скачать", "вакансии", "торрент"])
    allow_live_enabled: bool = Field(default=False, description="Override for live activation")

    @model_validator(mode="after")
    def enforce_zero_trust_state(self) -> "YandexCampaignDTO":
        if self.state == YandexCampaignState.ON and not self.allow_live_enabled:
            raise YandexAdsSafetyViolation(
                "Financial Zero-Trust Violation: Yandex campaign cannot be created in ON state. "
                "Must be created in OFF or SUSPENDED state to prevent accidental budget consumption."
            )
        return self

    def get_summary(self) -> Dict[str, Any]:
        total_keywords = sum(len(ag.keywords) for ag in self.ad_groups)
        total_ads = sum(len(ag.ads) for ag in self.ad_groups)
        return {
            "name": self.name,
            "state": self.state.value,
            "daily_budget_uzs": f"{self.daily_budget_uzs:,} UZS",
            "budget_mode": self.budget_mode.value,
            "ad_groups_count": len(self.ad_groups),
            "keywords_count": total_keywords,
            "ads_count": total_ads,
            "negative_keywords_count": len(self.negative_keywords),
        }
