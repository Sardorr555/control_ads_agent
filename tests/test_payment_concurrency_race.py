"""
Track 3 Concurrency Race & Idempotency Test.
Replicates the Track 2 test_phase2_concurrency_race.py methodology:
- 5 concurrent threads attempting to finalize and/or create_pending the exact same transaction ID simultaneously.
- Advisory lock serialization (simulating MySQL GET_LOCK / RELEASE_LOCK).
- Simulated 30ms network latency of Atmos gateway verification.
- Proves:
  1. Exactly ONE thread provisions the tenant and marks the transaction as PAID.
  2. Remaining 4 threads detect already_provisioned and exit cleanly.
  3. Tenant credits are incremented EXACTLY ONCE (no double crediting).
  4. Exactly ONE PaymentTransaction record exists in the DB.
  5. Attribution fields (session_id, utm_*) are cleanly preserved and never lost or corrupted.
  6. Race conditions with NULL / missing UTMs (direct visits) execute without error.
"""
import os
import sys
import unittest
import threading
import time
import re
from datetime import datetime
from peewee import SqliteDatabase, CharField, IntegerField, BigIntegerField, BooleanField, DateTimeField, TextField, JSONField

for _candidate_path in ["/home/ubuntu/swipies__ai_", "D:/ragflow/swipies_25/ragflow"]:
    if os.path.isdir(_candidate_path) and _candidate_path not in sys.path:
        sys.path.insert(0, _candidate_path)

import types
from importlib.machinery import ModuleSpec

class AutoMockClass:
    def __init__(self, *args, **kwargs):
        pass
    def __getattr__(self, name):
        return name

class AutoMockMeta(type):
    def __getattr__(cls, name):
        return name

class AutoMockModule(types.ModuleType):
    def __getattr__(self, name):
        cls = AutoMockMeta(name, (AutoMockClass,), {})
        setattr(self, name, cls)
        return cls

class AutoModuleFinder:
    @classmethod
    def find_spec(cls, fullname, path, target=None):
        for prefix in ['infinity', 'pyobvector', 'opensearchpy', 'azure', 'qdrant_client', 'pymilvus', 'tidb_vector', 'minio', 'boto3', 'botocore', 'opendal', 'valkey', 'quart_schema', 'quart_cors', 'quart_auth', 'langfuse']:
            if fullname == prefix or fullname.startswith(prefix + '.'):
                return ModuleSpec(fullname, cls)
        return None

    @classmethod
    def create_module(cls, spec):
        mod = AutoMockModule(spec.name)
        mod.__path__ = []
        mod.__version__ = (8, 0, 0)
        return mod

    @classmethod
    def exec_module(cls, module):
        pass

sys.meta_path.insert(0, AutoModuleFinder)

qa_mod = types.ModuleType('quart_auth')
class AuthUser:
    pass
qa_mod.AuthUser = AuthUser
qa_mod.Unauthorized = type('Unauthorized', (Exception,), {})
sys.modules['quart_auth'] = qa_mod

from sqlalchemy.types import TypeEngine
class MockARRAY(TypeEngine):
    def __init__(self, *args, **kwargs):
        pass
class MockVECTOR(TypeEngine):
    def __init__(self, *args, **kwargs):
        pass

import pyobvector
pyobvector.ARRAY = MockARRAY
pyobvector.VECTOR = MockVECTOR

rag_tok_mod = types.ModuleType('rag.nlp.rag_tokenizer')
rag_tok_mod.RagTokenizer = type('RagTokenizer', (), {})
rag_tok_mod.is_english = lambda *a, **k: True
rag_tok_mod.tokenize = lambda *a, **k: []
rag_tok_mod.fine_grained_tokenize = lambda *a, **k: []
rag_tok_mod.tag = lambda *a, **k: []
rag_tok_mod.freq = lambda *a, **k: 0
rag_tok_mod.tradi2simp = lambda *a, **k: ""
rag_tok_mod.strQ2B = lambda *a, **k: ""
sys.modules['rag.nlp.rag_tokenizer'] = rag_tok_mod
sys.modules['rag.nlp'] = types.ModuleType('rag.nlp')
sys.modules['rag.nlp'].rag_tokenizer = rag_tok_mod
sys.modules['rag.nlp'].is_english = rag_tok_mod.is_english
sys.modules['rag.nlp'].search = types.ModuleType('rag.nlp.search')
sys.modules['rag.nlp'].search = sys.modules['rag.nlp'].search

TEST_DB_FILE = "test_track3_concurrency.db"
if os.path.exists(TEST_DB_FILE):
    try:
        os.remove(TEST_DB_FILE)
    except Exception:
        pass

