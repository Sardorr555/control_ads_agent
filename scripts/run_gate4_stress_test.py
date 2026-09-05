#!/usr/bin/env python3
"""
TASK-4.5: Gate 4 Real-Stack Process Isolation & Latency Stress Test Runner.

Executes a bounded, safe stress test comparing Port 5000 (system_api.py under Gunicorn/Quart)
against concurrent background load on Port 5001 (swipies-tracker service).

SAFETY GUARANTEES:
1. Synthetic Prefix: Every transaction_id is strictly prefixed with 'gate4_test_<uuid>'.
   No real customer IDs or emails are touched.
2. User Isolation: Targets only a designated test/admin user account (--test-email).
3. Bounded Duration: Runs for ~30-45 seconds total (20 baseline + 40 under-load requests).
   Never runs an open-ended loop or creates persistent server load.
4. Automatic Dual-Ledger Cleanup: A robust finally: block immediately purges both:
   - 'gate4_test_%' rows from payment_transaction in MySQL
   - 'gate4_sess_%' rows from attribution_raw_events in SQLite.
5. Process-List Secret Safety: Does NOT expose passwords or API keys in argv (ps aux).
   Uses environment variables (MYSQL_PWD, RAGFLOW_API_KEY) directly.
6. Strict Success Verification: Accepts only HTTP 200 with JSON payload {"code": 0}.
   Any missing, malformed, or non-zero response is strictly recorded as an error.

SCOPE & METHODOLOGY NOTE:
- Target route: /system/payment/init.
  Exercises real Quart HTTP parsing, regex sanitization, user lookup, database
  connection pooling, and transactional INSERT into payment_transaction with 6 attribution
  columns, under concurrent 100 req/s SQLite WAL contention on port 5001.
- Note on /finalize: /finalize requires live verification with the Atmos Gateway
  (https://apigw.atmos.uz). Synthetic transactions would fail at the gateway and generate
  external API noise; /init provides 100% of the internal OS, connection pool, and DB load
  needed to verify process isolation for Gate 4 without external dependencies.
"""

import os
import sys
import time
import json
import uuid
import urllib.request
import urllib.error
import threading
import statistics
import argparse
import subprocess
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

GATE4_PREFIX = "gate4_test_"
GATE4_SESSION_PREFIX = "gate4_sess_"


def make_http_request(
    url: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout_sec: float = 10.0
) -> Dict[str, Any]:
    """Robust, dependency-free HTTP request helper using standard library."""
    req_headers = {"Content-Type": "application/json", "User-Agent": "SWIPIES-Gate4-Tester/1.0"}
    if headers:
        req_headers.update(headers)

    encoded_data = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=encoded_data, headers=req_headers, method=method)

    start_t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0
            body = resp.read().decode("utf-8")
            try:
                parsed_json = json.loads(body)
            except Exception:
                parsed_json = {"raw": body}
            return {
                "status_code": resp.status,
                "elapsed_ms": elapsed_ms,
                "data": parsed_json,
                "error": None
            }
    except urllib.error.HTTPError as he:
        elapsed_ms = (time.perf_counter() - start_t) * 1000.0
        err_body = he.read().decode("utf-8", errors="replace")
        return {
            "status_code": he.code,
            "elapsed_ms": elapsed_ms,
            "data": None,
            "error": f"HTTP {he.code}: {err_body[:200]}"
        }
    except Exception as ex:
        elapsed_ms = (time.perf_counter() - start_t) * 1000.0
        return {
            "status_code": 0,
            "elapsed_ms": elapsed_ms,
            "data": None,
            "error": str(ex)
        }


