"""
Usage Health Score & Proactive Churn Prediction Engine.
Monitors rolling query volume and flags accounts with sharp utilization drops (>40%).
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from ..models.db_models import Organization, UsageEvent, Memory


class UsageHealthScoreEngine:
    """
    Computes tenant health score (0-100) and churn risk status.
    Compares 7-day rolling activity against the preceding 30-day baseline.
    """

    @classmethod
    def calculate_org_health(cls, db: Session, org_id: str) -> Dict[str, Any]:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            return {"error": f"Organization {org_id} not found"}

        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)
        thirty_seven_days_ago = now - timedelta(days=37)

        # 1. Queries/Events in last 7 days
        count_7d = (
            db.query(UsageEvent)
            .filter(UsageEvent.org_id == org_id, UsageEvent.timestamp >= seven_days_ago)
            .count()
        )

        # 2. Queries/Events in the preceding 30 days
        count_prior_30d = (
            db.query(UsageEvent)
            .filter(
                UsageEvent.org_id == org_id,
                UsageEvent.timestamp >= thirty_seven_days_ago,
                UsageEvent.timestamp < seven_days_ago,
            )
            .count()
        )

        # In case usage_events is sparse in testing, fallback to Memory activity
        if count_7d == 0 and count_prior_30d == 0:
            mem_count_7d = (
                db.query(Memory)
                .filter(Memory.org_id == org_id, Memory.created_at >= seven_days_ago)
                .count()
            )
            mem_count_prior = (
                db.query(Memory)
                .filter(
                    Memory.org_id == org_id,
                    Memory.created_at >= thirty_seven_days_ago,
                    Memory.created_at < seven_days_ago,
                )
                .count()
            )
            count_7d = mem_count_7d
            count_prior_30d = mem_count_prior

        baseline_weekly = count_prior_30d / 4.0 if count_prior_30d > 0 else 0.0

        # Classification logic
        if count_7d == 0 and baseline_weekly == 0:
            status = "INACTIVE"
            health_score = 10
            churn_risk = "HIGH"
            reason = "Zero recorded queries or memory activity in the past 37 days."
        elif baseline_weekly == 0 and count_7d > 0:
            status = "HEALTHY"
            health_score = 95
            churn_risk = "LOW"
            reason = f"New active account with {count_7d} events this week."
        else:
            ratio = count_7d / baseline_weekly
            drop_pct = round(max(0.0, (1.0 - ratio) * 100), 1)

            if ratio >= 0.9:
                status = "HEALTHY"
                health_score = min(100, int(85 + (ratio * 10)))
                churn_risk = "LOW"
                reason = f"Stable or growing activity (Ratio: {ratio:.2f}x of baseline)."
            elif ratio >= 0.6:
                status = "NEUTRAL"
                health_score = int(60 + (ratio * 20))
                churn_risk = "MEDIUM"
                reason = f"Slight activity decline of {drop_pct}% vs baseline."
            else:
                status = "AT_RISK_OF_CHURN"
                health_score = max(15, int(ratio * 50))
                churn_risk = "CRITICAL"
                reason = f"Severe activity drop of {drop_pct}% (>40% threshold breach). Immediate check-in required."

        return {
            "org_id": org_id,
            "org_name": org.name,
            "tier": org.tier,
            "subscription_status": org.subscription_status,
            "health_score": health_score,
            "status": status,
            "churn_risk": churn_risk,
            "metrics": {
                "events_last_7d": count_7d,
                "baseline_weekly_events": round(baseline_weekly, 1),
                "activity_ratio": round(count_7d / baseline_weekly, 2) if baseline_weekly > 0 else 1.0,
            },
            "reason": reason,
            "action_required": churn_risk in ("MEDIUM", "CRITICAL"),
            "evaluated_at": now.isoformat(),
        }

    @classmethod
    def calculate_all_org_health_scores(cls, db: Session) -> Dict[str, Any]:
        """Scans all registered tenants and summarizes organization health portfolio."""
        orgs = db.query(Organization).all()
        results = []
        summary = {
            "total_evaluated": len(orgs),
            "healthy": 0,
            "neutral": 0,
            "at_risk_of_churn": 0,
            "inactive": 0,
        }
        at_risk_list = []

        for org in orgs:
            res = cls.calculate_org_health(db, org.id)
            results.append(res)
            s = res["status"].lower()
            if s == "healthy":
                summary["healthy"] += 1
            elif s == "neutral":
                summary["neutral"] += 1
            elif s == "at_risk_of_churn":
                summary["at_risk_of_churn"] += 1
                at_risk_list.append(res)
            elif s == "inactive":
                summary["inactive"] += 1

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "at_risk_accounts": at_risk_list,
            "all_accounts": results,
        }
