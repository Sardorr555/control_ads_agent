"""
Yandex Direct Campaign Orchestration Service.
Builds high-performing ??? & Search campaigns with local UZS accounting for Uzbekistan & CIS.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from src.models.yandex_ads import (
    YandexCampaignDTO,
    YandexAdGroupDTO,
    YandexKeywordDTO,
    YandexTextAdDTO,
    YandexCampaignState,
    YandexBudgetMode,
)
from .yandex_ads_client import YandexAdsClient


class YandexAdsService:
    """Service for building and deploying Yandex Direct campaigns."""

    def __init__(self, client: Optional[YandexAdsClient] = None):
        self.client = client or YandexAdsClient()

    def build_default_swipies_campaign(
        self,
        daily_budget_uzs: int = 200_000,
        region_ids: Optional[List[int]] = None,
    ) -> YandexCampaignDTO:
        """
        Build default B2B ??? & Search campaign for SWIPIES Enterprise RAG in UZS.
        Targets business decision makers across news and financial portals in Uzbekistan.
        """
        # 1. High-Converting Text Ad (Title <= 56, Title2 <= 35, Text <= 81 chars)
        ad = YandexTextAdDTO(
            title="SWIPIES ? ????????????? ??",
            title2="RAG-????? ??? ????????????",
            text="??-????? ?? ??????????? ? ?????????? ???????? ?? 1 ????. ???? ??? ??????.",
            href="https://swipies.io/enterprise",
            display_url_path="enterprise",
            tracking_params="utm_source=yandex&utm_medium=cpc&utm_campaign=swipies_b2b_yandex_uz&utm_content={adgroup_id}&utm_term={keyword}&yclid={yclid}"
        )

        # 2. Keywords
        keywords = [
            YandexKeywordDTO(keyword="?? ??? ??????", bid_uzs=6_000),
            YandexKeywordDTO(keyword="rag ??? ??????????", bid_uzs=7_000),
            YandexKeywordDTO(keyword="????????????? ???? ?????? ??", bid_uzs=5_000),
            YandexKeywordDTO(keyword="????? ????? ?? ???????????", bid_uzs=5_500),
            YandexKeywordDTO(keyword="????????? ai ??? ???????", bid_uzs=6_500),
        ]

        # 3. Ad Group
        ad_group = YandexAdGroupDTO(
            name="Enterprise_AI_Search_UZ",
            region_ids=region_ids or [10335, 171],  # Tashkent & Uzbekistan
            negative_keywords=["?????????", "???????", "????????", "??????", "???????"],
            keywords=keywords,
            ads=[ad]
        )

        # 4. Campaign
        return YandexCampaignDTO(
            name="SWIPIES_B2B_Yandex_UZ_RSYA",
            daily_budget_uzs=daily_budget_uzs,
            budget_mode=YandexBudgetMode.STANDARD,  # Zero overspend
            state=YandexCampaignState.OFF,  # Zero-Trust
            ad_groups=[ad_group],
            negative_keywords=["?????????", "???????", "????????", "?????", "????"]
        )

    def preview_campaign_summary(self, campaign: YandexCampaignDTO) -> str:
        summary = campaign.get_summary()
        lines = [
            "================================================================================",
            f"   Y A N D E X  D I R E C T  C A M P A I G N  P R E V I E W : {campaign.name}",
            "================================================================================",
            f"State:                   {summary['state']} (Zero-Trust Guard: Always OFF)",
            f"Daily Budget:            {summary['daily_budget_uzs']} (STANDARD mode: Zero overspend)",
            f"Ad Groups Count:         {summary['ad_groups_count']}",
            f"Keywords Count:          {summary['keywords_count']}",
            f"Ads Count:               {summary['ads_count']}",
            f"Negative Keywords:       {summary['negative_keywords_count']}",
            "--------------------------------------------------------------------------------",
            "Ad Group Details:",
        ]

        for ag in campaign.ad_groups:
            lines.append(f"  * [{ag.name}] Regions: {ag.region_ids}")
            lines.append("    Keywords:")
            for kw in ag.keywords:
                lines.append(f"      - {kw.keyword} ({kw.bid_uzs:,} UZS)")
            lines.append("    Ads:")
            for idx, ad in enumerate(ag.ads, 1):
                lines.append(f"      Ad #{idx}: {ad.title} | {ad.title2}")
                lines.append(f"      Href: {ad.href}")
                lines.append(f"      Copy: {ad.text}")

        lines.append("================================================================================")
        return "\n".join(lines)

    def validate_and_deploy(
        self,
        campaign: YandexCampaignDTO,
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
        campaign_name: str = "swipies_b2b_yandex_uz",
        clicks: int = 180,
        avg_cpc_uzs: int = 5_500,
    ) -> Dict[str, Any]:
        total_spend_uzs = clicks * avg_cpc_uzs
        total_spend_usd = round(total_spend_uzs / 12_800, 2)
        impressions = clicks * 22
        return {
            "campaign_name": campaign_name,
            "channel": "yandex",
            "medium": "cpc",
            "impressions": impressions,
            "clicks": clicks,
            "ctr_percent": round((clicks / impressions) * 100, 2),
            "avg_cpc_uzs": avg_cpc_uzs,
            "total_spend_uzs": total_spend_uzs,
            "total_spend_usd": total_spend_usd,
            "currency_reported": "UZS",
            "currency_converted": "USD",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