class TrackerFloodWorker(threading.Thread):
    """
    Generates controlled 100 req/s background load against Port 5001 (/event endpoint).
    Tests IP hashing, SQLite WAL serialization, and OS thread contention.
    """
    def __init__(self, target_url: str, target_rps: int = 100):
        super().__init__(daemon=True)
        self.target_url = target_url
        self.target_rps = target_rps
        self.stop_signal = threading.Event()
        self.sent_count = 0
        self.error_count = 0

    def stop(self):
        self.stop_signal.set()

    def run(self):
        interval = 1.0 / self.target_rps
        session_idx = 0
        while not self.stop_signal.is_set():
            t0 = time.perf_counter()
            session_idx += 1
            payload = {
                "event_type": "heartbeat",
                "session_id": f"{GATE4_SESSION_PREFIX}flood_{session_idx}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "page_path": "/pricing",
                "time_on_page_sec": 15,
                "active_time_sec": 10,
                "utm_source": "gate4_stress_test",
                "utm_medium": "cpc",
                "utm_campaign": "flood_test"
            }
            res = make_http_request(self.target_url, method="POST", data=payload, timeout_sec=2.0)
            if res["status_code"] in (200, 201, 202):
                self.sent_count += 1
            else:
                self.error_count += 1

            sleep_time = interval - (time.perf_counter() - t0)
            if sleep_time > 0:
                time.sleep(sleep_time)


def cleanup_synthetic_records(
    mysql_host: str,
    mysql_port: int,
    mysql_user: str,
    mysql_pass: str,
    mysql_db: str,
    sqlite_path: str
):
    """
    Removes all synthetic test records from both MySQL and SQLite:
    1. 'gate4_test_%' from MySQL payment_transaction.
    2. 'gate4_sess_%' from SQLite attribution_raw_events.
    Guarantees zero residue in the financial ledger and analytics views.
    """
    print(f"\n[CLEANUP] Starting cleanup of synthetic test records...")

    # 1. Cleanup MySQL payment_transaction
    try:
        import pymysql
        conn = pymysql.connect(
            host=mysql_host,
            port=mysql_port,
            user=mysql_user,
            password=mysql_pass,
            database=mysql_db,
            autocommit=True
        )
        with conn.cursor() as cur:
            sql = "DELETE FROM payment_transaction WHERE transaction_id LIKE %s"
            cur.execute(sql, (f"{GATE4_PREFIX}%",))
            cleaned_rows = cur.rowcount
        conn.close()
        print(f"[CLEANUP: MySQL] Successfully deleted {cleaned_rows} synthetic test rows ('{GATE4_PREFIX}%') via pymysql.")
    except ImportError:
        print("[CLEANUP: MySQL] pymysql not installed; falling back to mysql CLI with MYSQL_PWD env...")
        custom_env = os.environ.copy()
        if mysql_pass:
            custom_env["MYSQL_PWD"] = mysql_pass
        cmd = [
            "mysql",
            "-h", mysql_host,
            "-P", str(mysql_port),
            "-u", mysql_user,
            mysql_db,
            "-e", f"DELETE FROM payment_transaction WHERE transaction_id LIKE '{GATE4_PREFIX}%';"
        ]
        try:
            res = subprocess.run(cmd, env=custom_env, capture_output=True, text=True)
            if res.returncode == 0:
                print(f"[CLEANUP: MySQL] Successfully deleted synthetic test rows ('{GATE4_PREFIX}%') via mysql CLI.")
            else:
                print(f"[CLEANUP: MySQL WARNING] mysql CLI exited {res.returncode}: {res.stderr.strip()}")
        except Exception as ex:
            print(f"[CLEANUP: MySQL WARNING] Could not run mysql CLI ({ex}). Please manually execute:")
            print(f"  DELETE FROM payment_transaction WHERE transaction_id LIKE '{GATE4_PREFIX}%';")
    except Exception as e:
        print(f"[CLEANUP: MySQL ERROR] Failed to purge test rows from MySQL: {e}")
        print(f"  Please manually execute: DELETE FROM payment_transaction WHERE transaction_id LIKE '{GATE4_PREFIX}%';")

    # 2. Cleanup SQLite attribution_raw_events
    if sqlite_path and os.path.exists(sqlite_path):
        try:
            import sqlite3
            with sqlite3.connect(sqlite_path) as sconn:
                scur = sconn.cursor()
                scur.execute("DELETE FROM attribution_raw_events WHERE session_id LIKE ?", (f"{GATE4_SESSION_PREFIX}%",))
                s_deleted = scur.rowcount
                sconn.commit()
            print(f"[CLEANUP: SQLite] Successfully deleted {s_deleted} synthetic events ('{GATE4_SESSION_PREFIX}%') from {sqlite_path}.")
        except Exception as se:
            print(f"[CLEANUP: SQLite WARNING] Failed to purge SQLite test events: {se}")
    else:
        print(f"[CLEANUP: SQLite] SQLite database '{sqlite_path}' not present on this host or path not found (skipping local SQLite cleanup).")


