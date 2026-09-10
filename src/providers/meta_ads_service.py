"""
Meta (Instagram / Facebook) Campaign Orchestration Service.
Builds high-performing B2B campaigns for founders, bankers, and executives in Central Asia.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from src.models.meta_ads import (
    MetaCampaignDTO,
    MetaAdSetDTO,
    MetaAdCreativeDTO,
    MetaTargetingDTO,
    MetaCampaignObjective,
    MetaEntityStatus,
    MetaBillingEvent,
    MetaOptimizationGoal,
)
from .meta_ads_client import MetaAdsClient


class MetaAdsService:
    """Service for building and deploying Meta (Instagram/Facebook) campaigns."""

    def __init__(self, client: Optional[MetaAdsClient] = None):
        self.client = client or MetaAdsClient()

    def build_default_swipies_campaign(
        self,
        daily_budget_usd: float = 15.0,
        target_countries: Optional[List[str]] = None,
    ) -> MetaCampaignDTO:
        """
        Build default B2B Instagram/Facebook campaign for SWIPIES Enterprise RAG.
        Targets business founders and tech leaders in Uzbekistan and Kazakhstan.
        """
        daily_budget_cents = int(daily_budget_usd * 100)

        # 1. B2B Creative
        creative = MetaAdCreativeDTO(
            name="SWIPIES_Enterprise_RAG_Instagram_Card",
            headline="SWIPIES: Enterprise RAG & AI",
            primary_text=(
                "Внедрите защищенный ИИ-поиск по корпоративной базе знаний за 1 день. "
                "Локальный контур, нулевой риск утечки данных, соответствие закону о персональных данных РУз. "
                "RAG без галлюцинаций для банков, ритейла и enterprise-компаний."
            ),
            description="Локальный ИИ для бизнеса",
            website_url="https://swipies.io/enterprise",
            call_to_action="LEARN_MORE",
            url_tags="utm_source=meta&utm_medium=cpc&utm_campaign=swipies_b2b_instagram&utm_content=fintech_directors&fbclid={fbclid}"
        )

        # 2. Audience Targeting
        targeting = MetaTargetingDTO(
            countries=target_countries or ["UZ", "KZ"],
            cities=["Tashkent", "Almaty", "Samarkand", "Astana"],
            age_min=24,
            age_max=60,
            interests=[
                "Artificial intelligence",
                "Banking",
                "Enterprise software",
                "Financial technology",
                "Information technology",
            ],
            publisher_platforms=["instagram", "facebook"],
            device_platforms=["mobile", "desktop"]
        )

        # 3. AdSet
        adset = MetaAdSetDTO(
            name="Directors_and_Founders_Central_Asia",
            daily_budget_cents=daily_budget_cents,
            billing_event=MetaBillingEvent.IMPRESSIONS,
            optimization_goal=MetaOptimizationGoal.LINK_CLICKS,
            targeting=targeting,
            creatives=[creative],
            status=MetaEntityStatus.PAUSED
        )

        # 4. Campaign
        return MetaCampaignDTO(
            name="SWIPIES_B2B_Meta_Instagram_LeadGen",
            objective=MetaCampaignObjective.OUTCOME_LEADS,
            daily_budget_cents=daily_budget_cents,
            status=MetaEntityStatus.PAUSED,  # Zero-Trust
            ad_sets=[adset]
        )

    def preview_campaign_summary(self, campaign: MetaCampaignDTO) -> str:
        """Format text preview of campaign structure."""
        summary = campaign.get_summary()
        lines = [
            "================================================================================",
            f"   M E T A  ( I N S T A G R A M )  A D S  P R E V I E W : {campaign.name}",
            "================================================================================",
            f"Status:                  {summary['status']} (Zero-Trust Guard: Always PAUSED)",
            f"Daily Budget:            {summary['daily_budget_usd']} / day",
            f"Campaign Objective:      {summary['objective']}",
            f"AdSets Count:            {summary['ad_sets_count']}",
            f"Creatives Count:         {summary['creatives_count']}",
            f"Publisher Platforms:     {', '.join(summary['platforms'])}",
            "--------------------------------------------------------------------------------",
            "AdSet Details:",
        ]

        for adset in campaign.ad_sets:
            lines.append(f"  * [{adset.name}] Daily Budget: ${adset.daily_budget_cents / 100:.2f}")
            lines.append(f"    Geos: {', '.join(adset.targeting.countries)} ({', '.join(adset.targeting.cities)})")
            lines.append(f"    Interests: {', '.join(adset.targeting.interests)}")
            lines.append("    Creatives:")
            for idx, cr in enumerate(adset.creatives, 1):
                lines.append(f"      Creative #{idx}: {cr.name}")
                lines.append(f"      Headline: {cr.headline}")
                lines.append(f"      URL Tags: {cr.url_tags}")
                lines.append(f"      Copy: {cr.primary_text[:90]}...")

        lines.append("================================================================================")
        return "\n".join(lines)

    def validate_and_deploy(
        self,
        campaign: MetaCampaignDTO,
        dry_run: bool = True,
        approval_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.client.mutate_campaign(
            campaign=campaign,
            dry_run=dry_run,
            approval_token=approval_token,
        )

    def generate_mock_spend_report(
        self,
        campaign_name: str = "swipies_b2b_instagram",
        clicks: int = 300,
        avg_cpc_usd: float = 0.28,
    ) -> Dict[str, Any]:
        total_spend_usd = round(clicks * avg_cpc_usd, 2)
        spend_uzs = int(total_spend_usd * 12_800)
        impressions = clicks * 40
        return {
            "campaign_name": campaign_name,
            "channel": "meta",
            "medium": "cpc",
            "impressions": impressions,
            "clicks": clicks,
            "ctr_percent": round((clicks / impressions) * 100, 2),
            "avg_cpc_usd": avg_cpc_usd,
            "total_spend_usd": total_spend_usd,
            "total_spend_uzs": spend_uzs,
            "currency_reported": "USD",
            "currency_converted": "UZS",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
