from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..models.db_models import Organization, Memory, MemoryStatus, UsageEvent
from .plans import get_plan, PlanTier, SubscriptionStatus, BillableEventType
from .usage_tracker import UsageTracker
from .downgrade_manager import DowngradeManager


class PlanEnforcer:
    """Enforces subscription tier limits, handles overage routing, and prevents quota breaches."""

    @classmethod
    def check_dunning_status(cls, db: Session, org: Organization) -> None:
        """Enforces 7-day dunning grace window for past-due subscriptions."""
        if org.subscription_status in [SubscriptionStatus.PAST_DUE.value, SubscriptionStatus.UNPAID.value]:
            now = datetime.now(timezone.utc)
            if not org.past_due_since:
                org.past_due_since = now
                db.commit()

            past_due_dt = org.past_due_since
            if past_due_dt.tzinfo is None:
                past_due_dt = past_due_dt.replace(tzinfo=timezone.utc)

            days_past_due = (now - past_due_dt).days
            # 7-day dunning grace window: allow access during first 7 days
            if days_past_due > 7:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "error": "ACCOUNT_PAST_DUE",
                        "message": f"Account suspended. Payment has been past due for {days_past_due} days (7-day grace window expired). Please update payment method at /dashboard.",
                        "portal_url": "/v1/billing/portal"
                    }
                )

    @classmethod
    def enforce_query_quota(cls, db: Session, org_id: str) -> Dict[str, Any]:
        """Checks if organization is permitted to execute context retrieval or search."""
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            return {"allowed": True, "tier": "starter"}

        # 1. Check account delinquency with 7-day grace window
        cls.check_dunning_status(db, org)

        tier = org.tier or "starter"
        plan = get_plan(tier)

        start_time, _ = UsageTracker.get_billing_period_bounds(org)

        # 2. Total queries in current billing window
        query_count = (
            db.query(func.coalesce(func.sum(UsageEvent.units_billed), 0))
            .filter(
                UsageEvent.org_id == org_id,
                UsageEvent.event_type == BillableEventType.RECALL_QUERY.value,
                UsageEvent.timestamp >= start_time
            )
            .scalar() or 0
        )

        # 3. Quota evaluation
        quota_requests = org.monthly_quota_requests if org.monthly_quota_requests is not None else plan.monthly_quota_requests
        if query_count >= quota_requests:
            if not plan.overage_allowed or not org.overage_billing_enabled:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "QUOTA_EXCEEDED",
                        "message": f"Monthly request limit ({quota_requests:,}) reached on {plan.name}.",
                        "upgrade_url": "/v1/billing/checkout?tier=growth"
                    }
                )
            # Overage permitted for paid plans
            return {
                "allowed": True,
                "tier": plan.tier.value,
                "is_overage": True,
                "current_count": int(query_count),
                "quota": plan.monthly_quota_requests
            }

        return {
            "allowed": True,
            "tier": plan.tier.value,
            "is_overage": False,
            "current_count": int(query_count),
            "quota": plan.monthly_quota_requests
        }

    @classmethod
    def enforce_memory_quota(cls, db: Session, org_id: str) -> Dict[str, Any]:
        """Checks if organization is permitted to store additional active memories."""
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            return {"allowed": True, "tier": "starter"}

        # 1. Check account delinquency with 7-day grace window
        cls.check_dunning_status(db, org)

        # 2. Check if writes are frozen due to downgrade grace window
        is_frozen, freeze_reason = DowngradeManager.check_write_freeze(db, org_id)
        if is_frozen:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "DOWNGRADE_WRITES_FROZEN",
                    "message": freeze_reason,
                    "upgrade_url": "/v1/billing/checkout?tier=growth"
                }
            )

        tier = org.tier or "starter"
        plan = get_plan(tier)

        active_memory_count = (
            db.query(func.count(Memory.id))
            .filter(
                Memory.org_id == org_id,
                Memory.status == MemoryStatus.ACTIVE.value
            )
            .scalar() or 0
        )

        quota_memories = org.monthly_quota_memories if org.monthly_quota_memories is not None else plan.monthly_quota_memories
        if active_memory_count >= quota_memories:
            if not plan.overage_allowed or not org.overage_billing_enabled:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "MEMORY_STORAGE_QUOTA_EXCEEDED",
                        "message": f"Active memory capacity ({quota_memories:,}) reached on {plan.name}.",
                        "upgrade_url": "/v1/billing/checkout?tier=growth"
                    }
                )
            return {
                "allowed": True,
                "tier": plan.tier.value,
                "is_overage": True,
                "active_count": int(active_memory_count),
                "quota": plan.monthly_quota_memories
            }

        return {
            "allowed": True,
            "tier": plan.tier.value,
            "is_overage": False,
            "active_count": int(active_memory_count),
            "quota": plan.monthly_quota_memories
        }
