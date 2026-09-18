"""Downgrade Grace Window and Write-Freeze Lifecycle Manager."""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..models.db_models import Organization, PlanDowngrade, Memory, MemoryStatus
from .plans import get_plan, PlanTier


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class DowngradeManager:
    """Handles 14-day downgrade grace windows, write freezing, and oldest-first soft archiving."""

    GRACE_PERIOD_DAYS = 14
    RECOVERY_WINDOW_DAYS = 30

    @classmethod
    def initiate_downgrade(
        cls,
        db: Session,
        org_id: str,
        from_tier: str,
        to_tier: str
    ) -> Dict[str, Any]:
        """Triggered when an organization is demoted to a lower tier."""
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise ValueError(f"Organization {org_id} not found.")

        target_plan = get_plan(to_tier)
        now = datetime.now(timezone.utc)

        # Check current active memory count against new tier quota
        active_memory_count = (
            db.query(func.count(Memory.id))
            .filter(Memory.org_id == org_id, Memory.status == MemoryStatus.ACTIVE.value)
            .scalar() or 0
        )

        org.tier = to_tier
        org.subscription_tier = to_tier

        # If memories exceed new tier limit, activate 14-day write-freeze grace window
        if active_memory_count > target_plan.monthly_quota_memories:
            grace_expiry = now + timedelta(days=cls.GRACE_PERIOD_DAYS)
            downgrade_record = PlanDowngrade(
                id=f"dng_{uuid.uuid4().hex[:12]}",
                org_id=org.id,
                from_tier=from_tier,
                to_tier=to_tier,
                effective_at=now,
                grace_expires_at=grace_expiry,
                resolved_at=None,
                created_at=now
            )
            db.add(downgrade_record)
            db.commit()

            return {
                "status": "grace_window_activated",
                "org_id": org.id,
                "active_memories": int(active_memory_count),
                "quota": target_plan.monthly_quota_memories,
                "writes_frozen": True,
                "grace_expires_at": grace_expiry.isoformat(),
                "message": (
                    f"Downgrade to {target_plan.name} effective. Memory writes frozen for {cls.GRACE_PERIOD_DAYS} days "
                    f"until memory count is reduced below {target_plan.monthly_quota_memories:,}."
                )
            }

        db.commit()
        return {
            "status": "immediate_downgrade",
            "org_id": org.id,
            "writes_frozen": False,
            "message": f"Successfully downgraded to {target_plan.name}. Usage is within quota."
        }

    @classmethod
    def check_write_freeze(cls, db: Session, org_id: str) -> Tuple[bool, Optional[str]]:
        """Checks whether the organization's memory writes are frozen due to an active downgrade grace window."""
        active_downgrade = (
            db.query(PlanDowngrade)
            .filter(
                PlanDowngrade.org_id == org_id,
                PlanDowngrade.resolved_at.is_(None)
            )
            .first()
        )
        if not active_downgrade:
            return False, None

        org = db.query(Organization).filter(Organization.id == org_id).first()
        plan = get_plan(org.tier if org else "starter")

        active_count = (
            db.query(func.count(Memory.id))
            .filter(Memory.org_id == org_id, Memory.status == MemoryStatus.ACTIVE.value)
            .scalar() or 0
        )

        if active_count > plan.monthly_quota_memories:
            grace_dt = ensure_utc(active_downgrade.grace_expires_at)
            days_left = max(0, (grace_dt - datetime.now(timezone.utc)).days)
            reason = (
                f"Memory writes frozen due to plan downgrade. You have {active_count:,} active memories but your plan "
                f"allows {plan.monthly_quota_memories:,}. Grace window expires in {days_left} days."
            )
            return True, reason

        # Organization has cleaned up memories below quota -> auto-resolve downgrade
        active_downgrade.resolved_at = datetime.now(timezone.utc)
        db.commit()
        return False, None

    @classmethod
    def sweep_expired_downgrades(cls, db: Session) -> Dict[str, Any]:
        """Soft-archives oldest memories for any downgrade whose 14-day grace window expired."""
        now = datetime.now(timezone.utc)
        all_unresolved = (
            db.query(PlanDowngrade)
            .filter(PlanDowngrade.resolved_at.is_(None))
            .all()
        )
        expired_downgrades = [
            dg for dg in all_unresolved if ensure_utc(dg.grace_expires_at) <= now
        ]

        total_archived = 0
        resolved_orgs = []

        for dg in expired_downgrades:
            org = db.query(Organization).filter(Organization.id == dg.org_id).first()
            if not org:
                dg.resolved_at = now
                continue

            plan = get_plan(dg.to_tier)
            quota = plan.monthly_quota_memories

            # Get oldest active memories exceeding quota
            active_records = (
                db.query(Memory)
                .filter(Memory.org_id == dg.org_id, Memory.status == MemoryStatus.ACTIVE.value)
                .order_by(Memory.created_at.asc())
                .all()
            )

            excess_count = max(0, len(active_records) - quota)
            if excess_count > 0:
                to_archive = active_records[:excess_count]
                for mem in to_archive:
                    mem.status = MemoryStatus.SOFT_DELETED.value
                    mem.updated_at = now
                total_archived += excess_count

            dg.resolved_at = now
            resolved_orgs.append(dg.org_id)

        db.commit()
        return {
            "resolved_downgrades_count": len(resolved_orgs),
            "total_memories_soft_archived": total_archived,
            "resolved_org_ids": resolved_orgs
        }
