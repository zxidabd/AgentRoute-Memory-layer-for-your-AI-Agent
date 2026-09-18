"""
Pillar 25: Step 5 Addendum — Multi-Deployment Architecture (GCP + AWS + Self-Hosted) Suite.
Validates:
1. pgvector HNSW DDL generation and database engine compatibility.
2. 3-scope Redis context cache with graceful zero-crash in-memory fallback.
3. Open-Core licensing engine: Free core features, enterprise gating, cryptographic verification.
4. Terraform IaC parity across GCP and AWS modules.
5. Self-hosted Docker Compose stack, Nginx reverse proxy, and environment templates.
"""

import sys
import os
import unittest
import uuid
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from agent_memory.database import SessionFactory, init_db
from agent_memory.storage.vector_extension import get_pgvector_ddl, setup_vector_support
from agent_memory.cache.redis_cache import RedisContextCache
from agent_memory.licensing.license_validator import LicenseValidator, LicenseError


class TestMultiDeploymentArchitecture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.db = SessionFactory()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_01_pgvector_hnsw_ddl_and_setup(self):
        """Verify pgvector DDL statements use HNSW index and setup runs gracefully."""
        ddl = get_pgvector_ddl(dimension=768, m=16, ef_construction=64)
        self.assertEqual(len(ddl), 3)
        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector", ddl[0])
        self.assertIn("vector(768)", ddl[1])
        self.assertIn("USING hnsw (embedding vector_cosine_ops)", ddl[2])
        self.assertIn("m = 16", ddl[2])

        # Test dialect inspection and graceful setup on existing engine
        res = setup_vector_support(self.db.get_bind(), dimension=768)
        self.assertIn("dialect", res)
        self.assertEqual(res["dimension"], 768)
        self.assertIn(res["status"], ["CONFIGURED", "SQLITE_JSON_MODE", "FALLBACK_TO_JSON"])

    def test_02_redis_context_cache_and_resilient_fallback(self):
        """Verify Redis context caching works and degrades gracefully when disconnected."""
        cache = RedisContextCache(default_ttl=60)
        org_id = f"org_{uuid.uuid4().hex[:6]}"
        user_id = "user_deploy_test"
        query = "What is the primary cloud provider?"
        sample_context = {
            "user_id": user_id,
            "context": "Primary cloud provider is Google Cloud Platform (GCP).",
            "token_count": 12,
            "memory_count": 1
        }

        # 1. Cache set and get
        success = cache.cache_context(org_id, user_id, query, sample_context, ttl=60)
        self.assertTrue(success)

        retrieved = cache.get_cached_context(org_id, user_id, query)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["context"], sample_context["context"])

        # 2. Simulate complete Redis outage (kill connection)
        cache._redis = None
        # Cache must continue to work via local resilient storage without throwing exceptions
        retrieved_offline = cache.get_cached_context(org_id, user_id, query)
        self.assertIsNotNone(retrieved_offline)
        self.assertEqual(retrieved_offline["context"], sample_context["context"])

        # 3. Cache Invalidation
        cache.invalidate_user_context(org_id, user_id)
        invalidated = cache.get_cached_context(org_id, user_id, query)
        self.assertIsNone(invalidated)

    def test_03_open_core_licensing_validation(self):
        """Verify open-core licensing: free core features, cryptographic validation, and enterprise gating."""
        # 1. Core features are always entitled
        self.assertTrue(LicenseValidator.is_feature_entitled("store_memory"))
        self.assertTrue(LicenseValidator.is_feature_entitled("recall_context"))
        self.assertTrue(LicenseValidator.is_feature_entitled("delete_memory"))

        # 2. Generate and verify valid signed license
        key = LicenseValidator.generate_signed_license(
            customer_name="Stripe Partner",
            tier="enterprise",
            entitlements=["enterprise_rbac", "compliance_pack", "custom_limits"],
            expires_days=30
        )
        self.assertTrue(key.startswith("mb_lic_"))

        payload = LicenseValidator.verify_license_key(key)
        self.assertEqual(payload["customer_name"], "Stripe Partner")
        self.assertEqual(payload["tier"], "enterprise")
        self.assertIn("compliance_pack", payload["entitlements"])

        # 3. Test tampering detection
        tampered_key = key[:-4] + "abcd"
        with self.assertRaises(LicenseError):
            LicenseValidator.verify_license_key(tampered_key)

        # 4. Test self-hosted feature gating
        old_mode = os.environ.get("DEPLOYMENT_MODE")
        old_key = os.environ.get("MEMORYBRAIN_LICENSE_KEY")
        try:
            os.environ["DEPLOYMENT_MODE"] = "self_hosted"
            os.environ["MEMORYBRAIN_LICENSE_KEY"] = ""

            # Without license in self-hosted, enterprise feature is denied
            self.assertFalse(LicenseValidator.is_feature_entitled("compliance_pack"))

            # With valid license in self-hosted, enterprise feature is unlocked
            os.environ["MEMORYBRAIN_LICENSE_KEY"] = key
            self.assertTrue(LicenseValidator.is_feature_entitled("compliance_pack"))
        finally:
            if old_mode is not None:
                os.environ["DEPLOYMENT_MODE"] = old_mode
            else:
                os.environ.pop("DEPLOYMENT_MODE", None)

            if old_key is not None:
                os.environ["MEMORYBRAIN_LICENSE_KEY"] = old_key
            else:
                os.environ.pop("MEMORYBRAIN_LICENSE_KEY", None)

    def test_04_terraform_module_parity(self):
        """Verify presence and parity between GCP and AWS Terraform configurations."""
        shared_vars_file = ROOT_DIR / "infra" / "terraform" / "variables.tf"
        gcp_main = ROOT_DIR / "infra" / "terraform" / "gcp" / "main.tf"
        gcp_outputs = ROOT_DIR / "infra" / "terraform" / "gcp" / "outputs.tf"
        aws_main = ROOT_DIR / "infra" / "terraform" / "aws" / "main.tf"
        aws_outputs = ROOT_DIR / "infra" / "terraform" / "aws" / "outputs.tf"

        for p in [shared_vars_file, gcp_main, gcp_outputs, aws_main, aws_outputs]:
            self.assertTrue(p.exists(), f"Terraform file {p} should exist")

        # Check GCP contents
        gcp_text = gcp_main.read_text(encoding="utf-8")
        self.assertIn("google_cloud_run_v2_service", gcp_text)
        self.assertIn("POSTGRES_16", gcp_text)
        self.assertIn("cloudsql.enable_pgvector", gcp_text)
        self.assertIn("google_redis_instance", gcp_text)

        # Check AWS contents
        aws_text = aws_main.read_text(encoding="utf-8")
        self.assertIn("aws_ecs_service", aws_text)
        self.assertIn("aws_db_instance", aws_text)
        self.assertIn("aws_elasticache_replication_group", aws_text)
        self.assertIn("shared_preload_libraries", aws_text)

    def test_05_docker_compose_self_hosted_package(self):
        """Verify self-hosted docker-compose stack and reverse proxy configuration."""
        compose_file = ROOT_DIR / "infra" / "self-hosted" / "docker-compose.yml"
        env_example = ROOT_DIR / "infra" / "self-hosted" / ".env.example"
        nginx_conf = ROOT_DIR / "infra" / "self-hosted" / "nginx" / "default.conf"

        for p in [compose_file, env_example, nginx_conf]:
            self.assertTrue(p.exists(), f"File {p} should exist")
            self.assertGreater(p.stat().st_size, 100)

        compose_text = compose_file.read_text(encoding="utf-8")
        for s in ["api:", "db:", "redis:", "nginx:", "certbot:"]:
            self.assertIn(s, compose_text)
        self.assertIn("pgvector/pgvector:pg16", compose_text)
        self.assertIn("--appendonly", compose_text)

        nginx_text = nginx_conf.read_text(encoding="utf-8")
        self.assertIn("proxy_pass http://api:8000;", nginx_text)
        self.assertIn("proxy_set_header Upgrade $http_upgrade;", nginx_text)


if __name__ == "__main__":
    unittest.main()