test_db = SqliteDatabase(TEST_DB_FILE, timeout=30)

import api.db.db_models as db_models
db_models.DB = test_db
import api.db.services.common_service as cs
cs.DB = test_db

from api.db.db_models import User, Tenant, PaymentTransaction

User._meta.database = test_db
Tenant._meta.database = test_db
PaymentTransaction._meta.database = test_db
test_db.bind([User, Tenant, PaymentTransaction])

from api.db.services.payment_transaction_service import PaymentTransactionService
from api.db.services.user_service import UserService, TenantService

def sanitize_attribution(raw_session_id, raw_utm):
    raw_utm = raw_utm or {}
    clean_session_id = re.sub(r'[^a-zA-Z0-9_\-]', '', str(raw_session_id))[:64] if raw_session_id else None
    clean_utm_source = re.sub(r'[^a-zA-Z0-9_\-\.]', '', str(raw_utm.get('utm_source', '')))[:64] or None
    clean_utm_medium = re.sub(r'[^a-zA-Z0-9_\-\.]', '', str(raw_utm.get('utm_medium', '')))[:64] or None
    clean_utm_campaign = re.sub(r'[^a-zA-Z0-9_\-\.]', '', str(raw_utm.get('utm_campaign', '')))[:128] or None
    clean_utm_content = re.sub(r'[^a-zA-Z0-9_\-\.]', '', str(raw_utm.get('utm_content', '')))[:128] or None
    clean_utm_term = re.sub(r'[^a-zA-Z0-9_\-\.]', '', str(raw_utm.get('utm_term', '')))[:128] or None
    return {
        "session_id": clean_session_id,
        "utm_source": clean_utm_source,
        "utm_medium": clean_utm_medium,
        "utm_campaign": clean_utm_campaign,
        "utm_content": clean_utm_content,
        "utm_term": clean_utm_term,
    }

DB_MUTEX = threading.Lock()

class MockAdvisoryLock:
    _locks = {}
    _global_lock = threading.Lock()

    def __init__(self, name, timeout=10):
        self.name = name
        self.timeout = timeout
        with self._global_lock:
            if name not in self._locks:
                self._locks[name] = threading.Lock()
            self._lock = self._locks[name]

    def acquire(self):
        return self._lock.acquire(timeout=self.timeout)

    def release(self):
        try:
            self._lock.release()
        except RuntimeError:
            pass


def execute_simulated_finalize_with_attribution(
    tx_id, user_id, email, plan, months, gateway_paid_uzs,
    attribution_data, results_list, lock_factory
):
    sanitized = sanitize_attribution(attribution_data.get("session_id"), attribution_data.get("utm"))

    lock = lock_factory(f"swipies_pay_{tx_id}", timeout=5)
    acquired = lock.acquire()
    if not acquired:
        results_list.append({"thread": threading.current_thread().name, "status": "LOCK_TIMEOUT"})
        return

    try:
        with DB_MUTEX:
            existing = PaymentTransactionService.get_by_tx_id(tx_id)
            if existing and existing.status == "PAID" and existing.is_provisioned:
                results_list.append({
                    "thread": threading.current_thread().name,
                    "status": "ALREADY_PROVISIONED",
                    "provisioned": False,
                })
                return

            if not existing:
                PaymentTransactionService.create_pending(
                    transaction_id=tx_id,
                    user_id=user_id,
                    tenant_id=user_id,
                    account_email=email,
                    plan_type=plan,
                    duration_months=months,
                    expected_amount_uzs=gateway_paid_uzs,
                    session_id=sanitized["session_id"],
                    utm_source=sanitized["utm_source"],
                    utm_medium=sanitized["utm_medium"],
                    utm_campaign=sanitized["utm_campaign"],
                    utm_content=sanitized["utm_content"],
                    utm_term=sanitized["utm_term"],
                )

        time.sleep(0.03)

        with DB_MUTEX:
            existing = PaymentTransactionService.get_by_tx_id(tx_id)
            if existing and existing.status == "PAID" and existing.is_provisioned:
                results_list.append({
                    "thread": threading.current_thread().name,
                    "status": "ALREADY_PROVISIONED",
                    "provisioned": False,
                })
                return

            tenant = Tenant.get_by_id(user_id)
            new_credit = (tenant.credit or 0) + (10000 * months)
            Tenant.update(
                plan_type=plan,
                credit=new_credit,
            ).where(Tenant.id == user_id).execute()

            PaymentTransactionService.mark_paid(
                transaction_id=tx_id,
                paid_amount_uzs=gateway_paid_uzs,
                audit_note="Verified via Track 3 Concurrency Test",
            )

        results_list.append({
            "thread": threading.current_thread().name,
            "status": "FIRST_PROVISIONED",
            "provisioned": True,
        })
    finally:
        lock.release()


