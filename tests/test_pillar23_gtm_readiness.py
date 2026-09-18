"""
Pillar 23: Step 6 Go-to-Market (GTM) Readiness & Public Funnel Verification Suite.
Validates:
1. GTM collateral integrity: 30 ICP founders list, outreach templates, case studies, Show HN, Product Hunt, war room runbook.
2. Pricing tier consistency across public docs and billing definitions.
3. Interactive browser playground (/playground) availability and rendering.
4. GTM baseline telemetry analytics endpoint (/v1/analytics/gtm/baseline).
5. End-to-end automated dry run execution and signed audit certificate.
"""

import sys
import unittest
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from agent_memory.api.server import app
from agent_memory.database import SessionFactory, init_db
from agent_memory.models.db_models import Organization, Project, APIKey
from agent_memory.auth.api_key_service import APIKeyService
from agent_memory.billing.plans import PLANS, PlanTier
from scripts.gtm_dry_run import run_gtm_dry_run, CERT_FILE


class TestGTMReadiness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.db = SessionFactory()

        # Provision a test admin key for authenticated endpoints
        cls.org = Organization(
            id="org_gtm_test_runner",
            name="GTM Test Org",
            slug="gtm-test-org",
            tier="growth",
            subscription_status="active"
        )
        cls.db.merge(cls.org)
        cls.db.commit()

        key_res = APIKeyService.generate_api_key(
            db=cls.db,
            org_id=cls.org.id,
            name="GTM Runner Key",
            role="owner",
            environment="test"
        )
        cls.api_key = key_res["api_key"]
        cls.headers = {"Authorization": f"Bearer {cls.api_key}"}

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_01_gtm_collateral_assets_exist_and_populated(self):
        """Verify all 8 GTM launch assets exist, are non-empty, and contain required content."""
        assets = {
            "docs/gtm/icp-outreach-targets.md": ["Customer Support", "Coding Assistants", "Sales, Recruiting", "Alex Rivera"],
            "docs/gtm/outreach-templates.md": ["90-day", "Growth tier", "complimentary", "mb.store"],
            "docs/gtm/case-studies.md": ["ResolvAI", "CodePilotX", "OutreachIQ", "18.4 ms"],
            "docs/gtm/show-hn-launch.md": ["Show HN: MemoryBrain", "sub-25ms", "Hybrid Retrieval", "AES-256"],
            "docs/gtm/product-hunt-launch.md": ["HUNTER90", "Tagline", "Maker Opening Comment"],
            "docs/gtm/launch-war-room-runbook.md": ["War Room Commander", "Rapid Hotfix", "< 15 minutes"],
            "docs/gtm/launch-schedule.md": ["Master Launch Timeline", "Show HN", "Product Hunt"],
            "docs/playground.html": ["MemoryBrain — Interactive Developer Playground", "POST /v1/memories", "POST /v1/context"],
        }

        for rel_path, required_terms in assets.items():
            file_path = ROOT_DIR / rel_path
            self.assertTrue(file_path.exists(), f"Asset {rel_path} should exist")
            self.assertGreater(file_path.stat().st_size, 200, f"Asset {rel_path} should not be empty")

            content = file_path.read_text(encoding="utf-8")
            for term in required_terms:
                self.assertIn(term, content, f"Asset {rel_path} must contain '{term}'")

    def test_02_public_pricing_consistency(self):
        """Verify pricing model defines Starter as $0, Growth as $49, and Enterprise."""
        starter = PLANS[PlanTier.STARTER]
        growth = PLANS[PlanTier.GROWTH]
        enterprise = PLANS[PlanTier.ENTERPRISE]

        self.assertEqual(starter.price_usd_monthly, 0.0)
        self.assertEqual(growth.price_usd_monthly, 49.0)
        self.assertIn(enterprise.price_usd_monthly, (499.0, 1999.0))
        self.assertFalse(starter.overage_allowed)
        self.assertTrue(growth.overage_allowed)

    def test_03_interactive_playground_rendering(self):
        """Verify /playground endpoint serves the interactive developer playground."""
        resp = self.client.get("/playground")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("MemoryBrain — Interactive Developer Playground", resp.text)
        self.assertIn("storeMemory()", resp.text)
        self.assertIn("recallMemory()", resp.text)

    def test_04_gtm_baseline_analytics_endpoint(self):
        """Verify GET /v1/analytics/gtm/baseline returns funnel metrics and readiness checklist."""
        resp = self.client.get("/v1/analytics/gtm/baseline", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["status"], "READY_FOR_LAUNCH")
        self.assertIn("funnel_metrics", data)
        self.assertGreater(data["funnel_metrics"]["total_organizations"], 0)
        self.assertGreaterEqual(data["funnel_metrics"]["activation_rate_pct"], 0.0)
        self.assertIn("readiness_checks", data)
        self.assertEqual(data["readiness_checks"]["gtm_launch_assets"], "VERIFIED")
        self.assertEqual(data["readiness_checks"]["dual_gateway_billing"], "VERIFIED")

    def test_05_gtm_end_to_end_dry_run_execution(self):
        """Execute full automated dry run and verify signed certificate output."""
        report = run_gtm_dry_run()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["checks"]["gtm_assets"]["status"], "PASS")
        self.assertEqual(report["checks"]["pricing_tiers"]["status"], "PASS")
        self.assertTrue(report["latency_metrics"]["within_sla"])
        self.assertTrue(CERT_FILE.exists())

        # Validate saved JSON on disk
        saved_data = json.loads(CERT_FILE.read_text(encoding="utf-8"))
        self.assertEqual(saved_data["status"], "PASS")
        self.assertIn("Step 6 Go-to-Market Readiness", saved_data["sla_certification"])


if __name__ == "__main__":
    unittest.main()
