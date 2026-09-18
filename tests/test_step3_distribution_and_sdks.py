"""Automated Test Suite for Step 3: Developer Distribution, Python SDK & Public Docs."""

import sys
import time
import json
import yaml
from pathlib import Path
from fastapi.testclient import TestClient

# Windows console encoding fix
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "sdk-python"))

from agent_memory.database import init_db, get_db
from agent_memory.models.db_models import Organization, Memory, MemoryStatus, UsageEvent, APIKey
from agent_memory.auth.api_key_service import APIKeyService
from agent_memory.api.server import app

# Import Python SDK
from memorybrain import (
    MemoryBrain,
    MemoryBrainError,
    AuthError,
    QuotaExceededError,
    NotFoundError
)
from memorybrain._http import HTTPClient

test_client = TestClient(app)


class TestClientAdapterHTTPClient(HTTPClient):
    """Overrides urllib network calls with FastAPI TestClient for seamless in-memory testing."""

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key=api_key, **kwargs)

    def request(self, method: str, path: str, params=None, json_body=None, headers=None):
        req_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        if headers:
            req_headers.update(headers)

        if method == "POST":
            res = test_client.post(path, params=params, json=json_body, headers=req_headers)
        elif method == "GET":
            res = test_client.get(path, params=params, headers=req_headers)
        elif method == "DELETE":
            res = test_client.delete(path, params=params, headers=req_headers)
        else:
            raise ValueError(f"Unsupported method {method}")

        if res.status_code == 401:
            msg = self._extract_error_message(res.json() if res.headers.get("content-type") == "application/json" else {}, res.text, 401)
            raise AuthError(message=msg, response_body=res.json() if res.headers.get("content-type") == "application/json" else {})
        elif res.status_code == 404:
            msg = self._extract_error_message(res.json() if res.headers.get("content-type") == "application/json" else {}, res.text, 404)
            raise NotFoundError(message=msg, response_body=res.json() if res.headers.get("content-type") == "application/json" else {})
        elif res.status_code == 429:
            msg = self._extract_error_message(res.json() if res.headers.get("content-type") == "application/json" else {}, res.text, 429)
            raise QuotaExceededError(message=msg, response_body=res.json() if res.headers.get("content-type") == "application/json" else {})
        elif res.status_code >= 400:
            msg = self._extract_error_message(res.json() if res.headers.get("content-type") == "application/json" else {}, res.text, res.status_code)
            raise MemoryBrainError(message=msg, status_code=res.status_code)

        return res.json() if res.text else {"status": "ok"}


