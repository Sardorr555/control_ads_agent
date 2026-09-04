"""
Gate 2 Verification: Process & Performance Isolation Stress Test.
Validates:
1. Synthetic 100 req/s ingestion load on tracking service (port 5001).
2. Numerical threshold 1: p95 latency degradation on payment core (port 5000) <= +15ms (or <= 20%).
3. Numerical threshold 2: Payment core error rate is strictly 0.00%.
4. Numerical threshold 3: RSS memory consumption <= 200 MB.
"""
import time
import threading
import statistics
import socket
import pytest
import psutil
import httpx
from http.server import HTTPServer, BaseHTTPRequestHandler
from werkzeug.serving import make_server

from src.tracker_service import create_app


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class MockPaymentHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Simulate ~20-25ms payment processing & Atmos verification latency
        time.sleep(0.022)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "PAID", "is_provisioned": true}')

    def log_message(self, format, *args):
        pass  # Suppress console noise during stress test


@pytest.fixture(scope="module")
def servers(tmp_path_factory):
    # Setup temporary database for tracker
    temp_dir = tmp_path_factory.mktemp("stress_db")
    db_path = str(temp_dir / "stress_events.db")

    pay_port = find_free_port()
    track_port = find_free_port()

    # 1. Start Payment Mock Server (Simulating port 5000)
    pay_server = HTTPServer(('127.0.0.1', pay_port), MockPaymentHandler)
    pay_thread = threading.Thread(target=pay_server.serve_forever, daemon=True)
    pay_thread.start()

    # 2. Start Tracker Ingestion Service (Simulating port 5001)
    flask_app = create_app(db_path=db_path, base_salt="stress_test_master_salt_min_32_chars_ok")
    track_server = make_server('127.0.0.1', track_port, flask_app)
    track_thread = threading.Thread(target=track_server.serve_forever, daemon=True)
    track_thread.start()

    # Give servers a moment to bind
    time.sleep(0.2)

    yield {
        "pay_url": f"http://127.0.0.1:{pay_port}/api/pay/finalize",
        "track_url": f"http://127.0.0.1:{track_port}/api/v1/track/event",
        "db_path": db_path,
        "flask_app": flask_app,
    }

    track_server.shutdown()
    pay_server.shutdown()


def test_process_isolation_under_stress(servers):
    pay_url = servers["pay_url"]
    track_url = servers["track_url"]

    client = httpx.Client(timeout=10.0)

    # --------------------------------------------------------------------------
    # Phase 1: Baseline Measurement on Payment Core (No Tracking Load)
    # --------------------------------------------------------------------------
    baseline_latencies = []
    for _ in range(50):
        t0 = time.perf_counter()
        resp = client.post(pay_url, json={"transaction_id": "tx_base", "email": "test@swipies.uz"})
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert resp.status_code == 200
        baseline_latencies.append(elapsed_ms)

    p95_baseline = statistics.quantiles(baseline_latencies, n=20)[18]  # 95th percentile
    print(f"\n[Isolation Test] Baseline Payment p95 Latency: {p95_baseline:.2f} ms")

    # --------------------------------------------------------------------------
    # Phase 2: Stress Load Generation on Port 5001 (~100 req/s for 3 seconds)
    # --------------------------------------------------------------------------
    stop_event = threading.Event()
    ingested_events_count = [0]
    ingestion_errors = [0]

    def tracker_worker(worker_id):
        worker_client = httpx.Client(timeout=3.0)
        headers = {"X-Forwarded-For": f"84.54.70.{worker_id % 250 + 1}"}
        counter = 0
        
        while not stop_event.is_set():
            counter += 1
            sample_event = {
                "session_id": f"swp_stress_{worker_id}_{counter}_{int(time.time()*1000)}",
                "page_path": "/pricing",
                "time_on_page_sec": 15,
                "utm_source": "meta",
                "utm_medium": "cpc",
                "utm_campaign": "stress_load_campaign",
                "event_type": "heartbeat"
            }
            try:
                r = worker_client.post(track_url, json=sample_event, headers=headers)
                if r.status_code == 200:
                    ingested_events_count[0] += 1
                else:
                    ingestion_errors[0] += 1
            except Exception:
                ingestion_errors[0] += 1
            time.sleep(0.01)

    # Launch 10 parallel workers each doing ~10 req/s -> ~100 req/s total
    workers = []
    for i in range(10):
        w = threading.Thread(target=tracker_worker, args=(i,))
        w.start()
        workers.append(w)

    time.sleep(0.2)  # Let stress load ramp up

    # --------------------------------------------------------------------------
    # Phase 3: Concurrent Payment Execution under Stressed Ingestion
    # --------------------------------------------------------------------------
    stressed_latencies = []
    payment_errors = 0
    payment_total = 60

    for i in range(payment_total):
        t0 = time.perf_counter()
        try:
            resp = client.post(pay_url, json={"transaction_id": f"tx_stress_{i}", "email": "cfo@bank.uz"})
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if resp.status_code == 200:
                stressed_latencies.append(elapsed_ms)
            else:
                payment_errors += 1
        except Exception:
            payment_errors += 1
        time.sleep(0.03)

    # Stop tracker workers
    stop_event.set()
    for w in workers:
        w.join()

    # --------------------------------------------------------------------------
    # Phase 4: Metrics Calculation & Explicit Numerical Gate 2 Assertions
    # --------------------------------------------------------------------------
    p95_stressed = statistics.quantiles(stressed_latencies, n=20)[18]
    delta_ms = p95_stressed - p95_baseline
    pct_increase = (delta_ms / p95_baseline) * 100.0 if p95_baseline > 0 else 0.0

    # Memory RSS check
    current_process = psutil.Process()
    rss_mb = current_process.memory_info().rss / (1024.0 * 1024.0)

    print(f"[Isolation Test] Stressed Payment p95 Latency: {p95_stressed:.2f} ms")
    print(f"[Isolation Test] Latency Delta: {delta_ms:+.2f} ms ({pct_increase:+.1f}%)")
    print(f"[Isolation Test] Total Ingested Events: {ingested_events_count[0]} (errors: {ingestion_errors[0]})")
    print(f"[Isolation Test] Process Memory RSS: {rss_mb:.2f} MB")

    # Gate 2 Assertion 1: Latency degradation must be <= +15 ms OR <= 20%
    assert delta_ms <= 15.0 or pct_increase <= 20.0, (
        f"GATE 2 VIOLATION: Latency degradation too high: delta={delta_ms:+.2f} ms, "
        f"increase={pct_increase:.1f}% (limit: <= +15 ms or <= 20%)"
    )

    # Gate 2 Assertion 2: Payment core error rate must be strictly 0.00%
    error_rate = (payment_errors / payment_total) * 100.0
    assert error_rate == 0.00, f"GATE 2 VIOLATION: Payment error rate was {error_rate:.2f}%, must be strictly 0.00%"

    # Gate 2 Assertion 3: Process RSS memory must be <= 200 MB
    assert rss_mb <= 200.0, f"GATE 2 VIOLATION: Process RSS {rss_mb:.2f} MB exceeded 200 MB limit"

    # Gate 2 Assertion 4: Tracking service successfully ingested traffic without crashes
    assert ingested_events_count[0] >= 100, f"Ingestion throughput too low: {ingested_events_count[0]} events"
