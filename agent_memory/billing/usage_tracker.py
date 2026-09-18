"""Usage metering, monthly billing aggregation, and overage computation."""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.db_models import UsageEvent, Memory, MemoryStatus, Organization
from .plans import get_plan, BillableEventType, PlanDetails


class UsageTracker:
    """Manages recording billable events and computing real-time billing metrics."""

    @staticmethod
    def record_event(
        db: Session,
        org_id: str,
        endpoint: str,
        event_type: BillableEventType = BillableEventType.RECALL_QUERY,
        units_billed: int = 1,
        project_id: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_cost_usd: float = 0.0,
        latency_ms: float = 0.0
    ) -> UsageEvent:
        """Persists a billable usage event."""
        event = UsageEvent(
            id=f"use_{uuid.uuid4().hex[:12]}",
            org_id=org_id,
            project_id=project_id,
            endpoint=endpoint,
            event_type=event_type.value if hasattr(event_type, "value") else str(event_type),
            units_billed=units_billed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost_usd,
            latency_ms=latency_ms,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(event)
        try:
            db.commit()
        except Exception:
            db.rollback()
        return event

    @staticmethod
    def get_billing_period_bounds(org: Organization) -> tuple[datetime, datetime]:
        """Calculates current billing period start and end timestamps."""
        now = datetime.now(timezone.utc)
        start = org.current_period_start or now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = org.current_period_end or (start + timedelta(days=30))
        return start, end

    @classmethod
    def get_monthly_usage(cls, db: Session, org_id: str) -> Dict[str, Any]:
        """Aggregates all usage within the current billing cycle."""
        org = db.query(Organization).filter(Organization.id == org_id).first()
        tier = org.tier if org else "starter"
        plan = get_plan(tier)

        start_time, end_time = cls.get_billing_period_bounds(org) if org else (datetime.now(timezone.utc) - timedelta(days=30), datetime.now(timezone.utc))

        # 1. Total recall queries in period
        query_count = (
            db.query(func.coalesce(func.sum(UsageEvent.units_billed), 0))
            .filter(
                UsageEvent.org_id == org_id,
                UsageEvent.event_type == BillableEventType.RECALL_QUERY.value,
                UsageEvent.timestamp >= start_time
            )
            .scalar() or 0
        )

        # 2. Total ingestion turns in period
        ingestion_count = (
            db.query(func.coalesce(func.sum(UsageEvent.units_billed), 0))
            .filter(
                UsageEvent.org_id == org_id,
                UsageEvent.event_type == BillableEventType.INGESTION_TURN.value,
                UsageEvent.timestamp >= start_time
            )
            .scalar() or 0
        )

        # 3. Current active memories stored
        active_memory_count = (
            db.query(func.count(Memory.id))
            .filter(
                Memory.org_id == org_id,
                Memory.status == MemoryStatus.ACTIVE.value
            )
            .scalar() or 0
        )

        # 4. Compute overages
        query_quota = plan.monthly_quota_requests
        memory_quota = plan.monthly_quota_memories

        query_overage_units = max(0, query_count - query_quota)
        memory_overage_units = max(0, active_memory_count - memory_quota)

        query_overage_usd = (query_overage_units / 1000.0) * plan.overage_query_rate_usd_per_1k
        memory_overage_usd = (memory_overage_units / 1000.0) * plan.overage_memory_rate_usd_per_1k
        total_overage_usd = round(query_overage_usd + memory_overage_usd, 4)

        return {
            "org_id": org_id,
            "tier": plan.tier.value,
            "plan_name": plan.name,
            "billing_period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "usage": {
                "queries_executed": int(query_count),
                "queries_quota": query_quota,
                "queries_usage_percent": round((query_count / query_quota) * 100.0, 1) if query_quota else 0.0,
                "active_memories": int(active_memory_count),
                "memories_quota": memory_quota,
                "memories_usage_percent": round((active_memory_count / memory_quota) * 100.0, 1) if memory_quota else 0.0,
                "ingestions_executed": int(ingestion_count)
            },
            "overages": {
                "overage_allowed": plan.overage_allowed,
                "query_overage_units": int(query_overage_units),
                "memory_overage_units": int(memory_overage_units),
                "query_overage_cost_usd": round(query_overage_usd, 4),
                "memory_overage_cost_usd": round(memory_overage_usd, 4),
                "total_overage_usd": total_overage_usd
            },
            "total_estimated_monthly_bill_usd": round(plan.price_usd_monthly + total_overage_usd, 2)
        }
