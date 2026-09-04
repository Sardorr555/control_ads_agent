"""
Pydantic DTOs for Attribution Matching, Conversions, and Campaign Metrics.
"""
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


class AttributionMatchDTO(BaseModel):
    transaction_id: str = Field(..., max_length=128)
    session_id: Optional[str] = Field(None, max_length=64)
    payment_time: datetime
    amount_uzs: int = Field(..., ge=0)
    currency: str = Field(default="UZS", max_length=3)
    plan_type: str = Field(..., max_length=32)
    
    # Marketing source
    utm_source: Optional[str] = Field(None, max_length=64)
    utm_medium: Optional[str] = Field(None, max_length=64)
    utm_campaign: Optional[str] = Field(None, max_length=128)
    utm_content: Optional[str] = Field(None, max_length=128)
    utm_term: Optional[str] = Field(None, max_length=128)
    
    # Matching algorithm metadata
    match_type: Literal["session_direct", "ip_time_window", "organic_unmatched"] = "session_direct"
    time_to_convert_sec: Optional[int] = Field(None, ge=0)
    masked_payer_hash: Optional[str] = Field(None, max_length=64)


class CampaignAttributionMetric(BaseModel):
    campaign_name: str
    source: str
    medium: str
    total_visits: int = Field(default=0, ge=0)
    unique_sessions: int = Field(default=0, ge=0)
    total_conversions: int = Field(default=0, ge=0)
    total_revenue_uzs: int = Field(default=0, ge=0)
    cr_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    avg_order_value_uzs: float = Field(default=0.0, ge=0.0)
    roas: Optional[float] = Field(None, ge=0.0)
