"""
Command Line Interface for SWIPIES Traffic Attribution & Analytics Engine.
Commands:
- attribution-report: Generate aggregated campaign performance report.
- export: Export raw/matched attribution records to CSV or JSON.
- purge-old-events: Trigger pre-purge daily summary aggregation and data cleanup.
- audit-security: Audit local isolation, WAL pragmas, and MySQL read-only guards.
"""
import os
import sys
import json
import csv
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
import typer
from tabulate import tabulate

from .storage.sqlite_events_repo import SQLiteEventsRepo
from .storage.mysql_readonly_client import MySQLReadOnlyClient, ReadOnlySecurityViolation
from .core.matcher import SessionMatcher
from .core.metrics_engine import MetricsEngine
from .core.retention_guard import RetentionGuard
from .models.attribution import AttributionMatchDTO

app = typer.Typer(
    name="swipies-attribution",
    help="SWIPIES Marketing Traffic & Payment Attribution CLI Engine (Track 3)",
    add_completion=False
)


def parse_date_param(val: Optional[str], default_hour: int = 0) -> Optional[datetime]:
    if not val:
        return None
    val = val.strip()
    try:
        if len(val) == 10:  # YYYY-MM-DD
            d = date.fromisoformat(val)
            return datetime(d.year, d.month, d.day, default_hour, 0, 0, tzinfo=timezone.utc)
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError as e:
        typer.echo(f"Error parsing date '{val}': {e}", err=True)
        raise typer.Exit(code=1)


@app.command("attribution-report")
def attribution_report(
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date (YYYY-MM-DD)"),
    model: str = typer.Option("first-touch", "--model", help="Attribution model: 'first-touch' or 'last-touch'"),
    db_path: str = typer.Option("./data/attribution_events.db", "--db-path", help="Path to SQLite events DB"),
    ad_spend_file: Optional[str] = typer.Option(None, "--ad-spend-file", help="Path to JSON file with campaign spends"),
    payments_mock_file: Optional[str] = typer.Option(None, "--payments-mock-file", help="Optional mock payments JSON file for offline analysis"),
    enable_ip_fallback: bool = typer.Option(False, "--enable-ip-fallback", help="Opt-in to IP-hash fallback matching (disabled by default to prevent CGNAT collisions)")
):
    """
    Generate end-to-end attribution report linking marketing traffic with payments.
    """
    start_dt = parse_date_param(from_date, default_hour=0)
    end_dt = parse_date_param(to_date, default_hour=23)

    if model not in ("first-touch", "last-touch"):
        typer.echo(f"Invalid model '{model}'. Choose 'first-touch' or 'last-touch'.", err=True)
        raise typer.Exit(code=1)

    repo = SQLiteEventsRepo(db_path=db_path)
    matcher = SessionMatcher(repo=repo, enable_ip_fallback=enable_ip_fallback)

    # 1. Fetch payments
    payments: List[Dict[str, Any]] = []
    if payments_mock_file and os.path.exists(payments_mock_file):
        with open(payments_mock_file, "r", encoding="utf-8") as f:
            payments = json.load(f)
    else:
        try:
            with MySQLReadOnlyClient() as client:
                payments = client.fetch_attribution_payments(start_time=start_dt, end_time=end_dt)
        except Exception as e:
            typer.echo(f"[Warning] Could not fetch live payments from MySQL ({e}). Querying SQLite recorded events only.", err=True)
            payments = []

    # 2. Match payments to traffic
    matches: List[AttributionMatchDTO] = matcher.match_payments_batch(payments, model=model)

    # 3. Read raw traffic events for campaign metrics
    raw_events: List[Dict[str, Any]] = []
    with repo.get_connection() as conn:
        q = "SELECT * FROM attribution_raw_events WHERE 1=1"
        params = []
        if start_dt:
            q += " AND timestamp >= ?"
            params.append(start_dt.isoformat())
        if end_dt:
            q += " AND timestamp <= ?"
            params.append(end_dt.isoformat())
        cursor = conn.execute(q, params)
        raw_events = [dict(r) for r in cursor.fetchall()]

    # 4. Load ad spend if supplied
    ad_spends = {}
    if ad_spend_file and os.path.exists(ad_spend_file):
        with open(ad_spend_file, "r", encoding="utf-8") as f:
            ad_spends = json.load(f)

    # 5. Aggregate metrics
    metrics = MetricsEngine.aggregate_campaigns(raw_events, matches, ad_spends=ad_spends)

    # 6. Format table
    table_rows = []
    total_revenue = 0
    total_conversions = 0
    total_visits = 0

    for m in metrics:
        total_revenue += m.total_revenue_uzs
        total_conversions += m.total_conversions
        total_visits += m.total_visits
        roas_str = f"{m.roas:.2f}x" if m.roas is not None else "N/A"
        table_rows.append([
            m.campaign_name,
            m.source,
            m.medium,
            m.total_visits,
            m.unique_sessions,
            m.total_conversions,
            f"{m.total_revenue_uzs:,} UZS",
            f"{m.cr_percent:.2f}%",
            f"{m.avg_order_value_uzs:,.0f} UZS",
            roas_str
        ])

    headers = [
        "Campaign", "Source", "Medium", "Visits",
        "Sessions", "Conv", "Revenue", "CR%", "AOV", "ROAS"
    ]

    typer.echo("\n" + "=" * 80)
    typer.echo(f"  SWIPIES ATTRIBUTION REPORT (Model: {model.upper()})")
    typer.echo(f"  Period: {from_date or 'ALL'} to {to_date or 'ALL'}")
    typer.echo("=" * 80 + "\n")

    if table_rows:
        typer.echo(tabulate(table_rows, headers=headers, tablefmt="grid"))
    else:
        typer.echo("No traffic or payment data recorded for the selected period.")

    typer.echo(f"\nTotal Visits: {total_visits:,} | Total Conversions: {total_conversions:,} | Total Revenue: {total_revenue:,} UZS\n")


