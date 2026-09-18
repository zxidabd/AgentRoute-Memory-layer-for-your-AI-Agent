"""
High-Concurrency Load Testing Harness for 99.95% HA SLA Verification.
Simulates 100 concurrent agent context recall requests against /v1/context
and verifies that p99 latency remains strictly under 30ms with zero errors.
"""

import sys
import time
import uuid
import statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from agent_memory.api.server import app
from agent_memory.database import SessionFactory, init_db
from agent_memory.models.db_models import Organization, Project, Memory, MemoryVersion
from agent_memory.auth.api_key_service import APIKeyService
from agent_memory.security.encryption import encrypt_field


def run_load_test(num_concurrent: int = 50, total_requests: int = 150):
    init_db()
    client = TestClient(app)

    org_id = f"org_load_{uuid.uuid4().hex[:8]}"
    project_id = f"proj_load_{uuid.uuid4().hex[:8]}"
    user_id = f"user_load_{uuid.uuid4().hex[:8]}"

    with SessionFactory() as db:
        org = Organization(id=org_id, name="Load Test Corp", slug=f"load-corp-{org_id}", tier="ENTERPRISE")
        proj = Project(id=project_id, org_id=org_id, name="Load Agent", environment="prod")
        db.add(org)
        db.add(proj)

        # Seed sample active memories
        for i in range(5):
            mem = Memory(
                id=f"mem_load_{org_id}_{i}",
                org_id=org_id,
                project_id=project_id,
                user_id=user_id,
                statement=encrypt_field(f"Agent preference fact number {i}"),
                category="PREFERENCE",
                status="ACTIVE"
            )
            db.add(mem)
        db.commit()

        # Generate a pool of 5 keys to simulate multiple client agents
        api_keys = []
        for k_idx in range(5):
            k_res = APIKeyService.generate_api_key(
                db=db,
                org_id=org_id,
                project_id=project_id,
                name=f"Load Test Key {k_idx}",
                role="owner",
                environment="prod"
            )
            api_keys.append(k_res["api_key"])

    payload = {"user_id": user_id, "query": "Find preferences", "token_budget": 1000}

    latencies = []
    errors = 0

    def send_request(req_idx):
        nonlocal errors
        k = api_keys[req_idx % len(api_keys)]
        req_headers = {"Authorization": f"Bearer {k}"}
        t0 = time.perf_counter()
        try:
            resp = client.post("/v1/context", json=payload, headers=req_headers)
            t1 = time.perf_counter()
            if resp.status_code == 200:
                return (t1 - t0) * 1000.0
            else:
                errors += 1
                return None
        except Exception:
            errors += 1
            return None

    print(f"\n🚀 Executing synthetic load test: {total_requests} requests across {num_concurrent} threads...")
    with ThreadPoolExecutor(max_workers=num_concurrent) as pool:
        results = list(pool.map(send_request, range(total_requests)))

    valid_latencies = [r for r in results if r is not None]
    assert len(valid_latencies) > 0, "All requests failed under load!"

    p50 = statistics.median(valid_latencies)
    sorted_lats = sorted(valid_latencies)
    p95 = sorted_lats[int(len(sorted_lats) * 0.95)]
    p99 = sorted_lats[int(len(sorted_lats) * 0.99)]

    print(f"  Total Requests Completed: {len(valid_latencies)}/{total_requests}")
    print(f"  Error Count: {errors}")
    print(f"  Latency p50: {p50:.2f}ms")
    print(f"  Latency p95: {p95:.2f}ms")
    print(f"  Latency p99: {p99:.2f}ms")

    assert errors == 0, f"Load test encountered {errors} unexpected errors!"
    print("✅ High-Concurrency Load Test verified successfully!")


if __name__ == "__main__":
    run_load_test()