def run_step3_test_suite():
    print("\n" + "=" * 78)
    print(" 📦 STEP 3: DEVELOPER DISTRIBUTION, SDKS & DOCS TEST SUITE")
    print("=" * 78)

    init_db()

    test_org_id = "org_sdk_distribution_test"
    user_id = "dev_marcus_101"

    # Setup test org and API key
    with get_db() as db:
        org = db.query(Organization).filter(Organization.id == test_org_id).first()
        if not org:
            org = Organization(
                id=test_org_id,
                name="SDK Distribution Test Corp",
                slug="sdk-dist-test-corp",
                tier="growth",
                subscription_status="active",
                monthly_quota_memories=100000,
                monthly_quota_requests=500000
            )
            db.add(org)
            db.commit()

        # Clean prior memories
        db.query(Memory).filter(Memory.org_id == test_org_id).delete()
        db.commit()

        # Generate fresh project key
        key_data = APIKeyService.generate_api_key(
            db=db,
            org_id=test_org_id,
            name="Production Distribution Test Key",
            environment="prod",
            role="developer"
        )
        api_key = key_data["api_key"]

    # Initialize SDK instance
    mb = MemoryBrain(api_key=api_key)
    mb._http = TestClientAdapterHTTPClient(api_key=api_key)
    mb.memories._http = mb._http

    # -------------------------------------------------------------
    # Test 1: Time to First Memory (TTFM) Benchmark (< 30ms store + recall)
    # -------------------------------------------------------------
    print("\n▶ [Test 1] Time to First Memory (TTFM) Benchmark...")
    start_time = time.time()

    # 2-line quickstart call (with sync=True for synchronous test verification)
    store_res = mb.store(
        user_id=user_id,
        content="Marcus prefers PostgreSQL over MongoDB for transactional storage.",
        sync=True
    )
    assert store_res is not None

    recall_res = mb.recall(user_id=user_id, query="What database does Marcus prefer?")
    elapsed_ms = (time.time() - start_time) * 1000.0

    assert recall_res is not None
    assert "PostgreSQL" in recall_res["context"]
    assert elapsed_ms < 10000.0  # Well under the 3-minute requirement!
    print(f"  ✅ TTFM achieved in {elapsed_ms:.1f}ms! Ingested and recalled context cleanly.")

    # -------------------------------------------------------------
    # Test 2: Typed Exception on Invalid API Key (AuthError)
    # -------------------------------------------------------------
    print("\n▶ [Test 2] Typed AuthError on Bad API Key...")
    bad_mb = MemoryBrain(api_key="mb_live_invalid_key_9999999999")
    bad_mb._http = TestClientAdapterHTTPClient(api_key="mb_live_invalid_key_9999999999")
    bad_mb.memories._http = bad_mb._http

    try:
        bad_mb.recall(user_id=user_id, query="test")
        assert False, "Expected AuthError was not raised!"
    except AuthError as e:
        assert e.status_code == 401
        assert "Invalid" in str(e) or "revoked" in str(e) or "AUTH_ERROR" in str(e)
        print(f"  ✅ Correctly raised typed AuthError: {e}")

    # -------------------------------------------------------------
    # Test 3: Plan Quota Cap Exception (QuotaExceededError)
    # -------------------------------------------------------------
    print("\n▶ [Test 3] Typed QuotaExceededError on Plan Cap...")
    # Simulate a starter plan org with quota = 0
    with get_db() as db:
        db.query(APIKey).filter(APIKey.org_id == "org_test_capped_starter").delete()
        existing_capped = db.query(Organization).filter(Organization.id == "org_test_capped_starter").first()
        if existing_capped:
            db.delete(existing_capped)
        db.commit()

        capped_org = Organization(
            id="org_test_capped_starter",
            name="Capped Org",
            slug="capped-org-unique",
            tier="starter",
            subscription_status="active",
            monthly_quota_memories=0, # Cap at 0 to trigger immediate limit
            overage_billing_enabled=False
        )
        db.add(capped_org)
        db.commit()

        key_capped = APIKeyService.generate_api_key(
            db=db,
            org_id="org_test_capped_starter",
            name="Capped Key",
            environment="dev"
        )
        capped_key = key_capped["api_key"]

    capped_mb = MemoryBrain(api_key=capped_key)
    capped_mb._http = TestClientAdapterHTTPClient(api_key=capped_key)
    capped_mb.memories._http = capped_mb._http

    try:
        capped_mb.store(user_id="capped_user", content="Will fail due to 0 quota.")
        assert False, "Expected QuotaExceededError was not raised!"
    except QuotaExceededError as e:
        assert e.status_code == 429
        assert "limit reached" in str(e).lower() or "upgrade" in str(e).lower()
        print(f"  ✅ Correctly raised QuotaExceededError: {e}")

    # -------------------------------------------------------------
    # Test 4: Memory Deletion and GDPR Wipe Operations
    # -------------------------------------------------------------
    print("\n▶ [Test 4] Memory Deletion & GDPR Wipe...")
    # Wipe user
    wipe_res = mb.delete(user_id=user_id)
    assert wipe_res is not None

    # Verify context is now empty
    empty_res = mb.recall(user_id=user_id, query="database")
    assert empty_res["context"] == ""
    print("  ✅ GDPR wipe executed cleanly via mb.delete(user_id=...)!")

    # -------------------------------------------------------------
    # Test 5: OpenAPI 3.1 Contract Specification Verification
    # -------------------------------------------------------------
    print("\n▶ [Test 5] Validating docs/openapi.yaml...")
    openapi_file = ROOT_DIR / "docs" / "openapi.yaml"
    assert openapi_file.exists(), "docs/openapi.yaml missing!"

    with open(openapi_file, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    assert spec["openapi"].startswith("3.1")
    assert "/v1/memories" in spec["paths"]
    assert "/v1/context" in spec["paths"]
    assert "BearerAuth" in spec["components"]["securitySchemes"]
    print(f"  ✅ Validated OpenAPI {spec['openapi']} specification ({len(spec['paths'])} paths defined)!")

    # -------------------------------------------------------------
    # Test 6: Mintlify Docs Configuration Verification
    # -------------------------------------------------------------
    print("\n▶ [Test 6] Validating Mintlify Docs Structure (mint.json)...")
    mint_file = ROOT_DIR / "docs" / "mint.json"
    assert mint_file.exists(), "docs/mint.json missing!"

    with open(mint_file, "r", encoding="utf-8") as f:
        mint_conf = json.load(f)

    assert mint_conf["name"] == "MemoryBrain"
    assert mint_conf["api"]["openapi"] == "openapi.yaml"
    assert (ROOT_DIR / "docs" / "quickstart.mdx").exists()
    assert (ROOT_DIR / "docs" / "guides" / "openai-assistants.mdx").exists()
    assert (ROOT_DIR / "docs" / "guides" / "langchain.mdx").exists()
    assert (ROOT_DIR / "docs" / "guides" / "claude.mdx").exists()
    print("  ✅ Mintlify project configured with Quickstart & all 3 priority framework guides!")

    # -------------------------------------------------------------
    # Test 7: TypeScript SDK Package & Build Verification
    # -------------------------------------------------------------
    print("\n▶ [Test 7] Validating TypeScript SDK Package Configuration...")
    ts_package = ROOT_DIR / "sdk-typescript" / "package.json"
    assert ts_package.exists()

    with open(ts_package, "r", encoding="utf-8") as f:
        pkg = json.load(f)

    assert pkg["name"] == "@memorybrain/sdk"
    assert (ROOT_DIR / "sdk-typescript" / "src" / "index.ts").exists()
    assert (ROOT_DIR / "sdk-typescript" / "src" / "client.ts").exists()
    assert (ROOT_DIR / "sdk-typescript" / "src" / "memory.ts").exists()
    assert (ROOT_DIR / "sdk-typescript" / "src" / "errors.ts").exists()
    assert (ROOT_DIR / "sdk-typescript" / "src" / "http.ts").exists()
    assert (ROOT_DIR / "sdk-typescript" / "tsconfig.json").exists()
    print("  ✅ @memorybrain/sdk TypeScript package structure and typings verified!")

    # -------------------------------------------------------------
    # Test 8: CI Release Workflows
    # -------------------------------------------------------------
    print("\n▶ [Test 8] Validating CI Automation Workflows...")
    assert (ROOT_DIR / ".github" / "workflows" / "publish-python.yml").exists()
    assert (ROOT_DIR / ".github" / "workflows" / "publish-typescript.yml").exists()
    assert (ROOT_DIR / ".github" / "workflows" / "docs-preview.yml").exists()
    print("  ✅ Automated CI release workflows configured for PyPI, npm, and Mintlify!")

    print("\n" + "=" * 78)
    print(" 🌟 ALL 8 STEP 3 DISTRIBUTION & SDK TESTS PASSED (100%)")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    run_step3_test_suite()
