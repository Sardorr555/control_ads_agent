"""
Tests for Google Ads CLI commands integration.
"""
import os
import json
from typer.testing import CliRunner
from src.cli import app

runner = CliRunner()


def test_cli_google_check_credentials():
    result = runner.invoke(app, ["google", "check-credentials"])
    assert result.exit_code == 0
    assert "Google Ads API Credentials Audit" in result.output
    assert "Active Mode:" in result.output


def test_cli_google_preview():
    result = runner.invoke(app, ["google", "preview", "--budget-usd", "15.0"])
    assert result.exit_code == 0
    assert "G O O G L E  A D S  C A M P A I G N  P R E V I E W" in result.output
    assert "$15.00 / day" in result.output
    assert "Enterprise_RAG_Search_Core" in result.output


def test_cli_google_validate_dry_run():
    result = runner.invoke(app, ["google", "validate", "--budget-usd", "20.0", "--dry-run"])
    assert result.exit_code == 0
    assert "SWIPIES Google Ads Pre-Flight Validation" in result.output
    assert "[PASS] Status: SUCCESS_VALIDATED" in result.output
    assert "Simulated Google Resource Names:" in result.output


def test_cli_google_mock_spend_and_export(tmp_path):
    output_json = str(tmp_path / "test_spend.json")
    result = runner.invoke(app, [
        "google", "mock-spend",
        "--clicks", "50",
        "--cpc", "0.40",
        "--output", output_json
    ])
    assert result.exit_code == 0
    assert os.path.exists(output_json)

    with open(output_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "swipies_b2b_search" in data
    # 50 clicks * $0.40 = $20.00 * 12,800 UZS = 256,000 UZS
    assert data["swipies_b2b_search"] == 256_000
