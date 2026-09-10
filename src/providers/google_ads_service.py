"""
Google Ads Campaign Orchestration Service.
Builds high-converting B2B campaign structures for SWIPIES (Enterprise RAG & AI)
with strict financial controls and automated UTM tracking integration.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from src.models.google_ads import (
    GoogleCampaignDTO,
    GoogleAdGroupDTO,
    GoogleKeywordDTO,
    GoogleResponsiveSearchAdDTO,
    GoogleAdHeadlineDTO,
    GoogleAdDescriptionDTO,
    KeywordMatchType,
    CampaignStatus,
    BiddingStrategy,
)
from .google_ads_client import GoogleAdsClient


class GoogleAdsService:
    """Service for building, auditing, and executing Google Ads campaigns."""

    def __init__(self, client: Optional[GoogleAdsClient] = None):
        self.client = client or GoogleAdsClient()

    def build_default_swipies_campaign(
        self,
        daily_budget_usd: float = 10.0,
        target_locations: Optional[List[str]] = None,
    ) -> GoogleCampaignDTO:
        """
        Build pre-configured Enterprise B2B Search Campaign for SWIPIES.
        Ready for dry-run validation and submission in PAUSED mode.
        """
        daily_budget_micros = int(daily_budget_usd * 1_000_000)

        # 1. Headlines (strictly <= 30 chars, no exclamation mark at end, no ALL CAPS)
        headlines = [
            GoogleAdHeadlineDTO(text="SWIPIES: Enterprise RAG AI", pinned_position=1),
            GoogleAdHeadlineDTO(text="ИИ-поиск по базам знаний", pinned_position=2),
            GoogleAdHeadlineDTO(text="RAG без галлюцинаций в UZ", pinned_position=3),
            GoogleAdHeadlineDTO(text="Локальный AI для банков"),
            GoogleAdHeadlineDTO(text="Поиск по регламентам и базам"),
            GoogleAdHeadlineDTO(text="Внедрение LLM в Enterprise"),
            GoogleAdHeadlineDTO(text="Безопасный корпоративный ИИ"),
            GoogleAdHeadlineDTO(text="Демо-доступ к платформе RAG"),
        ]

        # 2. Descriptions (strictly <= 90 chars, no repeated punctuation)
        descriptions = [
            GoogleAdDescriptionDTO(
                text="Защищенный ИИ-поиск по корпоративным документам и регламентам. Попробуйте демо.",
                pinned_position=1
            ),
            GoogleAdDescriptionDTO(
                text="Изолированный контур на серверах компании. Соответствие закону о персональных данных.",
                pinned_position=2
            ),
            GoogleAdDescriptionDTO(
                text="Сократите время поиска документов сотрудниками на 80%. Подключение за 1 день."
            ),
        ]

        # 3. Responsive Search Ad
        rsa_ad = GoogleResponsiveSearchAdDTO(
            headlines=headlines,
            descriptions=descriptions,
            final_urls=["https://swipies.io/enterprise"],
            path1="enterprise",
            path2="rag-ai",
            tracking_url_template="{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign=swipies_b2b_search&utm_content=enterprise_rag&utm_term={keyword}&gclid={gclid}"
        )

        # 4. Target Keywords (Positive & Negative)
        keywords: List[GoogleKeywordDTO] = [
            # High-intent exact keywords
            GoogleKeywordDTO(text="enterprise rag", match_type=KeywordMatchType.EXACT, cpc_bid_micros=600_000),
            GoogleKeywordDTO(text="ии для банков", match_type=KeywordMatchType.EXACT, cpc_bid_micros=700_000),
            GoogleKeywordDTO(text="rag система для документов", match_type=KeywordMatchType.EXACT, cpc_bid_micros=500_000),
            GoogleKeywordDTO(text="корпоративный ии поиск", match_type=KeywordMatchType.EXACT, cpc_bid_micros=500_000),
            # Phrase match keywords
            GoogleKeywordDTO(text="внедрение llm", match_type=KeywordMatchType.PHRASE, cpc_bid_micros=450_000),
            GoogleKeywordDTO(text="умный поиск по документам", match_type=KeywordMatchType.PHRASE, cpc_bid_micros=450_000),
            GoogleKeywordDTO(text="ai чатбот для базы знаний", match_type=KeywordMatchType.PHRASE, cpc_bid_micros=400_000),
            # Negative keywords (filter out unwanted consumer/free traffic)
            GoogleKeywordDTO(text="бесплатно", match_type=KeywordMatchType.PHRASE, is_negative=True),
            GoogleKeywordDTO(text="скачать торрент", match_type=KeywordMatchType.PHRASE, is_negative=True),
            GoogleKeywordDTO(text="слив курсов", match_type=KeywordMatchType.PHRASE, is_negative=True),
            GoogleKeywordDTO(text="вакансии", match_type=KeywordMatchType.PHRASE, is_negative=True),
            GoogleKeywordDTO(text="дипломная работа", match_type=KeywordMatchType.PHRASE, is_negative=True),
            GoogleKeywordDTO(text="реферат", match_type=KeywordMatchType.PHRASE, is_negative=True),
            GoogleKeywordDTO(text="игры с ии", match_type=KeywordMatchType.PHRASE, is_negative=True),
        ]

        # 5. Ad Group
        ad_group = GoogleAdGroupDTO(
            name="Enterprise_RAG_Search_Core",
            cpc_bid_micros=500_000,  # $0.50 default bid
            keywords=keywords,
            ads=[rsa_ad]
        )

        # 6. Campaign
        return GoogleCampaignDTO(
            name="SWIPIES_B2B_AI_RAG_UZ_CIS",
            daily_budget_micros=daily_budget_micros,
            status=CampaignStatus.PAUSED,  # Zero-trust safety
            bidding_strategy=BiddingStrategy.MANUAL_CPC,
            target_locations=target_locations or ["Uzbekistan", "Kazakhstan"],
            target_languages=["ru", "en"],
            ad_groups=[ad_group],
            tracking_url_template="{lpurl}?utm_source=google&utm_medium=cpc&utm_campaign=swipies_b2b_search&utm_content={_adgroup}&utm_term={keyword}&gclid={gclid}",
            url_custom_parameters={"_campaign": "swipies_b2b_search"}
        )

    def preview_campaign_summary(self, campaign: GoogleCampaignDTO) -> str:
        """Format text preview of campaign structure."""
        summary = campaign.get_summary()
        lines = [
            "================================================================================",
            f"   G O O G L E  A D S  C A M P A I G N  P R E V I E W : {campaign.name}",
            "================================================================================",
            f"Status:                  {summary['status']} (Strict Zero-Trust Rule: Always PAUSED)",
            f"Daily Budget:            {summary['daily_budget_usd']} / day",
            f"200% Pacing Risk Cap:    {summary['pacing_200pct_max_risk_usd']} (Max possible spend in 1 day)",
            f"Bidding Strategy:        {summary['bidding_strategy']}",
            f"Target Locations:        {', '.join(summary['locations'])}",
            f"Ad Groups:               {summary['ad_groups_count']}",
            f"Positive Keywords:       {summary['positive_keywords_count']}",
            f"Negative Keywords:       {summary['negative_keywords_count']}",
            f"Responsive Search Ads:   {summary['ads_count']}",
            "--------------------------------------------------------------------------------",
            "Ad Group Details:",
        ]

        for ag in campaign.ad_groups:
            lines.append(f"  * [{ag.name}] Default CPC: ${ag.cpc_bid_micros / 1_000_000:.2f}")
            lines.append("    Positive Keywords:")
            for kw in ag.positive_keywords:
                lines.append(f"      - {kw.formatted_keyword()} (${(kw.cpc_bid_micros or ag.cpc_bid_micros) / 1_000_000:.2f})")
            lines.append("    Negative Keywords:")
            for kw in ag.negative_keywords:
                lines.append(f"      - [NEGATIVE] {kw.formatted_keyword()}")
            lines.append("    Responsive Search Ads:")
            for ad_idx, ad in enumerate(ag.ads, 1):
                lines.append(f"      RSA #{ad_idx} Final URL: {ad.final_urls[0]}")
                lines.append(f"      Tracking Template: {ad.tracking_url_template}")
                lines.append(f"      Headlines ({len(ad.headlines)}):")
                for h in ad.headlines[:4]:
                    lines.append(f"        * {h.text}")
                lines.append(f"      Descriptions ({len(ad.descriptions)}):")
                for d in ad.descriptions:
                    lines.append(f"        * {d.text}")

        lines.append("================================================================================")
        return "\n".join(lines)

    def validate_and_deploy(
        self,
        campaign: GoogleCampaignDTO,
        dry_run: bool = True,
        approval_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute validation and deployment through client."""
        return self.client.mutate_campaign(
            campaign=campaign,
            dry_run=dry_run,
            approval_token=approval_token,
        )

    def generate_mock_spend_report(
        self,
        campaign_name: str = "swipies_b2b_search",
        clicks: int = 150,
        avg_cpc_usd: float = 0.42,
    ) -> Dict[str, Any]:
        """
        Generate campaign spend data formatted for ingestion into Attribution Engine.
        Allows calculating ROAS, CAC, and CPL before connecting live billing.
        """
        total_spend_usd = round(clicks * avg_cpc_usd, 2)
        # Approximate exchange rate 1 USD = 12,800 UZS
        spend_uzs = int(total_spend_usd * 12_800)
        return {
            "campaign_name": campaign_name,
            "channel": "google",
            "medium": "cpc",
            "impressions": clicks * 14,
            "clicks": clicks,
            "ctr_percent": round((clicks / (clicks * 14)) * 100, 2),
            "avg_cpc_usd": avg_cpc_usd,
            "total_spend_usd": total_spend_usd,
            "total_spend_uzs": spend_uzs,
            "currency_reported": "USD",
            "currency_converted": "UZS",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