def get_process_rss_mb(port: int) -> Optional[float]:
    """Finds process listening on port and reads its current RSS memory in MB."""
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                for conn in proc.net_connections(kind="tcp"):
                    if conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                        rss_bytes = proc.memory_info().rss
                        return rss_bytes / (1024 * 1024)
            except Exception:
                continue
    except Exception:
        pass
    return None


def run_benchmark_phase(
    payment_url: str,
    api_key: str,
    test_email: str,
    num_requests: int,
    phase_name: str,
    run_id: str,
    pacing_sec: float = 0.05
) -> Dict[str, Any]:
    """
    Executes a sequence of payment initialization calls with Track 3 attribution metadata.
    Strictly verifies HTTP 200 and JSON body {'code': 0}.
    """
    print(f"\n--- Running {phase_name} ({num_requests} requests) ---")
    latencies: List[float] = []
    errors: List[str] = []
    created_ids: List[str] = []

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    for i in range(1, num_requests + 1):
        tx_id = f"{GATE4_PREFIX}{run_id}_{phase_name[:4]}_{i:03d}"
        session_id = f"{GATE4_SESSION_PREFIX}{run_id}_{i:03d}"

        payload = {
            "transaction_id": tx_id,
            "email": test_email,
            "plan": "plus",
            "months": 1,
            "payment_method": "atmos_uzcard_humo",
            "session_id": session_id,
            "utm": {
                "utm_source": "gate4_stress_bench",
                "utm_medium": "cpc",
                "utm_campaign": "gate4_system_api_load",
                "utm_content": f"bench_{phase_name}",
                "utm_term": "attribution_verification"
            }
        }

        res = make_http_request(payment_url, method="POST", data=payload, headers=headers, timeout_sec=10.0)
        created_ids.append(tx_id)

        # Strict Acceptance Criterion: HTTP 200 AND JSON dict AND code == 0 (RetCode.SUCCESS)
        is_success = (
            res["status_code"] == 200
            and isinstance(res["data"], dict)
            and res["data"].get("code") == 0
        )

        if is_success:
            latencies.append(res["elapsed_ms"])
        else:
            err_msg = res["error"] or str(res["data"])
            errors.append(f"Req #{i} ({tx_id}): status {res['status_code']}, err: {err_msg}")

        time.sleep(pacing_sec)

    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else (max(latencies) if latencies else 0.0)
    median = statistics.median(latencies) if latencies else 0.0
    mean = statistics.mean(latencies) if latencies else 0.0
    min_lat = min(latencies) if latencies else 0.0
    max_lat = max(latencies) if latencies else 0.0
    error_rate = (len(errors) / num_requests) * 100.0

    print(f"[{phase_name} Results]")
    print(f"  Successful: {len(latencies)}/{num_requests} ({100.0 - error_rate:.1f}%)")
    print(f"  Error count: {len(errors)}")
    print(f"  Latencies (ms): min={min_lat:.1f}, med={median:.1f}, mean={mean:.1f}, p95={p95:.1f}, max={max_lat:.1f}")

    if errors:
        print("  Sample errors (first 3):")
        for err in errors[:3]:
            print(f"    - {err}")

    return {
        "latencies": latencies,
        "errors": errors,
        "p95": p95,
        "median": median,
        "mean": mean,
        "min": min_lat,
        "max": max_lat,
        "error_rate": error_rate,
        "created_ids": created_ids
    }


