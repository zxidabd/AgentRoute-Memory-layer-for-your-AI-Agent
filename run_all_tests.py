"""Master Test Runner executing all test suites across the MemoryBrain platform."""

import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent

TESTS = [
    ("Phase 1: Smart Notebook Engine", ROOT_DIR / "test_phase1.py"),
    ("Phase 3: Security Door & Multi-Tenant API", ROOT_DIR / "test_phase3.py"),
    ("Pillar 1: Multi-Tenant Isolation & Adversarial Leak Protection", ROOT_DIR / "tests" / "test_tenant_isolation_leak_proof.py"),
    ("Pillars 2, 10, 11: Production Memory Lifecycle, AES-256 & GDPR", ROOT_DIR / "tests" / "test_production_lifecycle.py"),
    ("Pillars 3, 5: Resilience, Circuit Breaker & Dead Letter Queue", ROOT_DIR / "tests" / "test_resilience_circuit_breaker.py"),
    ("Pillars 4, 14: Benchmark Evaluation & Quality Scoring", ROOT_DIR / "tests" / "test_benchmark_evaluation.py"),
    ("Pillar 17: B2B Billing, Stripe, Razorpay & Plan Enforcement", ROOT_DIR / "tests" / "test_billing_and_plan_enforcement.py"),
    ("Pillar 17 (Advanced): Meter Events, Reconciliation, 14d Downgrades & 7d Dunning", ROOT_DIR / "tests" / "test_billing_advanced_lifecycle.py"),
    ("Pillar 18 (Step 2): Multi-Tenant Team Workspaces, Clerk Webhooks & RBAC", ROOT_DIR / "tests" / "test_team_workspaces_and_auth.py"),
    ("Pillar 19: Model Context Protocol (MCP) Server for Claude Desktop & Cursor", ROOT_DIR / "tests" / "test_mcp_server.py"),
    ("Pillar 20 (Step 3): Developer Distribution, SDKs & Public Mintlify Docs", ROOT_DIR / "tests" / "test_step3_distribution_and_sdks.py"),
    ("Pillar 21 (Step 4): Enterprise Trust, SOC 2 Evidence & Immutability", ROOT_DIR / "tests" / "test_pillar21_enterprise_compliance.py"),
    ("Pillar 22 (Step 5): 99.95% HA Infrastructure, Probes & Restore Drill", ROOT_DIR / "tests" / "test_pillar22_ha_infrastructure.py"),
    ("Pillar 23 (Step 6): Go-to-Market Readiness, Funnel Dry-Run & Telemetry", ROOT_DIR / "tests" / "test_pillar23_gtm_readiness.py"),
    ("Pillar 24 (Step 7): Post-Launch Operations, Churn Analytics & Foundation", ROOT_DIR / "tests" / "test_pillar24_post_launch_ops.py"),
    ("Pillar 25 (Step 5 Addendum): Multi-Deployment Architecture (GCP + AWS + Self-Hosted)", ROOT_DIR / "tests" / "test_pillar25_multi_deployment.py"),
    ("Pillar 26: Enterprise Data Assets, Business Metrics & Lineage Context Graph", ROOT_DIR / "tests" / "test_pillar26_enterprise_data_assets.py"),
    ("Auth Security: Strict Login Gate & Password Verification", ROOT_DIR / "tests" / "test_auth_security.py"),
    ("OAuth Integration: Google Sign-In & Single Sign-On", ROOT_DIR / "tests" / "test_google_auth.py"),
]


def main():
    print("\n" + "=" * 78)
    print(" 🚀 EXECUTING COMPLETE PRODUCTION TEST SUITE: AGENT MEMORY LAYER")
    print("=" * 78 + "\n")

    passed_count = 0
    total_count = len(TESTS)

    for name, script_path in TESTS:
        print(f"▶ Running: {name} ({script_path.name})...", flush=True)
        res = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        if res.returncode == 0:
            print("  ✅ PASSED\n", flush=True)
            passed_count += 1
        else:
            print(f"  ❌ FAILED (Exit Code: {res.returncode})", flush=True)
            print(f"STDOUT:\n{res.stdout}", flush=True)
            print(f"STDERR:\n{res.stderr}\n", flush=True)

    print("=" * 78)
    print(f" 📊 TEST EXECUTION SUMMARY: {passed_count}/{total_count} SUITES PASSED ({passed_count/total_count*100:.0f}%)")
    print("=" * 78 + "\n")

    if passed_count != total_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
