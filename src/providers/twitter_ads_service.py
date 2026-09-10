"""
Twitter / X Ads Campaign Orchestration Service.
Builds high-converting viral B2B tech campaigns for SWIPIES
targeting AI founders, CTOs, and enterprise developers.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from src.models.twitter_ads import (
    TwitterCampaignDTO,
    TwitterLineItemDTO,
    TwitterPromotedTweetDTO,
    TwitterTargetingDTO,
    TwitterCampaignObjective,
    TwitterEntityStatus,
    TwitterBidType,
    TwitterPlacement,
)
from .twitter_ads_client import TwitterAdsClient


class TwitterAdsService:
    """Service for building and deploying Twitter / X Ads campaigns."""

    def __init__(self, client: Optional[TwitterAdsClient] = None):
        self.client = client or TwitterAdsClient()

    def build_default_swipies_campaign(
        self,
        daily_budget_usd: float = 15.0,
        target_locations: Optional[List[str]] = None,
    ) -> TwitterCampaignDTO:
        """
        Build pre-configured Enterprise B2B tech campaign for X/Twitter.
        Targets followers of key AI companies and high-intent RAG/LLM keywords.
        """
        daily_budget_micros = int(daily_budget_usd * 1_000_000)

        # 1. High-Converting Tech Tweet Creative (ASCII-safe for Windows terminals)
        tweet = TwitterPromotedTweetDTO(
            text=(
                "Tired of LLM hallucinations in production?\n\n"
                "SWIPIES delivers air-gapped Enterprise RAG with zero hallucination retrieval, "
                "strict data residency, and deep vector search across 50+ enterprise document formats.\n\n"
                "Connect your internal databases and test local AI today:"
            ),
            card_title="SWIPIES: Enterprise RAG & Local AI",
            website_url="https://swipies.io/enterprise",
            call_to_action="LEARN_MORE",
            tracking_url_template="{website_url}?utm_source=twitter&utm_medium=cpc&utm_campaign=swipies_x_tech_rag&utm_content=follower_ai&twclid={twclid}"
        )

        # 2. Audience Targeting
        targeting = TwitterTargetingDTO(
            keywords=[
                "Enterprise RAG",
                "Local LLM",
                "Knowledge Base AI",
                "LangChain",
                "Vector Database",
                "Data Sovereignty",
            ],
            follower_lookalikes=[
                "@OpenAI",
                "@AnthropicAI",
                "@LangChainAI",
                "@huggingface",
                "@sama",
            ],
            locations=target_locations or ["US", "GB", "UZ", "KZ", "DE", "AE"],
            languages=["en", "ru"]
        )

        # 3. Line Item
        line_item = TwitterLineItemDTO(
            name="AI_Founders_and_Tech_Leads",
            objective=TwitterCampaignObjective.WEBSITE_CLICKS,
            bid_amount_local_micro=350_000,  # $0.35 target CPC
            bid_type=TwitterBidType.AUTO,
            placements=[TwitterPlacement.TWITTER_TIMELINE, TwitterPlacement.TWITTER_SEARCH],
            targeting=targeting,
            tweets=[tweet],
            status=TwitterEntityStatus.PAUSED
        )

        # 4. Campaign
        return TwitterCampaignDTO(
            name="SWIPIES_X_Global_B2B_Tech_RAG",
            daily_budget_amount_local_micro=daily_budget_micros,
            objective=TwitterCampaignObjective.WEBSITE_CLICKS,
            status=TwitterEntityStatus.PAUSED,  # Zero-Trust
            line_items=[line_item]
        )

    def preview_campaign_summary(self, campaign: TwitterCampaignDTO) -> str:
        """Format text preview of campaign structure."""
        summary = campaign.get_summary()
        lines = [
            "================================================================================",
            f"   T W I T T E R  /  X  A D S  C A M P A I G N  P R E V I E W : {campaign.name}",
            "================================================================================",
            f"Status:                  {summary['status']} (Zero-Trust Guard: Always PAUSED)",
            f"Daily Budget:            {summary['daily_budget_usd']} / day",
            f"Campaign Objective:      {summary['objective']}",
            f"Line Items Count:        {summary['line_items_count']}",
            f"Target Keywords:         {summary['target_keywords_count']}",
            f"Follower Lookalikes:     {summary['follower_lookalikes_count']}",
            f"Promoted Tweets:         {summary['promoted_tweets_count']}",
            "--------------------------------------------------------------------------------",
            "Line Item Details:",
        ]

        for li in campaign.line_items:
            lines.append(f"  * [{li.name}] Target Bid: ${li.bid_amount_local_micro / 1_000_000:.2f}")
            lines.append(f"    Placements: {', '.join(p.value for p in li.placements)}")
            lines.append("    Follower Lookalikes:")
            for handle in li.targeting.follower_lookalikes:
                lines.append(f"      - {handle}")
            lines.append("    Target Keywords:")
            for kw in li.targeting.keywords:
                lines.append(f"      - #{kw}")
            lines.append("    Promoted Tweets:")
            for idx, tw in enumerate(li.tweets, 1):
                lines.append(f"      Tweet #{idx} URL: {tw.website_url}")
                lines.append(f"      CTA: {tw.call_to_action} | Card Title: {tw.card_title}")
                lines.append("      Copy:")
                for text_line in tw.text.split("\n"):
                    lines.append(f"        {text_line}")

        lines.append("================================================================================")
        return "\n".join(lines)

    def validate_and_deploy(
        self,
        campaign: TwitterCampaignDTO,
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
        campaign_name: str = "swipies_x_tech_rag",
        clicks: int = 200,
        avg_cpc_usd: float = 0.35,
    ) -> Dict[str, Any]:
        """
        Generate campaign spend data from X Ads for ingestion into Attribution Engine.
        """
        total_spend_usd = round(clicks * avg_cpc_usd, 2)
        # Approximate exchange rate 1 USD = 12,800 UZS
        spend_uzs = int(total_spend_usd * 12_800)
        impressions = clicks * 28  # Typical CTR ~3.5%
        return {
            "campaign_name": campaign_name,
            "channel": "twitter",
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
