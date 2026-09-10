"""
Tests for Meta (Instagram / Facebook) Ads CLI commands integration.
"""
import os
import json
from typer.testing import CliRunner
from src.cli import app

runner = CliRunner()


def test_cli_meta_check_credentials():
    result = runner.invoke(app, ["meta", "check-credentials"])
    assert result.exit_code == 0
    assert "Meta Marketing API Credentials Audit" in result.output
    assert "Active Mode:" in result.output


def test_cli_meta_preview():
    result = runner.invoke(app, ["meta", "preview", "--budget-usd", "30.0"])
    assert result.exit_code == 0
    assert "M E T A  ( I N S T A G R A M )  A D S  P R E V I E W" in result.output
    assert "$30.00 / day" in result.output
    assert "Directors_and_Founders_Central_Asia" in result.output


def test_cli_meta_validate_dry_run():
    result = runner.invoke(app, ["meta", "validate", "--budget-usd", "15.0", "--dry-run"])
    assert result.exit_code == 0
    assert "SWIPIES Meta (Instagram/FB) Ads Pre-Flight Validation" in result.output
    assert "[PASS] Status: SUCCESS_VALIDATED" in result.output
    assert "Simulated Meta Graph Resources:" in result.output


def test_cli_meta_mock_spend_and_export(tmp_path):
    output_json = str(tmp_path / "test_meta_spend.json")
    result = runner.invoke(app, [
        "meta", "mock-spend",
        "--clicks", "200",
        "--cpc", "0.25",
        "--output", output_json
    ])
    assert result.exit_code == 0
    assert os.path.exists(output_json)

    with open(output_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "swipies_b2b_instagram" in data
    # 200 clicks * $0.25 = $50.00 * 12,800 UZS = 640,000 UZS
    assert data["swipies_b2b_instagram"] == 640_000
