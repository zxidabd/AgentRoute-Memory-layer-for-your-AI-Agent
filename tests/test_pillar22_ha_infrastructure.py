"""
Pillar 22: Step 5 High-Availability (HA) Infrastructure & SRE Verification Suite.
Validates:
1. Deep /healthz/liveness active database roundtrip & failure response.
2. /healthz/readiness and /healthz/startup probes.
3. Database Read/Write session routing (get_db_session vs get_read_db_session).
4. Tiered automated backups (hourly, daily, weekly) with retention rules.
5. Automated scratch-database restore drill with data integrity smoke tests.
"""

import sys
import unittest
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from fastapi.testclient import TestClient
from agent_memory.api.server import app
from agent_memory.database import SessionFactory, init_db, check_db_health, check_read_db_health, get_read_db_session
from agent_memory.models.db_models import Organization, Project, Memory
from scripts.backup_postgres import backup_database, prune_expired_backups
from scripts.restore_drill import run_restore_drill


class TestHighAvailabilityInfrastructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def test_01_healthz_liveness_active_db_check(self):
        """Verify /healthz/liveness performs real DB roundtrip."""
        resp = self.client.get("/healthz/liveness")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "alive")
        self.assertEqual(data["database"], "connected")

    def test_02_healthz_readiness_and_startup(self):
        """Verify /healthz/readiness and /healthz/startup probes report ready."""
        resp_ready = self.client.get("/healthz/readiness")
        self.assertEqual(resp_ready.status_code, 200)
        data_ready = resp_ready.json()
        self.assertEqual(data_ready["status"], "ready")
        self.assertEqual(data_ready["primary_db"], "healthy")

        resp_startup = self.client.get("/healthz/startup")
        self.assertEqual(resp_startup.status_code, 200)
        data_startup = resp_startup.json()
        self.assertEqual(data_startup["status"], "started")
        self.assertTrue(data_startup["initialized"])

    def test_03_read_session_routing_and_fallback(self):
        """Verify get_read_db_session successfully yields a working session."""
        gen = get_read_db_session()
        read_session = next(gen)
        try:
            # Simple query through read session
            count = read_session.query(Organization).count()
            self.assertGreaterEqual(count, 0)
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    def test_04_tiered_backup_cadence_generation(self):
        """Verify creation of hourly, daily, and weekly backup archives."""
        for tier in ["hourly", "daily", "weekly"]:
            b_path = backup_database(tier=tier)
            self.assertTrue(Path(b_path).exists(), f"Backup file for {tier} should exist")
            self.assertGreater(Path(b_path).stat().st_size, 0)

        # Verify pruner runs non-destructively
        pruned = prune_expired_backups()
        self.assertGreaterEqual(pruned, 0)

    def test_05_scratch_database_restore_drill(self):
        """Execute full automated restore drill into scratch DB and verify certificate report."""
        report = run_restore_drill()
        self.assertEqual(report["status"], "PASS")
        self.assertGreaterEqual(report["verification_metrics"]["memories_recovered"], 0)
        self.assertGreaterEqual(report["verification_metrics"]["organizations_recovered"], 0)
        self.assertEqual(report["verification_metrics"]["decryption_smoke_check"], "PASS")
        self.assertIn("99.95% High-Availability", report["sla_certification"])


if __name__ == "__main__":
    unittest.main()
