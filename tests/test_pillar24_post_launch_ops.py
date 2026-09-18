"""
Pillar 24: Step 7 Post-Launch Operations & Foundation Verification Suite.
Validates:
1. Complete operational playbooks in docs/ops/ (Support, Sales, Finance, Hiring, Roadmap, Security, Infra).
2. Algorithmic usage health score and proactive churn prediction engine.
3. GET /v1/analytics/orgs/health-scores API endpoint.
4. Enterprise Contract & DPA automated dispatch service.
5. Master Operations Handbook index and cross-references.
"""

import sys
import unittest
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from agent_memory.api.server import app
from agent_memory.database import SessionFactory, init_db
from agent_memory.models.db_models import Organization, Project, APIKey, UsageEvent, Memory
from agent_memory.auth.api_key_service import APIKeyService
from agent_memory.analytics.health_score import UsageHealthScoreEngine
from agent_memory.billing.contracts import ContractDispatchService


class TestPostLaunchOperations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.db = SessionFactory()

        # Create test organization
        cls.org_id = f"org_ops_{uuid.uuid4().hex[:8]}"
        cls.org = Organization(
            id=cls.org_id,
            name="Operations Test Corp",
            slug=f"ops-test-{uuid.uuid4().hex[:6]}",
            tier="enterprise",
            subscription_status="active"
        )
        cls.db.add(cls.org)
        cls.db.commit()

        key_res = APIKeyService.generate_api_key(
            db=cls.db,
            org_id=cls.org.id,
            name="Ops Runner Key",
            role="owner",
            environment="test"
        )
        cls.api_key = key_res["api_key"]
        cls.headers = {"Authorization": f"Bearer {cls.api_key}"}

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_01_operations_handbooks_and_playbooks_exist(self):
        """Verify all 8 operational documents exist, are non-empty, and contain required SOPs."""
        ops_files = {
            "docs/ops/operations-handbook.md": ["Master Operations Handbook", "Directory of Operating Systems", "Core Operational Cadences"],
            "docs/ops/support-operations-handbook.md": ["SLA Matrix", "< 24 Hours", "< 4 Hours", "Bug Escalation"],
            "docs/ops/sales-pipeline-playbook.md": ["CRM Pipeline Stages", "Lead", "Demo", "Trial", "Contract", "BANT"],
            "docs/ops/finance-and-rev-rec.md": ["ASC 606", "Deferred Revenue", "Stripe Tax", "Unit Economics"],
            "docs/ops/hiring-customer-success-lead.md": ["Founding Customer Success", "Scorecard", "Bottleneck Conditions"],
            "docs/ops/product-roadmap.md": ["RICE Scoring", "NOW (Q3)", "NEXT (Q4)", "LATER (Q1+)"],
            "docs/ops/security-continuous-monitoring.md": ["Vanta", "Remediation SLAs", "< 48 Hours", "Penetration Testing"],
            "docs/ops/infra-scaling-playbook.md": ["5x Active Org Growth", "Cloud SQL Read Replica", "Multi-Region EU"],
        }

        for rel_path, required_terms in ops_files.items():
            full_path = ROOT_DIR / rel_path
            self.assertTrue(full_path.exists(), f"File {rel_path} must exist")
            self.assertGreater(full_path.stat().st_size, 300, f"File {rel_path} must be detailed (>300 bytes)")

            content = full_path.read_text(encoding="utf-8")
            for term in required_terms:
                self.assertIn(term, content, f"File {rel_path} must mention '{term}'")

    def test_02_usage_health_score_engine_calculation(self):
        """Verify health score engine detects active usage and flags at-risk usage drops."""
        # 1. Test active org (has recent activity)
        health_active = UsageHealthScoreEngine.calculate_org_health(self.db, self.org_id)
        self.assertIn("health_score", health_active)
        self.assertIn(health_active["status"], ["HEALTHY", "INACTIVE"])

        # 2. Simulate an account experiencing a severe drop (>40%)
        at_risk_org_id = f"org_churn_{uuid.uuid4().hex[:8]}"
        churn_org = Organization(
            id=at_risk_org_id,
            name="Churn Risk Corp",
            slug=f"churn-risk-{uuid.uuid4().hex[:6]}",
            tier="growth",
            subscription_status="active"
        )
        self.db.add(churn_org)

        # Seed high activity in prior 30 days (100 events) and low activity in last 7 days (2 events)
        now = datetime.now(timezone.utc)
        # Prior activity
        for i in range(40):
            ev = UsageEvent(
                id=f"ev_prior_{uuid.uuid4().hex[:8]}",
                org_id=at_risk_org_id,
                endpoint="/v1/context",
                event_type="RECALL_QUERY",
                units_billed=1,
                timestamp=now - timedelta(days=15)
            )
            self.db.add(ev)
        # Low recent activity (only 1 event in last 7 days)
        ev_recent = UsageEvent(
            id=f"ev_rec_{uuid.uuid4().hex[:8]}",
            org_id=at_risk_org_id,
            endpoint="/v1/context",
            event_type="RECALL_QUERY",
            units_billed=1,
            timestamp=now - timedelta(days=1)
        )
        self.db.add(ev_recent)
        self.db.commit()

        # Evaluate churn org
        churn_health = UsageHealthScoreEngine.calculate_org_health(self.db, at_risk_org_id)
        self.assertEqual(churn_health["status"], "AT_RISK_OF_CHURN")
        self.assertEqual(churn_health["churn_risk"], "CRITICAL")
        self.assertTrue(churn_health["action_required"])
        self.assertLess(churn_health["health_score"], 60)

        # 3. Test portfolio summary
        all_health = UsageHealthScoreEngine.calculate_all_org_health_scores(self.db)
        self.assertGreater(all_health["summary"]["total_evaluated"], 0)
        self.assertGreaterEqual(all_health["summary"]["at_risk_of_churn"], 1)

    def test_03_analytics_orgs_health_scores_endpoint(self):
        """Verify GET /v1/analytics/orgs/health-scores returns portfolio health metrics."""
        resp = self.client.get("/v1/analytics/orgs/health-scores", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("summary", data)
        self.assertIn("total_evaluated", data["summary"])
        self.assertIn("at_risk_accounts", data)
        self.assertIsInstance(data["all_accounts"], list)

    def test_04_enterprise_contract_and_dpa_dispatch(self):
        """Verify automated generation and dispatch of standard enterprise DPA."""
        dpa = ContractDispatchService.generate_and_dispatch_dpa(
            db=self.db,
            org_id=self.org_id,
            authorized_signer_name="Sarah Connor",
            authorized_signer_email="sarah@skynet-defense.com"
        )

        self.assertTrue(dpa["contract_id"].startswith("dpa_"))
        self.assertEqual(dpa["contract_type"], "DATA_PROCESSING_AGREEMENT_GDPR_CCPA")
        self.assertEqual(dpa["status"], "DISPATCHED_PENDING_SIGNATURE")
        self.assertEqual(dpa["authorized_signer"]["email"], "sarah@skynet-defense.com")
        self.assertIn("Standard Contractual Clauses", dpa["governing_clauses"][0])
        self.assertIn("signing_url", dpa)

    def test_05_master_operations_handbook_cross_references(self):
        """Verify Master Operations Handbook links all operational departments."""
        handbook_file = ROOT_DIR / "docs" / "ops" / "operations-handbook.md"
        content = handbook_file.read_text(encoding="utf-8")

        required_links = [
            "support-operations-handbook.md",
            "sales-pipeline-playbook.md",
            "finance-and-rev-rec.md",
            "hiring-customer-success-lead.md",
            "product-roadmap.md",
            "security-continuous-monitoring.md",
            "infra-scaling-playbook.md",
            "uptime-sla-runbook.md",
        ]
        for link in required_links:
            self.assertIn(link, content, f"Handbook must link to {link}")


if __name__ == "__main__":
    unittest.main()