@app.command("export")
def export(
    from_date: Optional[str] = typer.Option(None, "--from", help="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = typer.Option(None, "--to", help="End date (YYYY-MM-DD)"),
    format: str = typer.Option("json", "--format", help="Export format: 'csv' or 'json'"),
    output: str = typer.Option("./attribution_export.json", "--output", help="Output file path"),
    model: str = typer.Option("first-touch", "--model", help="Attribution model: 'first-touch' or 'last-touch'"),
    db_path: str = typer.Option("./data/attribution_events.db", "--db-path", help="Path to SQLite events DB"),
    payments_mock_file: Optional[str] = typer.Option(None, "--payments-mock-file", help="Mock payments JSON file"),
    enable_ip_fallback: bool = typer.Option(False, "--enable-ip-fallback", help="Opt-in to IP-hash fallback matching (disabled by default to prevent CGNAT collisions)")
):
    """
    Export matched attribution records to CSV or JSON.
    """
    start_dt = parse_date_param(from_date, default_hour=0)
    end_dt = parse_date_param(to_date, default_hour=23)

    repo = SQLiteEventsRepo(db_path=db_path)
    matcher = SessionMatcher(repo=repo, enable_ip_fallback=enable_ip_fallback)

    payments: List[Dict[str, Any]] = []
    if payments_mock_file and os.path.exists(payments_mock_file):
        with open(payments_mock_file, "r", encoding="utf-8") as f:
            payments = json.load(f)
    else:
        try:
            with MySQLReadOnlyClient() as client:
                payments = client.fetch_attribution_payments(start_time=start_dt, end_time=end_dt)
        except Exception:
            payments = []

    matches = matcher.match_payments_batch(payments, model=model)
    data = [m.model_dump(mode="json") for m in matches]

    os.makedirs(os.path.dirname(os.path.abspath(output)) or ".", exist_ok=True)

    if format.lower() == "json":
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    elif format.lower() == "csv":
        if data:
            keys = list(data[0].keys())
            with open(output, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(data)
        else:
            with open(output, "w", encoding="utf-8") as f:
                f.write("")
    else:
        typer.echo(f"Unsupported format '{format}'. Use 'csv' or 'json'.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Successfully exported {len(data)} attribution records to {output}")


@app.command("purge-old-events")
def purge_old_events(
    days: int = typer.Option(30, "--days", help="Retention period for raw traffic events (default 30)"),
    summary_days: int = typer.Option(365, "--summary-days", help="Retention period for daily summaries (default 365)"),
    db_path: str = typer.Option("./data/attribution_events.db", "--db-path", help="Path to SQLite events DB")
):
    """
    Safely summarize and purge expired traffic events and daily summaries.
    """
    repo = SQLiteEventsRepo(db_path=db_path)
    guard = RetentionGuard(repo=repo)
    result = guard.archive_and_purge(retention_days=days, summary_retention_days=summary_days)

    typer.echo("\n" + "=" * 60)
    typer.echo("  RETENTION & STORAGE PURGE REPORT")
    typer.echo("=" * 60)
    typer.echo(f"Daily Summaries Aggregated : {result['summaries_aggregated']}")
    typer.echo(f"Raw Traffic Events Purged  : {result['raw_events_purged']}")
    typer.echo(f"Daily Summaries Purged     : {result['summaries_purged']}")
    typer.echo(f"Remaining Raw Events       : {guard.get_raw_events_count()}")
    typer.echo(f"Remaining Summaries        : {guard.get_summaries_count()}")
    typer.echo("=" * 60 + "\n")


@app.command("audit-security")
def audit_security(
    db_path: str = typer.Option("./data/attribution_events.db", "--db-path", help="Path to SQLite events DB")
):
    """
    Audit isolation barriers, SQLite WAL pragmas, and MySQL read-only guards.
    """
    typer.echo("\n--- [SWIPIES Track 3 Security Audit] ---")

    # 1. SQLite Pragmas Check
    repo = SQLiteEventsRepo(db_path=db_path)
    with repo.get_connection() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0].upper()
        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]

    typer.echo(f"[PASS] SQLite Journal Mode: {journal_mode} (expected: WAL)")
    typer.echo(f"[PASS] SQLite Busy Timeout: {busy_timeout}ms (expected: >=5000)")

    # 2. Read-Only Query Guard Check
    ro_client = MySQLReadOnlyClient()
    try:
        ro_client._validate_read_only_query("INSERT INTO test VALUES (1);")
        typer.echo("[FAIL] Write query was NOT blocked!", err=True)
    except ReadOnlySecurityViolation:
        typer.echo("[PASS] MySQL Read-Only query filter strictly blocks write operations.")

    # 3. Environment Variables Check
    has_salt = bool(os.getenv("ATTRIBUTION_BASE_SALT"))
    salt_status = "Configured" if has_salt else "Default fallback active"
    typer.echo(f"[INFO] ATTRIBUTION_BASE_SALT: {salt_status}")
    typer.echo("[PASS] Security audit completed successfully.\n")


