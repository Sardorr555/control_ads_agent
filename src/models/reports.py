"""
Pydantic DTOs for Aggregated Attribution Reports and CLI Output.
"""
from datetime import date
from typing import List, Optional
from pydantic import BaseModel, Field
from .attribution import CampaignAttributionMetric


class UtmPerformanceSummary(BaseModel):
    utm_key: str
    visits: int = Field(default=0, ge=0)
    conversions: int = Field(default=0, ge=0)
    revenue_uzs: int = Field(default=0, ge=0)
    avg_time_on_site_sec: float = Field(default=0.0, ge=0.0)


class DailyAttributionReportDTO(BaseModel):
    report_date: date
    total_visits: int = Field(default=0, ge=0)
    total_conversions: int = Field(default=0, ge=0)
    total_revenue_uzs: int = Field(default=0, ge=0)
    overall_cr_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    campaigns: List[CampaignAttributionMetric] = Field(default_factory=list)
    top_sources: List[UtmPerformanceSummary] = Field(default_factory=list)
