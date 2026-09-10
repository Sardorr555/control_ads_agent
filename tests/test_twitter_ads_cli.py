"""
Tests for Twitter / X Ads CLI commands integration.
"""
import os
import json
from typer.testing import CliRunner
from src.cli import app

runner = CliRunner()


def test_cli_twitter_check_credentials():
    result = runner.invoke(app, ["twitter", "check-credentials"])
    assert result.exit_code == 0
    assert "Twitter / X Ads API Credentials Audit" in result.output
    assert "Active Mode:" in result.output


def test_cli_twitter_preview():
    result = runner.invoke(app, ["twitter", "preview", "--budget-usd", "25.0"])
    assert result.exit_code == 0
    assert "T W I T T E R  /  X  A D S  C A M P A I G N  P R E V I E W" in result.output
    assert "$25.00 / day" in result.output
    assert "AI_Founders_and_Tech_Leads" in result.output


def test_cli_twitter_validate_dry_run():
    result = runner.invoke(app, ["twitter", "validate", "--budget-usd", "15.0", "--dry-run"])
    assert result.exit_code == 0
    assert "SWIPIES Twitter / X Ads Pre-Flight Validation" in result.output
    assert "[PASS] Status: SUCCESS_VALIDATED" in result.output
    assert "Simulated X Ads Resources:" in result.output


def test_cli_twitter_mock_spend_and_export(tmp_path):
    output_json = str(tmp_path / "test_twitter_spend.json")
    result = runner.invoke(app, [
        "twitter", "mock-spend",
        "--clicks", "100",
        "--cpc", "0.30",
        "--output", output_json
    ])
    assert result.exit_code == 0
    assert os.path.exists(output_json)

    with open(output_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "swipies_x_tech_rag" in data
    # 100 clicks * $0.30 = $30.00 * 12,800 UZS = 384,000 UZS
    assert data["swipies_x_tech_rag"] == 384_000
