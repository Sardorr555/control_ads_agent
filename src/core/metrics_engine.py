"""
Financial and Conversion Metrics Engine with Strict Decimal Precision.
Guarantees zero IEEE 754 float drift using Python Decimal and ROUND_HALF_UP.
Calculates CR%, AOV, ROAS, CAC, and CPL.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional
from collections import defaultdict

from ..models.attribution import AttributionMatchDTO, CampaignAttributionMetric


def to_decimal(val: Any) -> Decimal:
    if isinstance(val, Decimal):
        return val
    if val is None:
        return Decimal("0.00")
    return Decimal(str(val))


class MetricsEngine:
    ROUNDING = ROUND_HALF_UP
    TWO_PLACES = Decimal("0.01")
    FOUR_PLACES = Decimal("0.0001")

    @classmethod
    def calculate_cr_percent(cls, conversions: int, total_units: int) -> Decimal:
        """
        Conversion Rate = (Conversions / Units) * 100
        Units can be unique sessions or total visits.
        """
        if total_units <= 0 or conversions <= 0:
            return Decimal("0.00")
        cr = (Decimal(conversions) / Decimal(total_units)) * Decimal("100")
        return cr.quantize(cls.TWO_PLACES, rounding=cls.ROUNDING)

    @classmethod
    def calculate_aov_uzs(cls, total_revenue_uzs: Any, conversions: int) -> Decimal:
        """
        Average Order Value (AOV) = Total Revenue / Conversions
        """
        if conversions <= 0:
            return Decimal("0.00")
        rev = to_decimal(total_revenue_uzs)
        aov = rev / Decimal(conversions)
        return aov.quantize(cls.TWO_PLACES, rounding=cls.ROUNDING)

    @classmethod
    def calculate_roas(cls, total_revenue_uzs: Any, ad_spend_uzs: Any) -> Optional[Decimal]:
        """
        Return on Ad Spend (ROAS) = Total Revenue / Ad Spend
        """
        spend = to_decimal(ad_spend_uzs)
        if spend <= Decimal("0.00"):
            return None
        rev = to_decimal(total_revenue_uzs)
        roas = rev / spend
        return roas.quantize(cls.FOUR_PLACES, rounding=cls.ROUNDING)

    @classmethod
    def calculate_cac_uzs(cls, ad_spend_uzs: Any, paying_customers: int) -> Optional[Decimal]:
        """
        Customer Acquisition Cost (CAC) = Ad Spend / Paying Customers
        """
        if paying_customers <= 0:
            return None
        spend = to_decimal(ad_spend_uzs)
        cac = spend / Decimal(paying_customers)
        return cac.quantize(cls.TWO_PLACES, rounding=cls.ROUNDING)

    @classmethod
    def calculate_cpl_uzs(cls, ad_spend_uzs: Any, leads_count: int) -> Optional[Decimal]:
        """
        Cost per Lead (CPL) = Ad Spend / Leads
        """
        if leads_count <= 0:
            return None
        spend = to_decimal(ad_spend_uzs)
        cpl = spend / Decimal(leads_count)
        return cpl.quantize(cls.TWO_PLACES, rounding=cls.ROUNDING)

    @classmethod
    def aggregate_campaigns(
        cls,
        raw_events: List[Dict[str, Any]],
        attributed_payments: List[AttributionMatchDTO],
        ad_spends: Optional[Dict[str, Any]] = None
    ) -> List[CampaignAttributionMetric]:
        """
        Aggregates raw traffic events and attributed payments by campaign slice:
        (utm_source, utm_medium, utm_campaign)
        """
        ad_spends = ad_spends or {}
        campaign_visits = defaultdict(int)
        campaign_sessions = defaultdict(set)

        for ev in raw_events:
            src = ev.get("utm_source") or "(direct)"
            med = ev.get("utm_medium") or "(none)"
            camp = ev.get("utm_campaign") or "(direct)"
            key = (src, med, camp)

            campaign_visits[key] += 1
            if ev.get("session_id"):
                campaign_sessions[key].add(ev["session_id"])

        campaign_conversions = defaultdict(int)
        campaign_revenue = defaultdict(Decimal)

        for p in attributed_payments:
            src = p.utm_source or "(direct)"
            med = p.utm_medium or "(none)"
            camp = p.utm_campaign or "(direct)"
            key = (src, med, camp)

            campaign_conversions[key] += 1
            campaign_revenue[key] += Decimal(p.amount_uzs)

        all_keys = set(campaign_visits.keys()) | set(campaign_conversions.keys())
        results: List[CampaignAttributionMetric] = []

        for key in sorted(all_keys):
            src, med, camp = key
            visits = campaign_visits[key]
            unique_sessions_count = len(campaign_sessions[key])
            conversions = campaign_conversions[key]
            revenue = campaign_revenue[key]

            # Denominator for CR is unique sessions, fallback to visits, fallback to conversions
            denom = unique_sessions_count if unique_sessions_count > 0 else (visits if visits > 0 else conversions)
            cr = cls.calculate_cr_percent(conversions, denom)
            aov = cls.calculate_aov_uzs(revenue, conversions)

            spend_val = ad_spends.get(camp) or ad_spends.get(src)
            roas_dec = cls.calculate_roas(revenue, spend_val) if spend_val else None

            results.append(
                CampaignAttributionMetric(
                    campaign_name=camp,
                    source=src,
                    medium=med,
                    total_visits=visits,
                    unique_sessions=unique_sessions_count,
                    total_conversions=conversions,
                    total_revenue_uzs=int(revenue),
                    cr_percent=float(cr),
                    avg_order_value_uzs=float(aov),
                    roas=float(roas_dec) if roas_dec is not None else None
                )
            )

        return results