class TestTrack3ConcurrencyRace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_db.connect(reuse_if_open=True)
        test_db.create_tables([User, Tenant, PaymentTransaction], safe=True)

    @classmethod
    def tearDownClass(cls):
        test_db.drop_tables([User, Tenant, PaymentTransaction], safe=True)
        test_db.close()
        if os.path.exists(TEST_DB_FILE):
            try:
                os.remove(TEST_DB_FILE)
            except Exception:
                pass

    def setUp(self):
        with DB_MUTEX:
            PaymentTransaction.delete().execute()
            User.delete().execute()
            Tenant.delete().execute()

            self.user = User.create(id="u_race_t3", email="race_t3@test.com", nickname="RaceT3")
            self.tenant = Tenant.create(
                id="u_race_t3",
                name="RaceT3",
                plan_type="free",
                credit=1000,
                llm_id="d", embd_id="d", asr_id="d", img2txt_id="d", rerank_id="d", parser_ids="d"
            )

    def test_concurrent_finalization_with_attribution(self):
        tx_id = "tx_race_track3_meta"
        results = []
        threads = []

        meta_payload = {
            "session_id": "sess_race_abc_123",
            "utm": {
                "utm_source": "meta_instagram",
                "utm_medium": "story_cpc",
                "utm_campaign": "b2b_fintech_q3",
                "utm_content": "creative_video_01",
                "utm_term": "invoice_auto"
            }
        }

        for i in range(5):
            t = threading.Thread(
                target=execute_simulated_finalize_with_attribution,
                args=(tx_id, "u_race_t3", "race_t3@test.com", "pro", 1, 400000, meta_payload, results, MockAdvisoryLock),
                name=f"Worker-Attribution-{i+1}",
            )
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        first_provisions = [r for r in results if r["status"] == "FIRST_PROVISIONED"]
        already_provisions = [r for r in results if r["status"] == "ALREADY_PROVISIONED"]

        self.assertEqual(len(first_provisions), 1, f"Expected 1 FIRST_PROVISIONED, got: {results}")
        self.assertEqual(len(already_provisions), 4, f"Expected 4 ALREADY_PROVISIONED, got: {results}")

        with DB_MUTEX:
            updated_tenant = Tenant.get_by_id("u_race_t3")
            self.assertEqual(updated_tenant.plan_type, "pro")
            self.assertEqual(updated_tenant.credit, 11000)

            records = list(PaymentTransaction.select().where(PaymentTransaction.transaction_id == tx_id))
            self.assertEqual(len(records), 1)
            tx = records[0]
            self.assertEqual(tx.status, "PAID")
            self.assertEqual(tx.paid_amount_uzs, 400000)
            self.assertTrue(tx.is_provisioned)

            self.assertEqual(tx.session_id, "sess_race_abc_123")
            self.assertEqual(tx.utm_source, "meta_instagram")
            self.assertEqual(tx.utm_medium, "story_cpc")
            self.assertEqual(tx.utm_campaign, "b2b_fintech_q3")
            self.assertEqual(tx.utm_content, "creative_video_01")
            self.assertEqual(tx.utm_term, "invoice_auto")

    def test_concurrent_creation_null_attribution(self):
        tx_id = "tx_race_track3_direct"
        results = []
        threads = []

        direct_payload = {"session_id": None, "utm": {}}

        for i in range(5):
            t = threading.Thread(
                target=execute_simulated_finalize_with_attribution,
                args=(tx_id, "u_race_t3", "race_t3@test.com", "plus", 1, 199000, direct_payload, results, MockAdvisoryLock),
                name=f"Worker-Direct-{i+1}",
            )
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        first_provisions = [r for r in results if r["status"] == "FIRST_PROVISIONED"]
        already_provisions = [r for r in results if r["status"] == "ALREADY_PROVISIONED"]

        self.assertEqual(len(first_provisions), 1)
        self.assertEqual(len(already_provisions), 4)

        with DB_MUTEX:
            records = list(PaymentTransaction.select().where(PaymentTransaction.transaction_id == tx_id))
            self.assertEqual(len(records), 1)
            tx = records[0]
            self.assertEqual(tx.status, "PAID")
            self.assertIsNone(tx.session_id)
            self.assertIsNone(tx.utm_source)
            self.assertIsNone(tx.utm_campaign)


if __name__ == "__main__":
    unittest.main()
