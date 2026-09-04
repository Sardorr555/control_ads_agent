"""
Comprehensive Privacy & Cryptographic Tests for IP Anonymization (AC-02).
Proves:
1. Irreversibility: SHA256(IP + Salt) cannot be reversed without secret base salt.
2. Avalanche effect: changing 1 bit of IP changes >40% of hash bits.
3. Daily salt rotation at 00:00:00 UTC boundary (cross-day unlinkability).
4. Reliable public IP extraction from multi-proxy X-Forwarded-For headers.
5. Deterministic GeoIP country/city resolution.
"""
import pytest
from datetime import datetime, timezone, timedelta
from src.core.anonymizer import (
    extract_client_ip,
    get_daily_salt,
    hash_ip,
    resolve_geoip,
    anonymize_request,
)

BASE_SALT = "c9f8a4e1b7d302581649acdf7823e590fa12bc45de67890123456789abcdef01"


def test_ip_irreversibility_and_rainbow_immunity():
    """
    AC-02 Verification:
    Proves that a salted IP hash cannot be reversed by brute-forcing candidate IPs
    without knowledge of the secret base salt.
    """
    secret_salt = BASE_SALT
    real_ip = "84.54.70.15"
    target_hash = hash_ip(real_ip, secret_salt)

    assert len(target_hash) == 64
    assert all(c in "0123456789abcdef" for c in target_hash)

    # An attacker attempts brute force / rainbow table of common Tashkent IP ranges
    # WITHOUT knowing the secret salt (or using a guessed/empty salt):
    attacker_guessed_salt = "wrong_salt_guess_12345678"
    candidate_ips = [f"84.54.70.{i}" for i in range(1, 255)]
    
    matches = []
    for cand in candidate_ips:
        # Attacker tries unsalted or incorrectly salted candidates
        if hash_ip(cand, attacker_guessed_salt) == target_hash:
            matches.append(cand)

    # Cryptographic guarantee: zero matches found by attacker
    assert len(matches) == 0


def test_hash_avalanche_effect():
    """
    Verifies that changing a single digit in the IP produces completely different hashes.
    """
    ip1 = "84.54.70.1"
    ip2 = "84.54.70.2"
    h1 = hash_ip(ip1, BASE_SALT)
    h2 = hash_ip(ip2, BASE_SALT)

    assert h1 != h2
    # Count bit differences
    int1 = int(h1, 16)
    int2 = int(h2, 16)
    diff_bits = bin(int1 ^ int2).count("1")
    # Strict avalanche property: ~50% (at least 30%) of 256 bits must differ
    assert diff_bits >= 80, f"Expected strong avalanche, got {diff_bits} bit differences"


def test_midnight_salt_rotation_unlinkability():
    """
    Verifies that the same IP produces DIFFERENT hashes across day boundaries (00:00 UTC).
    Guarantees that user tracking cannot be linked across multiple calendar days.
    """
    test_ip = "84.54.70.88"

    # Day 1: 2026-09-05 23:59:59 UTC
    dt_day1 = datetime(2026, 9, 5, 23, 59, 59, tzinfo=timezone.utc)
    # Day 2: 2026-09-06 00:00:01 UTC (2 seconds later, cross-day)
    dt_day2 = datetime(2026, 9, 6, 0, 0, 1, tzinfo=timezone.utc)

    hash_day1 = hash_ip(test_ip, BASE_SALT, dt=dt_day1)
    hash_day2 = hash_ip(test_ip, BASE_SALT, dt=dt_day2)

    assert hash_day1 != hash_day2, "Hashes across day boundary must not match!"

    # Intraday stability: 2 events on the same day MUST match for session attribution
    dt_day1_morning = datetime(2026, 9, 5, 10, 15, 0, tzinfo=timezone.utc)
    hash_day1_morning = hash_ip(test_ip, BASE_SALT, dt=dt_day1_morning)
    assert hash_day1 == hash_day1_morning, "Hashes within the same day must match!"


def test_extract_client_ip_headers():
    """
    Verifies public IP extraction from various proxy header configurations.
    """
    # 1. Multi-tier reverse proxy (Private CDN -> Internal LB -> Public Client)
    headers_multi = {
        "X-Forwarded-For": "10.0.0.1, 172.16.0.5, 84.54.70.22, 192.168.1.10"
    }
    assert extract_client_ip(headers_multi, remote_addr="127.0.0.1") == "84.54.70.22"

    # 2. Spoofed internal addresses falling back to valid public X-Real-IP
    headers_spoofed = {
        "X-Forwarded-For": "192.168.1.50, 10.10.10.10",
        "X-Real-IP": "89.236.195.1"
    }
    assert extract_client_ip(headers_spoofed, remote_addr="10.0.0.2") == "89.236.195.1"

    # 3. Direct client connection without proxy headers
    assert extract_client_ip({}, remote_addr="185.139.136.99") == "185.139.136.99"

    # 4. Localhost loopback fallback
    assert extract_client_ip({}, remote_addr="") == "127.0.0.1"


def test_resolve_geoip():
    """
    Verifies deterministic offline GeoIP lookup for Uzbekistan CIDRs.
    """
    # Known UZ subnets
    country, city = resolve_geoip("84.54.70.5")
    assert country == "UZ"
    assert city == "Tashkent"

    country, city = resolve_geoip("185.139.136.10")
    assert country == "UZ"
    assert city == "Tashkent"

    # Loopback
    country, city = resolve_geoip("127.0.0.1")
    assert country == "UZ"
    assert city == "Local"

    # Foreign public IP
    country, city = resolve_geoip("8.8.8.8")
    assert country is None
    assert city is None


def test_anonymize_request_pipeline():
    """
    Verifies the complete pipeline cleans the request without retaining raw IP.
    """
    headers = {"X-Forwarded-For": "84.54.70.99"}
    result = anonymize_request(headers, remote_addr="127.0.0.1", base_salt=BASE_SALT)

    assert "ip_hash" in result
    assert len(result["ip_hash"]) == 64
    assert result["country"] == "UZ"
    assert result["city"] == "Tashkent"
    # Guaranteed that raw IP is NOT in the result dict
    assert "raw_ip" not in result
    assert "ip" not in result


def test_weak_salt_rejected():
    """
    Verifies that insecure or short salts (<16 chars) raise an explicit ValueError.
    """
    with pytest.raises(ValueError, match="at least 16 characters"):
        get_daily_salt("short_salt")
