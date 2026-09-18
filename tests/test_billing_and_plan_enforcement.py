"""Comprehensive Test Suite for B2B Billing, Stripe, Razorpay, Quotas, and Plan Enforcement."""

import sys
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import HTTPException

# Windows console encoding fix
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from agent_memory.database import init_db, get_db
from agent_memory.models.db_models import Organization, Memory, MemoryStatus, UsageEvent
from agent_memory.billing.plans import PLANS, PlanTier, SubscriptionStatus, BillableEventType, get_plan
from agent_memory.billing.usage_tracker import UsageTracker
from agent_memory.billing.plan_enforcer import PlanEnforcer
from agent_memory.billing.stripe_service import StripeBillingService
from agent_memory.billing.razorpay_service import RazorpayBillingService


def run_billing_test_suite():
    print("\n" + "=" * 78)
    print(" 💳 B2B BILLING, STRIPE, RAZORPAY & PLAN ENFORCEMENT TEST SUITE")
    print("=" * 78)

    init_db()

    # Setup test organizations
    org_starter_id = "org_billing_test_starter"
    org_growth_id = "org_billing_test_growth"
    org_delinquent_id = "org_billing_test_delinquent"

    with get_db() as db:
        for oid in [org_starter_id, org_growth_id, org_delinquent_id]:
            existing = db.query(Organization).filter(Organization.id == oid).first()
            if existing:
                db.delete(existing)
            db.query(UsageEvent).filter(UsageEvent.org_id == oid).delete()
            db.query(Memory).filter(Memory.org_id == oid).delete()
        db.commit()

        # 1. Create Starter Org
        org_starter = Organization(
            id=org_starter_id,
            name="Free Hobbyist Team",
            slug="free-hobbyist",
            tier="starter",
            subscription_status="active",
            monthly_quota_requests=25000,
            monthly_quota_memories=5000,
            overage_billing_enabled=False
        )
        # 2. Create Growth Org
        org_growth = Organization(
            id=org_growth_id,
            name="Acme AI Startup",
            slug="acme-ai-startup",
            tier="growth",
            subscription_status="active",
            monthly_quota_requests=500000,
            monthly_quota_memories=100000,
            overage_billing_enabled=True,
            stripe_customer_id="cus_test_acme_123"
        )
        # 3. Create Delinquent Org
        org_delinquent = Organization(
            id=org_delinquent_id,
            name="Past Due Corp",
            slug="past-due-corp",
            tier="growth",
            subscription_status="past_due",
            past_due_since=datetime.now(timezone.utc) - timedelta(days=10),
            overage_billing_enabled=True
        )
        db.add_all([org_starter, org_growth, org_delinquent])
        db.commit()

    # =========================================================================
    # TEST 1: Tier & Pricing Specifications
    # =========================================================================
    print("\n--- [Step 1] Verifying B2B Product & Price Specifications ---")
    starter_plan = get_plan("starter")
    growth_plan = get_plan("growth")
    scale_plan = get_plan("scale")
    enterprise_plan = get_plan("enterprise")

    assert starter_plan.price_usd_monthly == 0.0, "Starter must be free"
    assert starter_plan.overage_allowed is False, "Starter must block overages"
    assert growth_plan.price_usd_monthly == 49.0, "Growth plan price mismatch"
    assert growth_plan.overage_query_rate_usd_per_1k == 0.10, "Growth overage query rate mismatch"
    assert scale_plan.price_usd_monthly == 249.0, "Scale plan price mismatch"
    assert scale_plan.monthly_quota_requests == 5000000, "Scale quota mismatch"
    assert enterprise_plan.price_usd_monthly == 1999.0, "Enterprise price mismatch"
    print("  ✅ All 4 Tiers (Starter, Growth, Scale, Enterprise) verified with exact quotas and pricing!")

    # =========================================================================
    # TEST 2: Usage Tracking & Monthly Aggregation
    # =========================================================================
    print("\n--- [Step 2] Testing Billable Event Metering & Usage Aggregation ---")
    with get_db() as db:
        # Record 150 recall queries and 10 ingest turns
        for _ in range(15):
            UsageTracker.record_event(
                db, org_id=org_growth_id, endpoint="/v1/context",
                event_type=BillableEventType.RECALL_QUERY, units_billed=10
            )
        UsageTracker.record_event(
            db, org_id=org_growth_id, endpoint="/v1/memories",
            event_type=BillableEventType.INGESTION_TURN, units_billed=10
        )

        # Store 20 sample active memories
        for i in range(20):
            db.add(Memory(
                id=f"mem_usage_{i}", org_id=org_growth_id, user_id="user_test",
                statement="enc_statement", category="FACT", entity="user", status="ACTIVE"
            ))
        db.commit()

        usage = UsageTracker.get_monthly_usage(db, org_growth_id)
        print(f"  Recorded Queries : {usage['usage']['queries_executed']}")
        print(f"  Active Memories  : {usage['usage']['active_memories']}")
        print(f"  Ingestions       : {usage['usage']['ingestions_executed']}")
        assert usage["usage"]["queries_executed"] == 150, "Query metering count mismatch!"
        assert usage["usage"]["active_memories"] == 20, "Active memory count mismatch!"
        print("  ✅ Usage Metering and Aggregation verified!")

    # =========================================================================
    # TEST 3: Overage Billing Computation
    # =========================================================================
    print("\n--- [Step 3] Testing Overage Calculation Formula ---")
    with get_db() as db:
        # Intentionally record overage events for Growth tier (quota: 500,000)
        # Add 5,000 queries above quota
        UsageTracker.record_event(
            db, org_id=org_growth_id, endpoint="/v1/context",
            event_type=BillableEventType.RECALL_QUERY, units_billed=505000 - 150
        )
        usage = UsageTracker.get_monthly_usage(db, org_growth_id)
        overages = usage["overages"]
        print(f"  Total Queries    : {usage['usage']['queries_executed']:,}")
        print(f"  Overage Units    : {overages['query_overage_units']:,}")
        print(f"  Overage Charge   : ${overages['query_overage_cost_usd']:.2f}")
        print(f"  Estimated Bill   : ${usage['total_estimated_monthly_bill_usd']:.2f}")

        assert overages["query_overage_units"] == 5000, "Overage units mismatch!"
        # 5,000 / 1,000 * $0.10 = $0.50
        assert overages["query_overage_cost_usd"] == 0.50, "Overage charge mismatch!"
        assert usage["total_estimated_monthly_bill_usd"] == 49.50, "Total monthly bill mismatch!"
        print("  ✅ Automated overage math verified ($0.10/1k queries)!")

    # =========================================================================
    # TEST 4: Real-time API Plan Enforcement
    # =========================================================================
    print("\n--- [Step 4] Testing Real-Time API Plan Enforcement ---")
    with get_db() as db:
        # A. Delinquent account blocked with 402
        try:
            PlanEnforcer.enforce_query_quota(db, org_delinquent_id)
            assert False, "Delinquent account must be blocked!"
        except HTTPException as exc:
            assert exc.status_code == 402, "Must return HTTP 402 Payment Required"
            print("  ✅ Delinquent account successfully blocked with HTTP 402 Payment Required!")

        # B. Starter tier exceeding quota blocked with 429
        # Pump starter usage past 25,000
        UsageTracker.record_event(
            db, org_id=org_starter_id, endpoint="/v1/context",
            event_type=BillableEventType.RECALL_QUERY, units_billed=25001
        )
        try:
            PlanEnforcer.enforce_query_quota(db, org_starter_id)
            assert False, "Starter plan must be hard-capped at 25,000 requests!"
        except HTTPException as exc:
            assert exc.status_code == 429, "Must return HTTP 429 Quota Exceeded"
            print("  ✅ Starter plan hard cap enforced with HTTP 429 Quota Exceeded!")

        # C. Growth tier exceeding quota ALLOWED with overage flag
        enforce_growth = PlanEnforcer.enforce_query_quota(db, org_growth_id)
        assert enforce_growth["allowed"] is True, "Growth plan must allow requests with overage!"
        assert enforce_growth["is_overage"] is True, "Growth plan must flag request as overage!"
        print("  ✅ Paid tier overage allowance verified without disrupting customer traffic!")

    # =========================================================================
    # TEST 5: Stripe Webhook Lifecycle Processing
    # =========================================================================
    print("\n--- [Step 5] Testing Stripe Webhook Lifecycle (Upgrade & Cancel) ---")
    stripe_service = StripeBillingService()

    # Simulate customer.subscription.updated from Stripe (Starter -> Scale)
    mock_stripe_payload = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_stripe_scale_987",
                "customer": "cus_test_acme_123",
                "status": "active",
                "current_period_start": int(time.time()),
                "current_period_end": int(time.time()) + 2592000,
                "metadata": {"org_id": org_growth_id, "target_tier": "scale"},
                "items": {"data": [{"price": {"id": "price_scale_249usd_mo"}}]}
            }
        }
    }
    with get_db() as db:
        res = stripe_service.process_webhook(json.dumps(mock_stripe_payload).encode("utf-8"), sig_header=None, db=db)
        assert res["status"] == "success"
        assert res["tier"] == "scale"

        updated_org = db.query(Organization).filter(Organization.id == org_growth_id).first()
        assert updated_org.tier == "scale"
        assert updated_org.stripe_subscription_id == "sub_stripe_scale_987"
        print("  ✅ Stripe Webhook: Subscription upgrade to 'Scale' processed successfully!")

    # Simulate customer.subscription.deleted from Stripe
    mock_cancel_payload = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"customer": "cus_test_acme_123"}}
    }
    with get_db() as db:
        stripe_service.process_webhook(json.dumps(mock_cancel_payload).encode("utf-8"), sig_header=None, db=db)
        canceled_org = db.query(Organization).filter(Organization.id == org_growth_id).first()
        assert canceled_org.tier == "starter"
        assert canceled_org.subscription_status == "canceled"
        print("  ✅ Stripe Webhook: Subscription cancellation & downgrade to 'Starter' verified!")

    # =========================================================================
    # TEST 6: Razorpay Webhook Lifecycle Processing
    # =========================================================================
    print("\n--- [Step 6] Testing Razorpay Webhook Lifecycle (UPI / Cards in APAC) ---")
    razorpay_service = RazorpayBillingService()

    # Simulate subscription.charged from Razorpay
    mock_rzp_payload = {
        "event": "subscription.charged",
        "payload": {
            "subscription": {
                "entity": {
                    "id": "sub_rzp_test_555",
                    "status": "active",
                    "notes": {"org_id": org_starter_id, "target_tier": "growth"}
                }
            }
        }
    }
    with get_db() as db:
        rzp_res = razorpay_service.process_webhook(json.dumps(mock_rzp_payload).encode("utf-8"), signature=None, db=db)
        assert rzp_res["status"] == "success"
        assert rzp_res["tier"] == "growth"

        rzp_org = db.query(Organization).filter(Organization.id == org_starter_id).first()
        assert rzp_org.tier == "growth"
        assert rzp_org.billing_gateway == "razorpay"
        print("  ✅ Razorpay Webhook: UPI/Card renewal & upgrade to 'Growth' verified!")

    print("\n" + "=" * 78)
    print(" 🏆 ALL B2B BILLING, STRIPE & RAZORPAY TESTS PASSED (100% GREEN)!")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    run_billing_test_suite()
