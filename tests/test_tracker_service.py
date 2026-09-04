"""
Unit Tests for Tracker Ingestion Service (TASK-4.1).
Validates:
1. Health check routes (/health, /api/v1/track/health).
2. CORS preflight OPTIONS request.
3. Single and batch event ingestion with IP anonymization.
4. Validation error handling for invalid payloads.
"""
import pytest
from src.tracker_service import create_app


@pytest.fixture
def app(tmp_path):
    db_file = str(tmp_path / "tracker_test.db")
    app = create_app(db_path=db_file, base_salt="test_service_salt_min_32_chars_ok")
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_health_check(client):
    res1 = client.get("/health")
    assert res1.status_code == 200
    assert res1.get_json()["status"] == "healthy"

    res2 = client.get("/api/v1/track/health")
    assert res2.status_code == 200
    assert res2.get_json()["status"] == "healthy"


def test_cors_preflight(client):
    res = client.options("/api/v1/track/event")
    assert res.status_code == 204
    assert res.headers.get("Access-Control-Allow-Origin") == "*"
    assert "POST" in res.headers.get("Access-Control-Allow-Methods", "")


def test_single_event_ingestion(client, app):
    payload = {
        "session_id": "swp_test_sess_001",
        "page_path": "/features",
        "time_on_page_sec": 12,
        "utm_source": "meta",
        "utm_medium": "cpc",
        "utm_campaign": "launch_sale",
        "event_type": "pageview"
    }
    headers = {"X-Forwarded-For": "84.54.70.10"}
    res = client.post("/api/v1/track/event", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["saved"] == 1

    repo = app.config["REPO"]
    events = repo.get_events_by_session("swp_test_sess_001")
    assert len(events) == 1
    assert events[0]["page_path"] == "/features"
    assert events[0]["utm_campaign"] == "launch_sale"
    assert len(events[0]["ip_hash"]) == 64
    assert events[0]["country"] == "UZ"
    assert events[0]["city"] == "Tashkent"


def test_batch_event_ingestion(client, app):
    batch = [
        {
            "session_id": f"swp_batch_sess_{i}",
            "page_path": f"/step_{i}",
            "time_on_page_sec": 5 * i,
            "utm_source": "meta",
            "event_type": "heartbeat"
        }
        for i in range(3)
    ]
    res = client.post("/api/v1/track/event", json=batch)
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["saved"] == 3


def test_invalid_payload_rejection(client):
    # Missing session_id
    res = client.post("/api/v1/track/event", json={"page_path": "/test"})
    assert res.status_code == 400
    data = res.get_json()
    assert data["success"] is False
    assert len(data["errors"]) > 0

    # Non-JSON payload
    res_raw = client.post("/api/v1/track/event", data="plain text", content_type="text/plain")
    assert res_raw.status_code == 400