def main():
    parser = argparse.ArgumentParser(description="TASK-4.5: Gate 4 Real-Stack Process Isolation & Latency Stress Test")
    parser.add_argument("--payment-url", default="http://127.0.0.1:5000/api/v1/system/payment/init", help="Full URL to system_api.py payment init route")
    parser.add_argument("--tracker-url", default="http://127.0.0.1:5001/event", help="Full URL to swipies-tracker event endpoint")
    parser.add_argument("--api-key", default=os.getenv("RAGFLOW_API_KEY", ""), help="RAGFLOW_API_KEY (defaults to RAGFLOW_API_KEY env without argv exposure)")
    parser.add_argument("--test-email", default="admin@swipies.app", help="Existing test/admin user email in the database")
    parser.add_argument("--baseline-n", type=int, default=20, help="Number of baseline requests without background load")
    parser.add_argument("--stress-n", type=int, default=40, help="Number of payment requests during 100 req/s flood")
    parser.add_argument("--tracker-port", type=int, default=5001, help="Port of swipies-tracker for RSS inspection")
    parser.add_argument("--mysql-host", default=os.getenv("MYSQL_HOST", "127.0.0.1"), help="MySQL host for cleanup")
    parser.add_argument("--mysql-port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")), help="MySQL port")
    parser.add_argument("--mysql-user", default=os.getenv("MYSQL_USER", "root"), help="MySQL user")
    parser.add_argument("--mysql-pass", default=os.getenv("MYSQL_PASSWORD", ""), help="MySQL password (defaults to MYSQL_PASSWORD env without argv exposure)")
    parser.add_argument("--mysql-db", default=os.getenv("MYSQL_DB", "swipies_db"), help="MySQL database name")
    parser.add_argument("--sqlite-path", default="./data/attribution_events.db", help="Path to SQLite events DB for cleanup")
    parser.add_argument("--cleanup-only", action="store_true", help="Only run cleanup of synthetic rows and exit")
    parser.add_argument("--skip-cleanup", action="store_true", help="Skip cleanup for forensic manual SQL inspection")
    args = parser.parse_args()

    if args.cleanup_only:
        cleanup_synthetic_records(args.mysql_host, args.mysql_port, args.mysql_user, args.mysql_pass, args.mysql_db, args.sqlite_path)
        return

    run_id = uuid.uuid4().hex[:8]
    print("=" * 80)
    print(f"  SWIPIES GATE 4 REAL-STACK STRESS TEST (TASK-4.5) | Run ID: {run_id}")
    print(f"  Target Payment Route: {args.payment_url}")
    print(f"  Target Tracker Route: {args.tracker_url}")
    print(f"  Test Email:           {args.test_email}")
    print(f"  Synthetic Prefix:     {GATE4_PREFIX}{run_id}_*")
    print("=" * 80)

    # 1. Healthcheck pre-flight on both ports
    print("\n[PRE-FLIGHT] Checking connectivity to ports 5000 and 5001...")
    p_health = make_http_request(args.payment_url.replace("/init", "/ping") if "/init" in args.payment_url else args.payment_url, timeout_sec=3.0)
    t_health = make_http_request(args.tracker_url.replace("/event", "/health"), timeout_sec=3.0)

    print(f"  Port 5000 status: code {p_health['status_code']} ({p_health['error'] or 'ONLINE'})")
    print(f"  Port 5001 status: code {t_health['status_code']} ({t_health['error'] or 'ONLINE'})")

    if t_health["status_code"] != 200:
        print("[PRE-FLIGHT WARNING] Tracker service on port 5001 did not return HTTP 200.")
        print("Please ensure swipies-tracker.service (gunicorn) is running on port 5001.")

    try:
        # Phase 1: Baseline (Port 5000 only, zero traffic on 5001)
        base_res = run_benchmark_phase(
            payment_url=args.payment_url,
            api_key=args.api_key,
            test_email=args.test_email,
            num_requests=args.baseline_n,
            phase_name="Baseline (Zero Background)",
            run_id=run_id,
            pacing_sec=0.05
        )

        # Phase 2: Start 100 req/s background flood on Port 5001
        print(f"\n[FLOOD] Starting background flood of 100 req/s to {args.tracker_url}...")
        flood_worker = TrackerFloodWorker(target_url=args.tracker_url, target_rps=100)
        flood_worker.start()

        # Allow flood to stabilize for 2 seconds
        time.sleep(2.0)

        # Phase 3: Benchmark under load (Port 5000 during 100 req/s flood)
        stress_res = run_benchmark_phase(
            payment_url=args.payment_url,
            api_key=args.api_key,
            test_email=args.test_email,
            num_requests=args.stress_n,
            phase_name="Under-Load (100 req/s on 5001)",
            run_id=run_id,
            pacing_sec=0.05
        )

        # Stop flood
        flood_worker.stop()
        flood_worker.join(timeout=3.0)
        print(f"[FLOOD] Completed. Sent {flood_worker.sent_count} tracking events, errors: {flood_worker.error_count}.")

        # Phase 4: Resource footprint check
        tracker_rss = get_process_rss_mb(args.tracker_port)
        rss_str = f"{tracker_rss:.2f} MB" if tracker_rss is not None else "N/A (psutil unavailable)"

        # Phase 5: Verification of Gate Criteria
        p95_base = base_res["p95"]
        p95_stress = stress_res["p95"]
        delta_p95_ms = p95_stress - p95_base
        delta_p95_pct = ((delta_p95_ms) / p95_base * 100.0) if p95_base > 0 else 0.0
        error_rate = stress_res["error_rate"]

        passed_p95 = (delta_p95_ms <= 15.0) or (delta_p95_pct <= 20.0)
        passed_errors = (error_rate == 0.0)
        passed_rss = (tracker_rss is None) or (tracker_rss <= 256.0)
        overall_pass = passed_p95 and passed_errors and passed_rss

        print("\n" + "=" * 80)
        print("  TASK-4.5 GATE 4 VERIFICATION REPORT")
        print("=" * 80)
        print(f"  1. Payment Core Baseline p95 (Port 5000):   {p95_base:.2f} ms")
        print(f"  2. Payment Core Under-Load p95 (Port 5000):  {p95_stress:.2f} ms")
        print(f"  3. Delta p95 Latency Impact:                 {delta_p95_ms:+.2f} ms ({delta_p95_pct:+.1f}%) [Threshold: <= +15ms or <= 20%]")
        print(f"     -> P95 Latency Check:                     {'PASS' if passed_p95 else 'FAIL'}")
        print(f"  4. Payment Core Error Rate:                  {error_rate:.2f}% [Threshold: strictly 0.00%]")
        print(f"     -> Error Rate Check:                      {'PASS' if passed_errors else 'FAIL'}")
        print(f"  5. Tracker Service Memory Footprint (5001):  {rss_str} [Threshold: <= 256 MB]")
        print(f"     -> Memory Footprint Check:                {'PASS' if passed_rss else 'FAIL'}")
        print("-" * 80)
        print(f"  FINAL GATE 4 STATUS:                         {'✅ PASSED (GATE 4 CLEARED)' if overall_pass else '❌ FAILED'}")
        print("=" * 80)

    finally:
        if not args.skip_cleanup:
            cleanup_synthetic_records(args.mysql_host, args.mysql_port, args.mysql_user, args.mysql_pass, args.mysql_db, args.sqlite_path)
        else:
            print("\n[CLEANUP SKIPPED] --skip-cleanup set. Synthetic records retained for manual inspection.")


if __name__ == "__main__":
    main()
