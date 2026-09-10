"""
Tests for Yandex Direct Ads CLI commands integration.
"""
import os
import json
from typer.testing import CliRunner
from src.cli import app

runner = CliRunner()


def test_cli_yandex_check_credentials():
    result = runner.invoke(app, ["yandex", "check-credentials"])
    assert result.exit_code == 0
    assert "Yandex Direct API Credentials Audit" in result.output
    assert "Active Mode:" in result.output


def test_cli_yandex_preview():
    result = runner.invoke(app, ["yandex", "preview", "--budget-uzs", "300000"])
    assert result.exit_code == 0
    assert "Y A N D E X  D I R E C T  C A M P A I G N  P R E V I E W" in result.output
    assert "300,000 UZS" in result.output
    assert "Enterprise_AI_Search_UZ" in result.output


def test_cli_yandex_validate_dry_run():
    result = runner.invoke(app, ["yandex", "validate", "--budget-uzs", "200000", "--dry-run"])
    assert result.exit_code == 0
    assert "SWIPIES Yandex Direct Pre-Flight Validation" in result.output
    assert "[PASS] Status: SUCCESS_VALIDATED" in result.output
    assert "Simulated Yandex Direct Resources:" in result.output


def test_cli_yandex_mock_spend_and_export(tmp_path):
    output_json = str(tmp_path / "test_yandex_spend.json")
    result = runner.invoke(app, [
        "yandex", "mock-spend",
        "--clicks", "100",
        "--cpc-uzs", "5000",
        "--output", output_json
    ])
    assert result.exit_code == 0
    assert os.path.exists(output_json)

    with open(output_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "swipies_b2b_yandex_uz" in data
    # 100 clicks * 5,000 UZS = 500,000 UZS
    assert data["swipies_b2b_yandex_uz"] == 500_000
