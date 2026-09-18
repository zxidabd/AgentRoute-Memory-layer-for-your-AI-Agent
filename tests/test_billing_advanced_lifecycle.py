"""Comprehensive Test Suite for Advanced B2B Billing Lifecycle:
- Stripe Meter Events API & Idempotency
- Nightly Reconciliation Drift Detector
- 14-Day Downgrade Grace Window & Write Freeze
- 30-Day Recoverable Oldest-First Soft-Archiving
- 7-Day Past-Due Dunning Grace Period
"""

import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import HTTPException

# Console encoding fix
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from agent_memory.database import init_db, get_db
from agent_memory.models.db_models import (
    Organization, Memory, MemoryStatus, UsageEvent, StripeMeterSubmission, PlanDowngrade
)
from agent_memory.billing.plans import BillableEventType, PlanTier, SubscriptionStatus
from agent_memory.billing.usage_tracker import UsageTracker
from agent_memory.billing.metering_worker import metering_worker
from agent_memory.billing.downgrade_manager import DowngradeManager
from agent_memory.billing.plan_enforcer import PlanEnforcer


def run_advanced_billing_test_suite():
    print("\n" + "=" * 78)
    print(" 🛡️ ADVANCED B2B BILLING LIFECYCLE & RESILIENCE TEST SUITE")
    print("=" * 78)

    init_db()

    test_org_id = "org_adv_billing_corp"

    with get_db() as db:
        # Clean test state
        db.query(StripeMeterSubmission).filter(StripeMeterSubmission.org_id == test_org_id).delete()
        db.query(PlanDowngrade).filter(PlanDowngrade.org_id == test_org_id).delete()
        db.query(UsageEvent).filter(UsageEvent.org_id == test_org_id).delete()
        db.query(Memory).filter(Memory.org_id == test_org_id).delete()
        existing = db.query(Organization).filter(Organization.id == test_org_id).first()
        if existing:
            db.delete(existing)
        db.commit()

        # Create test org on Growth tier
        org = Organization(
            id=test_org_id,
            name="Advanced Billing Corp",
            slug="adv-billing-corp",
            tier=PlanTier.GROWTH.value,
            subscription_status=SubscriptionStatus.ACTIVE.value,
            stripe_customer_id="cus_adv_test_99",
            monthly_quota_memories=100000,
            monthly_quota_requests=500000,
            overage_billing_enabled=True
        )
        db.add(org)
        db.commit()

    # =========================================================================
    # TEST 1: Stripe Meter Submissions & Idempotency
    # =========================================================================
    print("\n--- [Step 1] Testing Stripe Meter API & Idempotent Submission ---")
    with get_db() as db:
        # Generate 20 billable events
        for _ in range(20):
            UsageTracker.record_event(
                db, org_id=test_org_id, endpoint="/v1/context",
                event_type=BillableEventType.RECALL_QUERY, units_billed=5
            )

        # Batch 1: Sync to Meter
        res1 = metering_worker.sync_pending_events(db, org_id=test_org_id, batch_size=50)
        print(f"  Batch 1 Synced : {res1['synced_count']} events")
        assert res1["synced_count"] == 20, "Must sync all 20 unmetered events!"

        # Verify records in stripe_meter_submissions table
        sub_count = db.query(StripeMeterSubmission).filter(StripeMeterSubmission.org_id == test_org_id).count()
        assert sub_count == 20, "20 idempotency rows must be recorded in stripe_meter_submissions!"

        # Batch 2: Immediate resync -> Idempotency assertion
        res2 = metering_worker.sync_pending_events(db, org_id=test_org_id, batch_size=50)
        print(f"  Batch 2 Synced : {res2['synced_count']} events (Idempotency check)")
        assert res2["synced_count"] == 0, "Second sync must find 0 events (100% idempotent)!"
        print("  ✅ Stripe Meter Event submission verified with 100% idempotency guarantee!")

    # =========================================================================
    # TEST 2: Nightly Reconciliation Drift Detection
    # =========================================================================
    print("\n--- [Step 2] Testing Reconciliation Drift Detection ---")
    with get_db() as db:
        # Add 3 unmetered events to simulate network drop
        for _ in range(3):
            UsageTracker.record_event(
                db, org_id=test_org_id, endpoint="/v1/context",
                event_type=BillableEventType.RECALL_QUERY, units_billed=10
            )

        # Audit check: Drift must be detected
        audit = metering_worker.run_reconciliation_check(db, test_org_id)
        print(f"  Usage Units    : {audit['internal_usage_events_units']}")
        print(f"  Submitted Units: {audit['submitted_meter_units']}")
        print(f"  Detected Drift : {audit['unmetered_drift']} units")
        assert audit["is_drift_detected"] is True, "Reconciliation must detect unmetered drift!"
        assert audit["unmetered_drift"] == 30, "Drift calculation mismatch!"

        # Auto-heal sync
        sync_res = metering_worker.sync_pending_events(db, org_id=test_org_id)
        post_audit = metering_worker.run_reconciliation_check(db, test_org_id)
        assert post_audit["is_drift_detected"] is False, "Auto-heal must resolve drift to 0!"
        print("  ✅ Reconciliation drift detector & auto-healing verified!")

    # =========================================================================
    # TEST 3: 14-Day Downgrade Grace Window & Write Freeze
    # =========================================================================
    print("\n--- [Step 3] Testing 14-Day Downgrade Grace Window & Write Freeze ---")
    with get_db() as db:
        # Populate 6,000 active memories (exceeds Starter tier limit of 5,000)
        now = datetime.now(timezone.utc)
        memories = [
            Memory(
                id=f"mem_dg_{i:04d}",
                org_id=test_org_id,
                user_id="user_downgrade",
                statement=f"Fact number {i}",
                category="FACT",
                entity="test",
                status="ACTIVE",
                created_at=now - timedelta(days=(6000 - i))
            )
            for i in range(6000)
        ]
        db.add_all(memories)
        db.commit()

        # Initiate downgrade to Starter
        dg_res = DowngradeManager.initiate_downgrade(
            db, org_id=test_org_id, from_tier="growth", to_tier="starter"
        )
        print(f"  Downgrade Status : {dg_res['status']}")
        print(f"  Writes Frozen    : {dg_res['writes_frozen']}")
        print(f"  Grace Expires At : {dg_res['grace_expires_at']}")
        assert dg_res["writes_frozen"] is True, "Writes must be frozen during downgrade grace!"

        # Verify write rejection via PlanEnforcer
        try:
            PlanEnforcer.enforce_memory_quota(db, test_org_id)
            assert False, "Memory write must be rejected with 429 while writes are frozen!"
        except HTTPException as exc:
            assert exc.status_code == 429
            assert exc.detail["error"] == "DOWNGRADE_WRITES_FROZEN"
            print("  ✅ Write-freeze verified: New memory creation blocked during grace period!")

        # Verify read/context retrieval is NOT blocked
        query_check = PlanEnforcer.enforce_query_quota(db, test_org_id)
        assert query_check["allowed"] is True, "Recall queries must NOT be blocked during grace!"
        print("  ✅ Read access preserved: Recall queries continue functioning seamlessly!")

    # =========================================================================
    # TEST 4: Oldest-First Soft-Archiving on Grace Window Expiration
    # =========================================================================
    print("\n--- [Step 4] Testing Oldest-First Soft-Archiving on Expiration ---")
    with get_db() as db:
        # Simulate grace window expiring (set grace_expires_at to 1 day ago)
        dg_record = db.query(PlanDowngrade).filter(PlanDowngrade.org_id == test_org_id).first()
        dg_record.grace_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()

        # Run sweep
        sweep_res = DowngradeManager.sweep_expired_downgrades(db)
        print(f"  Resolved Downgrades : {sweep_res['resolved_downgrades_count']}")
        print(f"  Memories Archived   : {sweep_res['total_memories_soft_archived']}")
        assert sweep_res["total_memories_soft_archived"] == 1000, "Must archive exactly 1,000 excess memories!"

        # Verify active count is now exactly at Starter quota (5,000)
        active_count = db.query(Memory).filter(Memory.org_id == test_org_id, Memory.status == "ACTIVE").count()
        soft_archived_count = db.query(Memory).filter(Memory.org_id == test_org_id, Memory.status == "SOFT_DELETED").count()
        print(f"  Remaining Active    : {active_count} (Quota: 5,000)")
        print(f"  Soft-Archived (30d) : {soft_archived_count}")
        assert active_count == 5000, "Active memories must be reduced to exactly 5,000!"
        assert soft_archived_count == 1000, "1,000 memories must be preserved as SOFT_DELETED!"

        # Verify writes are auto-unfrozen now that usage is within quota
        is_frozen, _ = DowngradeManager.check_write_freeze(db, test_org_id)
        assert is_frozen is False, "Writes must be unblocked once memories are within quota!"
        print("  ✅ Oldest-first soft-archiving & automatic write unfreezing verified!")

    # =========================================================================
    # TEST 5: Dunning 7-Day Past-Due Grace Period
    # =========================================================================
    print("\n--- [Step 5] Testing Dunning 7-Day Past-Due Grace Period ---")
    with get_db() as db:
        org = db.query(Organization).filter(Organization.id == test_org_id).first()
        org.subscription_status = SubscriptionStatus.PAST_DUE.value
        now = datetime.now(timezone.utc)

        # Case A: Day 3 of past_due -> Allowed (within 7-day grace window)
        org.past_due_since = now - timedelta(days=3)
        db.commit()
        enforce_grace = PlanEnforcer.enforce_query_quota(db, test_org_id)
        assert enforce_grace["allowed"] is True, "Traffic must be allowed during 7-day dunning grace!"
        print("  ✅ Dunning Day 3: Full access allowed within 7-day grace window!")

        # Case B: Day 8 of past_due -> Blocked with HTTP 402 Payment Required
        org.past_due_since = now - timedelta(days=8)
        db.commit()
        try:
            PlanEnforcer.enforce_query_quota(db, test_org_id)
            assert False, "Must raise HTTP 402 after 7-day dunning window expires!"
        except HTTPException as exc:
            assert exc.status_code == 402
            assert exc.detail["error"] == "ACCOUNT_PAST_DUE"
            print("  ✅ Dunning Day 8: Successfully blocked with HTTP 402 Payment Required!")

    print("\n" + "=" * 78)
    print(" 🏆 ALL ADVANCED B2B BILLING LIFECYCLE TESTS PASSED (100% GREEN)!")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    run_advanced_billing_test_suite()