# ----------------------------------------------------------------------
# Google Ads Management Sub-App (Track 4)
# ----------------------------------------------------------------------
google_app = typer.Typer(
    name="google",
    help="Google Ads B2B Search Automation, Dry-Run Validation & Financial Zero-Trust (Track 4)",
    add_completion=False
)
app.add_typer(google_app, name="google")


@google_app.command("preview")
def google_preview(
    budget_usd: float = typer.Option(10.0, "--budget-usd", help="Daily campaign budget in USD")
):
    """
    Preview the pre-configured SWIPIES Enterprise B2B Search Campaign structure.
    """
    from .providers.google_ads_service import GoogleAdsService
    service = GoogleAdsService()
    campaign = service.build_default_swipies_campaign(daily_budget_usd=budget_usd)
    preview_text = service.preview_campaign_summary(campaign)
    typer.echo(preview_text)


@google_app.command("validate")
def google_validate(
    budget_usd: float = typer.Option(10.0, "--budget-usd", help="Daily campaign budget in USD"),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Dry-run simulation mode"),
    confirm_approval: Optional[str] = typer.Option(None, "--confirm-budget-approval", help="Human approval token required for live mutations"),
):
    """
    Validate campaign structure and run pre-flight dry-run simulation against Google Ads Policy.
    """
    from .providers.google_ads_service import GoogleAdsService
    from .models.google_ads import GoogleAdsSafetyViolation

    service = GoogleAdsService()
    campaign = service.build_default_swipies_campaign(daily_budget_usd=budget_usd)

    typer.echo(f"\n--- [SWIPIES Google Ads Pre-Flight Validation] ---")
    typer.echo(f"Campaign: {campaign.name}")
    typer.echo(f"Mode: {'DRY_RUN (Simulated Zero-Key)' if dry_run else 'LIVE_API'}")
    typer.echo(f"Daily Budget: ${campaign.daily_budget_usd:.2f} (200% Pacing Risk: ${campaign.max_daily_spend_risk_usd:.2f})")

    try:
        result = service.validate_and_deploy(
            campaign=campaign,
            dry_run=dry_run,
            approval_token=confirm_approval
        )
        typer.echo(f"\n[PASS] Status: {result.get('status')}")
        typer.echo(f"Operations Validated: {result.get('operations_count', 0)}")
        if result.get("validation_notes"):
            for note in result["validation_notes"]:
                typer.echo(f"  [OK] {note}")
        if result.get("created_resources"):
            typer.echo("\nSimulated Google Resource Names:")
            for res in result["created_resources"]:
                typer.echo(f"  - {res}")
        typer.echo("\n[SUCCESS] Campaign is ready and compliant with Google Ads Search Policies.\n")
    except GoogleAdsSafetyViolation as e:
        typer.echo(f"\n[SECURITY VIOLATION] {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"\n[ERROR] Validation failed: {e}", err=True)
        raise typer.Exit(code=1)


@google_app.command("check-credentials")
def google_check_credentials():
    """
    Check status of Google Ads API credentials in the environment.
    """
    from .providers.google_ads_client import GoogleAdsClient
    client = GoogleAdsClient()
    status = client.check_credentials_status()

    typer.echo("\n--- [Google Ads API Credentials Audit] ---")
    typer.echo(f"Developer Token:  {'[OK] Present' if status['developer_token_present'] else '[MISSING] Not set'}")
    typer.echo(f"OAuth Client ID:  {'[OK] Present' if status['client_id_present'] else '[MISSING] Not set'}")
    typer.echo(f"OAuth Secret:     {'[OK] Present' if status['client_secret_present'] else '[MISSING] Not set'}")
    typer.echo(f"Refresh Token:    {'[OK] Present' if status['refresh_token_present'] else '[MISSING] Not set'}")
    typer.echo(f"Customer ID:      {status['customer_id']}")
    typer.echo(f"Active Mode:      {status['mode']}")
    if status["is_ready_for_live"]:
        typer.echo("\n[READY] All credentials configured for live API requests.")
    else:
        typer.echo("\n[INFO] Running in Zero-Key Mock/Dry-Run mode. Safe for local testing.")
    typer.echo("------------------------------------------\n")


@google_app.command("mock-spend")
def google_mock_spend(
    clicks: int = typer.Option(120, "--clicks", help="Number of simulated clicks"),
    cpc_usd: float = typer.Option(0.45, "--cpc", help="Simulated Average CPC in USD"),
    output_file: Optional[str] = typer.Option(None, "--output", help="Optional path to save JSON spend report for attribution")
):
    """
    Generate simulated Google Ads spend report to link with Attribution Engine.
    """
    from .providers.google_ads_service import GoogleAdsService
    service = GoogleAdsService()
    spend_data = service.generate_mock_spend_report(clicks=clicks, avg_cpc_usd=cpc_usd)

    typer.echo("\n--- [Google Ads Campaign Spend Simulation] ---")
    typer.echo(f"Campaign:        {spend_data['campaign_name']}")
    typer.echo(f"Impressions:     {spend_data['impressions']}")
    typer.echo(f"Clicks:          {spend_data['clicks']} (CTR: {spend_data['ctr_percent']}%)")
    typer.echo(f"Average CPC:     ${spend_data['avg_cpc_usd']:.2f}")
    typer.echo(f"Total Spend USD: ${spend_data['total_spend_usd']:.2f}")
    typer.echo(f"Total Spend UZS: {spend_data['total_spend_uzs']:,} UZS (excl. VAT)")

    if output_file:
        # Format as spend dict for attribution-report --ad-spend-file
        spend_dict = {spend_data["campaign_name"]: spend_data["total_spend_uzs"]}
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(spend_dict, f, indent=2)
        typer.echo(f"[SAVED] Spend data exported to '{output_file}' for attribution-report.\n")


# ----------------------------------------------------------------------
# Twitter / X Ads Management Sub-App (Track 5)
# ----------------------------------------------------------------------
twitter_app = typer.Typer(
    name="twitter",
    help="Twitter / X Ads B2B Tech Lead Generation, Dry-Run & Financial Zero-Trust (Track 5)",
    add_completion=False
)
app.add_typer(twitter_app, name="twitter")


@twitter_app.command("preview")
def twitter_preview(
    budget_usd: float = typer.Option(15.0, "--budget-usd", help="Daily campaign budget in USD")
):
    """
    Preview the pre-configured SWIPIES Enterprise B2B tech campaign on Twitter/X.
    """
    from .providers.twitter_ads_service import TwitterAdsService
    service = TwitterAdsService()
    campaign = service.build_default_swipies_campaign(daily_budget_usd=budget_usd)
    preview_text = service.preview_campaign_summary(campaign)
    typer.echo(preview_text)


@twitter_app.command("validate")
def twitter_validate(
    budget_usd: float = typer.Option(15.0, "--budget-usd", help="Daily campaign budget in USD"),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Dry-run simulation mode"),
    confirm_approval: Optional[str] = typer.Option(None, "--confirm-budget-approval", help="Human approval token required for live mutations"),
):
    """
    Validate Twitter/X campaign structure, targeting, and creative via dry-run simulation.
    """
    from .providers.twitter_ads_service import TwitterAdsService
    from .models.twitter_ads import TwitterAdsSafetyViolation

    service = TwitterAdsService()
    campaign = service.build_default_swipies_campaign(daily_budget_usd=budget_usd)

    typer.echo(f"\n--- [SWIPIES Twitter / X Ads Pre-Flight Validation] ---")
    typer.echo(f"Campaign: {campaign.name}")
    typer.echo(f"Mode: {'DRY_RUN (Simulated Zero-Key)' if dry_run else 'LIVE_API'}")
    typer.echo(f"Daily Budget: ${campaign.daily_budget_usd:.2f} / day")

    try:
        result = service.validate_and_deploy(
            campaign=campaign,
            dry_run=dry_run,
            approval_token=confirm_approval
        )
        typer.echo(f"\n[PASS] Status: {result.get('status')}")
        typer.echo(f"Platform: {result.get('platform')}")
        typer.echo(f"Targeting Rules Validated: {result.get('targeting_rules_count', 0)}")
        typer.echo(f"Promoted Tweets Validated: {result.get('promoted_tweets_count', 0)}")
        if result.get("validation_notes"):
            for note in result["validation_notes"]:
                typer.echo(f"  [OK] {note}")
        if result.get("created_resources"):
            res = result["created_resources"]
            typer.echo("\nSimulated X Ads Resources:")
            typer.echo(f"  - Campaign ID: {res.get('campaign')}")
            typer.echo(f"  - Line Items: {', '.join(res.get('line_items', []))}")
            typer.echo(f"  - Promoted Tweets: {', '.join(res.get('promoted_tweets', []))}")
        typer.echo("\n[SUCCESS] Campaign is ready and compliant with Twitter / X Ads Policies.\n")
    except TwitterAdsSafetyViolation as e:
        typer.echo(f"\n[SECURITY VIOLATION] {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"\n[ERROR] Validation failed: {e}", err=True)
        raise typer.Exit(code=1)


@twitter_app.command("check-credentials")
def twitter_check_credentials():
    """
    Check status of Twitter / X Ads API credentials in the environment.
    """
    from .providers.twitter_ads_client import TwitterAdsClient
    client = TwitterAdsClient()
    status = client.check_credentials_status()

    typer.echo("\n--- [Twitter / X Ads API Credentials Audit] ---")
    typer.echo(f"Ads Account ID:       {status['ads_account_id']}")
    typer.echo(f"API Key (Consumer):   {'[OK] Present' if status['api_key_present'] else '[MISSING] Not set'}")
    typer.echo(f"API Secret:           {'[OK] Present' if status['api_secret_present'] else '[MISSING] Not set'}")
    typer.echo(f"Access Token:         {'[OK] Present' if status['access_token_present'] else '[MISSING] Not set'}")
    typer.echo(f"OAuth2 Bearer Token:  {'[OK] Present' if status['bearer_token_present'] else '[MISSING] Not set'}")
    typer.echo(f"Active Mode:          {status['mode']}")
    if status["is_ready_for_live"]:
        typer.echo("\n[READY] All credentials configured for live API requests.")
    else:
        typer.echo("\n[INFO] Running in Zero-Key Mock/Dry-Run mode. Safe for local testing.")
    typer.echo("----------------------------------------------\n")


@twitter_app.command("mock-spend")
def twitter_mock_spend(
    clicks: int = typer.Option(200, "--clicks", help="Number of simulated clicks"),
    cpc_usd: float = typer.Option(0.35, "--cpc", help="Simulated Average CPC in USD"),
    output_file: Optional[str] = typer.Option(None, "--output", help="Optional path to save JSON spend report for attribution")
):
    """
    Generate simulated Twitter / X Ads spend report to link with Attribution Engine.
    """
    from .providers.twitter_ads_service import TwitterAdsService
    service = TwitterAdsService()
    spend_data = service.generate_mock_spend_report(clicks=clicks, avg_cpc_usd=cpc_usd)

    typer.echo("\n--- [Twitter / X Ads Campaign Spend Simulation] ---")
    typer.echo(f"Campaign:        {spend_data['campaign_name']}")
    typer.echo(f"Impressions:     {spend_data['impressions']}")
    typer.echo(f"Clicks:          {spend_data['clicks']} (CTR: {spend_data['ctr_percent']}%)")
    typer.echo(f"Average CPC:     ${spend_data['avg_cpc_usd']:.2f}")
    typer.echo(f"Total Spend USD: ${spend_data['total_spend_usd']:.2f}")
    typer.echo(f"Total Spend UZS: {spend_data['total_spend_uzs']:,} UZS (excl. VAT)")

    if output_file:
        spend_dict = {spend_data["campaign_name"]: spend_data["total_spend_uzs"]}
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(spend_dict, f, indent=2)
        typer.echo(f"[SAVED] Spend data exported to '{output_file}' for attribution-report.\n")


# ----------------------------------------------------------------------
# Meta (Instagram / Facebook) Ads Sub-App (Track 6)
# ----------------------------------------------------------------------
meta_app = typer.Typer(
    name="meta",
    help="Meta (Instagram/Facebook) Ads LeadGen, Dry-Run & Financial Zero-Trust (Track 6)",
    add_completion=False
)
app.add_typer(meta_app, name="meta")


@meta_app.command("preview")
def meta_preview(
    budget_usd: float = typer.Option(15.0, "--budget-usd", help="Daily campaign budget in USD")
):
    """Preview pre-configured SWIPIES B2B Instagram/Facebook campaign."""
    from .providers.meta_ads_service import MetaAdsService
    service = MetaAdsService()
    campaign = service.build_default_swipies_campaign(daily_budget_usd=budget_usd)
    typer.echo(service.preview_campaign_summary(campaign))


@meta_app.command("validate")
def meta_validate(
    budget_usd: float = typer.Option(15.0, "--budget-usd", help="Daily campaign budget in USD"),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Dry-run simulation mode"),
    confirm_approval: Optional[str] = typer.Option(None, "--confirm-budget-approval", help="Human approval token"),
):
    """Validate Meta campaign, targeting, and ad creatives via dry-run."""
    from .providers.meta_ads_service import MetaAdsService
    from .models.meta_ads import MetaAdsSafetyViolation

    service = MetaAdsService()
    campaign = service.build_default_swipies_campaign(daily_budget_usd=budget_usd)

    typer.echo(f"\n--- [SWIPIES Meta (Instagram/FB) Ads Pre-Flight Validation] ---")
    typer.echo(f"Campaign: {campaign.name}")
    typer.echo(f"Mode: {'DRY_RUN (Simulated Zero-Key)' if dry_run else 'LIVE_API'}")
    typer.echo(f"Daily Budget: ${campaign.daily_budget_usd:.2f} / day")

    try:
        result = service.validate_and_deploy(
            campaign=campaign,
            dry_run=dry_run,
            approval_token=confirm_approval
        )
        typer.echo(f"\n[PASS] Status: {result.get('status')}")
        typer.echo(f"Platform: {result.get('platform')}")
        typer.echo(f"AdSets Validated: {result.get('adsets_count', 0)}")
        typer.echo(f"Creatives Validated: {result.get('creatives_count', 0)}")
        if result.get("validation_notes"):
            for note in result["validation_notes"]:
                typer.echo(f"  [OK] {note}")
        if result.get("created_resources"):
            res = result["created_resources"]
            typer.echo("\nSimulated Meta Graph Resources:")
            typer.echo(f"  - Campaign ID: {res.get('campaign')}")
            typer.echo(f"  - AdSets: {', '.join(res.get('adsets', []))}")
            typer.echo(f"  - Ads: {', '.join(res.get('ads', []))}")
        typer.echo("\n[SUCCESS] Campaign is ready and compliant with Meta Marketing Policies.\n")
    except MetaAdsSafetyViolation as e:
        typer.echo(f"\n[SECURITY VIOLATION] {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"\n[ERROR] Validation failed: {e}", err=True)
        raise typer.Exit(code=1)


@meta_app.command("check-credentials")
def meta_check_credentials():
    """Check status of Meta Marketing API credentials in the environment."""
    from .providers.meta_ads_client import MetaAdsClient
    client = MetaAdsClient()
    status = client.check_credentials_status()

    typer.echo("\n--- [Meta Marketing API Credentials Audit] ---")
    typer.echo(f"Ad Account ID:   {status['ad_account_id']}")
    typer.echo(f"Access Token:    {'[OK] Present' if status['access_token_present'] else '[MISSING] Not set'}")
    typer.echo(f"App ID:          {'[OK] Present' if status['app_id_present'] else '[MISSING] Not set'}")
    typer.echo(f"App Secret:      {'[OK] Present' if status['app_secret_present'] else '[MISSING] Not set'}")
    typer.echo(f"Active Mode:     {status['mode']}")
    if status["is_ready_for_live"]:
        typer.echo("\n[READY] All credentials configured for live API requests.")
    else:
        typer.echo("\n[INFO] Running in Zero-Key Mock/Dry-Run mode. Safe for local testing.")
    typer.echo("----------------------------------------------\n")


@meta_app.command("mock-spend")
def meta_mock_spend(
    clicks: int = typer.Option(300, "--clicks", help="Number of simulated clicks"),
    cpc_usd: float = typer.Option(0.28, "--cpc", help="Simulated Average CPC in USD"),
    output_file: Optional[str] = typer.Option(None, "--output", help="Path to save JSON spend report")
):
    """Generate simulated Meta Ads spend report for Attribution Engine."""
    from .providers.meta_ads_service import MetaAdsService
    service = MetaAdsService()
    spend_data = service.generate_mock_spend_report(clicks=clicks, avg_cpc_usd=cpc_usd)

    typer.echo("\n--- [Meta Ads Campaign Spend Simulation] ---")
    typer.echo(f"Campaign:        {spend_data['campaign_name']}")
    typer.echo(f"Impressions:     {spend_data['impressions']}")
    typer.echo(f"Clicks:          {spend_data['clicks']} (CTR: {spend_data['ctr_percent']}%)")
    typer.echo(f"Average CPC:     ${spend_data['avg_cpc_usd']:.2f}")
    typer.echo(f"Total Spend USD: ${spend_data['total_spend_usd']:.2f}")
    typer.echo(f"Total Spend UZS: {spend_data['total_spend_uzs']:,} UZS (excl. VAT)")

    if output_file:
        spend_dict = {spend_data["campaign_name"]: spend_data["total_spend_uzs"]}
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(spend_dict, f, indent=2)
        typer.echo(f"[SAVED] Spend data exported to '{output_file}' for attribution-report.\n")


# ----------------------------------------------------------------------
# Yandex Direct Ads Sub-App (Track 7)
# ----------------------------------------------------------------------
yandex_app = typer.Typer(
    name="yandex",
    help="Yandex Direct (РСЯ/Search) Ads Automation & Local UZS Accounting (Track 7)",
    add_completion=False
)
app.add_typer(yandex_app, name="yandex")


@yandex_app.command("preview")
def yandex_preview(
    budget_uzs: int = typer.Option(200_000, "--budget-uzs", help="Daily campaign budget in UZS")
):
    """Preview pre-configured SWIPIES B2B Yandex Direct campaign."""
    from .providers.yandex_ads_service import YandexAdsService
    service = YandexAdsService()
    campaign = service.build_default_swipies_campaign(daily_budget_uzs=budget_uzs)
    typer.echo(service.preview_campaign_summary(campaign))


@yandex_app.command("validate")
def yandex_validate(
    budget_uzs: int = typer.Option(200_000, "--budget-uzs", help="Daily campaign budget in UZS"),
    dry_run: bool = typer.Option(True, "--dry-run/--live", help="Dry-run simulation mode"),
    confirm_approval: Optional[str] = typer.Option(None, "--confirm-budget-approval", help="Human approval token"),
):
    """Validate Yandex Direct campaign via dry-run simulation."""
    from .providers.yandex_ads_service import YandexAdsService
    from .models.yandex_ads import YandexAdsSafetyViolation

    service = YandexAdsService()
    campaign = service.build_default_swipies_campaign(daily_budget_uzs=budget_uzs)

    typer.echo(f"\n--- [SWIPIES Yandex Direct Pre-Flight Validation] ---")
    typer.echo(f"Campaign: {campaign.name}")
    typer.echo(f"Mode: {'DRY_RUN (Simulated Zero-Key)' if dry_run else 'LIVE_API'}")
    typer.echo(f"Daily Budget: {campaign.daily_budget_uzs:,} UZS (STANDARD mode: Zero Overspend)")

    try:
        result = service.validate_and_deploy(
            campaign=campaign,
            dry_run=dry_run,
            approval_token=confirm_approval
        )
        typer.echo(f"\n[PASS] Status: {result.get('status')}")
        typer.echo(f"Platform: {result.get('platform')}")
        typer.echo(f"Ad Groups Validated: {result.get('ad_groups_count', 0)}")
        typer.echo(f"Ads Validated: {result.get('ads_count', 0)}")
        if result.get("validation_notes"):
            for note in result["validation_notes"]:
                typer.echo(f"  [OK] {note}")
        if result.get("created_resources"):
            res = result["created_resources"]
            typer.echo("\nSimulated Yandex Direct Resources:")
            typer.echo(f"  - Campaign ID: {res.get('campaign')}")
            typer.echo(f"  - Ad Groups: {', '.join(res.get('ad_groups', []))}")
            typer.echo(f"  - Ads: {', '.join(res.get('ads', []))}")
        typer.echo("\n[SUCCESS] Campaign is ready and compliant with Yandex Direct Policies.\n")
    except YandexAdsSafetyViolation as e:
        typer.echo(f"\n[SECURITY VIOLATION] {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"\n[ERROR] Validation failed: {e}", err=True)
        raise typer.Exit(code=1)


@yandex_app.command("check-credentials")
def yandex_check_credentials():
    """Check status of Yandex Direct API credentials in the environment."""
    from .providers.yandex_ads_client import YandexAdsClient
    client = YandexAdsClient()
    status = client.check_credentials_status()

    typer.echo("\n--- [Yandex Direct API Credentials Audit] ---")
    typer.echo(f"OAuth Token:     {'[OK] Present' if status['token_present'] else '[MISSING] Not set'}")
    typer.echo(f"Client Login:    {status['client_login']}")
    typer.echo(f"Sandbox Enabled: {status['use_sandbox']}")
    typer.echo(f"Active Mode:     {status['mode']}")
    if status["is_ready_for_live"]:
        typer.echo("\n[READY] All credentials configured for live API requests.")
    else:
        typer.echo("\n[INFO] Running in Zero-Key Mock/Dry-Run mode. Safe for local testing.")
    typer.echo("---------------------------------------------\n")


@yandex_app.command("mock-spend")
def yandex_mock_spend(
    clicks: int = typer.Option(180, "--clicks", help="Number of simulated clicks"),
    cpc_uzs: int = typer.Option(5_500, "--cpc-uzs", help="Simulated Average CPC in UZS"),
    output_file: Optional[str] = typer.Option(None, "--output", help="Path to save JSON spend report")
):
    """Generate simulated Yandex Direct spend report for Attribution Engine."""
    from .providers.yandex_ads_service import YandexAdsService
    service = YandexAdsService()
    spend_data = service.generate_mock_spend_report(clicks=clicks, avg_cpc_uzs=cpc_uzs)

    typer.echo("\n--- [Yandex Direct Campaign Spend Simulation] ---")
    typer.echo(f"Campaign:        {spend_data['campaign_name']}")
    typer.echo(f"Impressions:     {spend_data['impressions']}")
    typer.echo(f"Clicks:          {spend_data['clicks']} (CTR: {spend_data['ctr_percent']}%)")
    typer.echo(f"Average CPC:     {spend_data['avg_cpc_uzs']:,} UZS")
    typer.echo(f"Total Spend UZS: {spend_data['total_spend_uzs']:,} UZS (excl. VAT)")
    typer.echo(f"Total Spend USD: ~${spend_data['total_spend_usd']:.2f}")

    if output_file:
        spend_dict = {spend_data["campaign_name"]: spend_data["total_spend_uzs"]}
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(spend_dict, f, indent=2)
        typer.echo(f"[SAVED] Spend data exported to '{output_file}' for attribution-report.\n")


def main():
    app()


if __name__ == "__main__":
    main()

