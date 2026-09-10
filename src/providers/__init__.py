"""
Marketing Platform Providers (Google Ads, Meta, Yandex).
"""
from .google_ads_client import GoogleAdsClient
from .google_ads_service import GoogleAdsService

__all__ = [
    "GoogleAdsClient",
    "GoogleAdsService",
]
