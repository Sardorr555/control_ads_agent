"""
Session Matching Engine for SWIPIES Traffic Attribution.
Implements:
- First-Touch Attribution (first recorded marketing touchpoint within 30 days)
- Last-Touch Attribution (most recent marketing touchpoint before payment)
- IP-Hash Lookback Fallback (24-hour window when session_id is absent)
- Direct/Organic Fallback
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Literal
from ..models.attribution import AttributionMatchDTO
from ..storage.sqlite_events_repo import SQLiteEventsRepo

logger = logging.getLogger("swipies.attribution.matcher")


class SessionMatcher:
    def __init__(
        self,
        repo: SQLiteEventsRepo,
        attribution_window_days: int = 30,
        ip_fallback_window_hours: int = 24,
        enable_ip_fallback: bool = False
    ):
        self.repo = repo
        self.attribution_window_days = attribution_window_days
        self.ip_fallback_window_hours = ip_fallback_window_hours
        self.enable_ip_fallback = enable_ip_fallback

    def _parse_datetime(self, val: Any) -> datetime:
        if isinstance(val, datetime):
            if val.tzinfo is None:
                return val.replace(tzinfo=timezone.utc)
            return val
        if isinstance(val, str):
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        return datetime.now(timezone.utc)

    def match_payment(
        self,
        payment: Dict[str, Any],
        model: Literal["first-touch", "last-touch"] = "first-touch"
    ) -> AttributionMatchDTO:
        """
        Matches a single payment transaction from v_attribution_payments with traffic events.
        """
        transaction_id = str(payment.get("transaction_id") or payment.get("payment_id") or "UNKNOWN")
        session_id = payment.get("session_id")
        raw_payment_time = payment.get("payment_time") or datetime.now(timezone.utc)
        payment_time = self._parse_datetime(raw_payment_time)
        amount_uzs = int(payment.get("amount_uzs") or 0)
        currency = str(payment.get("currency") or "UZS")
        plan_type = str(payment.get("plan_type") or "standard")
        masked_payer_hash = payment.get("masked_payer_hash")

        # 1. Direct Session Matching
        matched_event = None
        if session_id:
            if model == "first-touch":
                matched_event = self.repo.get_first_touch_by_session(session_id)
            else:
                matched_event = self.repo.get_last_touch_by_session(session_id, before_time=payment_time)

        if matched_event:
            event_time = self._parse_datetime(matched_event["timestamp"])
            window_cutoff = payment_time - timedelta(days=self.attribution_window_days)
            
            # Verify within 30-day attribution window
            if event_time >= window_cutoff:
                time_to_convert = max(0, int((payment_time - event_time).total_seconds()))
                utm_source = matched_event.get("utm_source") or payment.get("utm_source")
                utm_medium = matched_event.get("utm_medium") or payment.get("utm_medium")
                utm_campaign = matched_event.get("utm_campaign") or payment.get("utm_campaign")
                utm_content = matched_event.get("utm_content") or payment.get("utm_content")
                utm_term = matched_event.get("utm_term") or payment.get("utm_term")

                if utm_source:
                    return AttributionMatchDTO(
                        transaction_id=transaction_id,
                        session_id=session_id,
                        payment_time=payment_time,
                        amount_uzs=amount_uzs,
                        currency=currency,
                        plan_type=plan_type,
                        utm_source=utm_source,
                        utm_medium=utm_medium or "(none)",
                        utm_campaign=utm_campaign or "(direct)",
                        utm_content=utm_content,
                        utm_term=utm_term,
                        match_type="session_direct",
                        time_to_convert_sec=time_to_convert,
                        masked_payer_hash=masked_payer_hash
                    )

        # 1b. Check if payment record itself carries UTMs (persisted during session creation)
        if payment.get("utm_source"):
            return AttributionMatchDTO(
                transaction_id=transaction_id,
                session_id=session_id,
                payment_time=payment_time,
                amount_uzs=amount_uzs,
                currency=currency,
                plan_type=plan_type,
                utm_source=payment.get("utm_source"),
                utm_medium=payment.get("utm_medium") or "(none)",
                utm_campaign=payment.get("utm_campaign") or "(direct)",
                utm_content=payment.get("utm_content"),
                utm_term=payment.get("utm_term"),
                match_type="session_direct",
                time_to_convert_sec=None,
                masked_payer_hash=masked_payer_hash
            )

        # 2. IP Hash Fallback Matching (strictly opt-in, disabled by default to prevent CGNAT collisions)
        if self.enable_ip_fallback:
            ip_hash = payment.get("ip_hash")
            if ip_hash:
                since = payment_time - timedelta(hours=self.ip_fallback_window_hours)
                ip_event = self.repo.get_touch_by_ip_hash(
                    ip_hash=ip_hash,
                    since=since,
                    before_time=payment_time,
                    model=model
                )
                if ip_event and ip_event.get("utm_source"):
                    event_time = self._parse_datetime(ip_event["timestamp"])
                    time_to_convert = max(0, int((payment_time - event_time).total_seconds()))
                    return AttributionMatchDTO(
                        transaction_id=transaction_id,
                        session_id=ip_event.get("session_id") or session_id,
                        payment_time=payment_time,
                        amount_uzs=amount_uzs,
                        currency=currency,
                        plan_type=plan_type,
                        utm_source=ip_event.get("utm_source"),
                        utm_medium=ip_event.get("utm_medium") or "(none)",
                        utm_campaign=ip_event.get("utm_campaign") or "(direct)",
                        utm_content=ip_event.get("utm_content"),
                        utm_term=ip_event.get("utm_term"),
                        match_type="ip_time_window",
                        time_to_convert_sec=time_to_convert,
                        masked_payer_hash=masked_payer_hash
                    )

        # 3. Organic / Direct Unmatched Fallback
        return AttributionMatchDTO(
            transaction_id=transaction_id,
            session_id=session_id,
            payment_time=payment_time,
            amount_uzs=amount_uzs,
            currency=currency,
            plan_type=plan_type,
            utm_source="(direct)",
            utm_medium="(none)",
            utm_campaign="(direct)",
            utm_content=None,
            utm_term=None,
            match_type="organic_unmatched",
            time_to_convert_sec=None,
            masked_payer_hash=masked_payer_hash
        )

    def match_payments_batch(
        self,
        payments: List[Dict[str, Any]],
        model: Literal["first-touch", "last-touch"] = "first-touch"
    ) -> List[AttributionMatchDTO]:
        return [self.match_payment(p, model=model) for p in payments]
