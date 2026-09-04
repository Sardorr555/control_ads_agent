"""
Pydantic DTOs for Raw Traffic Ingestion and Validation.
Enforces strict length, pattern constraints, and GDPR/privacy rules.
"""
from datetime import datetime, timezone
import re
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


class UserAgentInfo(BaseModel):
    browser: Optional[str] = Field(None, max_length=64)
    os: Optional[str] = Field(None, max_length=64)
    device_type: Optional[str] = Field(None, max_length=32)  # mobile, desktop, tablet


class RawTrafficEventDTO(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=64)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    page_path: str = Field(..., min_length=1, max_length=255)
    time_on_page_sec: int = Field(default=0, ge=0, le=86400)
    
    # Marketing UTM parameters
    utm_source: Optional[str] = Field(None, max_length=64)
    utm_medium: Optional[str] = Field(None, max_length=64)
    utm_campaign: Optional[str] = Field(None, max_length=128)
    utm_content: Optional[str] = Field(None, max_length=128)
    utm_term: Optional[str] = Field(None, max_length=128)
    
    # Referrer & context
    referrer: Optional[str] = Field(None, max_length=512)
    
    # Privacy-preserving fields (RAW IP MUST NEVER BE STORED)
    ip_hash: str = Field(..., min_length=64, max_length=64)
    country: Optional[str] = Field(None, max_length=2)  # ISO alpha-2
    city: Optional[str] = Field(None, max_length=64)
    user_agent: Optional[str] = Field(None, max_length=255)
    
    event_type: Literal["pageview", "heartbeat", "leave", "conversion"] = "pageview"

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        if not re.match(r'^[a-zA-Z0-9_\-]+$', v):
            raise ValueError("session_id contains invalid characters")
        return v

    @field_validator("page_path")
    @classmethod
    def sanitize_page_path(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("/"):
            v = "/" + v
        return v[:255]

    @field_validator("ip_hash")
    @classmethod
    def validate_ip_hash(cls, v: str) -> str:
        if not re.match(r'^[a-fA-F0-9]{64}$', v):
            raise ValueError("ip_hash must be a valid 64-character hex SHA-256 hash")
        return v.lower()
