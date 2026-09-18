"""
GTM & Platform Funnel Analytics API Routes.
Provides real-time launch metrics, conversion rates, and activation telemetry.
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ...database import get_db_session
from ...analytics.gtm_metrics import collect_gtm_baseline_metrics
from ...analytics.health_score import UsageHealthScoreEngine
from ...auth.rbac_middleware import AuthContext, require_permission

router = APIRouter(prefix="/v1", tags=["GTM & Growth Analytics (v1)"])


@router.get(
    "/analytics/gtm/baseline",
    summary="Retrieve real-time GTM launch funnel and conversion baseline",
    description="Returns organization signups, active keys, TTFM latency, activation rate, and readiness verification checklist."
)
def get_gtm_baseline(
    context: AuthContext = Depends(require_permission("projects:read")),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    return collect_gtm_baseline_metrics(db)


@router.get(
    "/analytics/orgs/health-scores",
    summary="Retrieve tenant usage health scores and proactive churn risk audit",
    description="Analyzes rolling 7-day query activity against 30-day baseline to flag at-risk accounts."
)
def get_org_health_scores(
    context: AuthContext = Depends(require_permission("projects:read")),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    return UsageHealthScoreEngine.calculate_all_org_health_scores(db)
