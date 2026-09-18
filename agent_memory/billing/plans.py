"""B2B Subscription Plans, Quotas, Pricing, and Overage Rules."""

from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel


class PlanTier(str, Enum):
    STARTER = "starter"
    GROWTH = "growth"
    SCALE = "scale"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"


class BillableEventType(str, Enum):
    RECALL_QUERY = "RECALL_QUERY"       # Context retrieval / search query
    INGESTION_TURN = "INGESTION_TURN"   # Fact extraction & write turn
    STORAGE_SAMPLE = "STORAGE_SAMPLE"   # Active memories in storage


class PlanDetails(BaseModel):
    tier: PlanTier
    name: str
    description: str
    price_usd_monthly: float
    price_inr_monthly: float
    monthly_quota_memories: int
    monthly_quota_requests: int
    rate_limit_rpm: int
    overage_allowed: bool
    overage_query_rate_usd_per_1k: float
    overage_memory_rate_usd_per_1k: float
    stripe_product_id: str
    stripe_price_id: str
    razorpay_plan_id: str


PLANS: Dict[PlanTier, PlanDetails] = {
    PlanTier.STARTER: PlanDetails(
        tier=PlanTier.STARTER,
        name="Starter (Hobby)",
        description="Ideal for indie hackers, hobbyists, and hackathon prototypes.",
        price_usd_monthly=0.0,
        price_inr_monthly=0.0,
        monthly_quota_memories=5000,
        monthly_quota_requests=25000,
        rate_limit_rpm=60,
        overage_allowed=False,  # Hard stop at quota limit
        overage_query_rate_usd_per_1k=0.0,
        overage_memory_rate_usd_per_1k=0.0,
        stripe_product_id="prod_starter_free",
        stripe_price_id="price_starter_free",
        razorpay_plan_id="plan_starter_free"
    ),
    PlanTier.GROWTH: PlanDetails(
        tier=PlanTier.GROWTH,
        name="Growth (Pro)",
        description="For production AI agents, support bots, and growing startups.",
        price_usd_monthly=49.0,
        price_inr_monthly=4000.0,
        monthly_quota_memories=100000,
        monthly_quota_requests=500000,
        rate_limit_rpm=300,
        overage_allowed=True,
        overage_query_rate_usd_per_1k=0.10,   # $0.10 per 1,000 queries over limit
        overage_memory_rate_usd_per_1k=1.00,  # $1.00 per 1,000 memories over limit
        stripe_product_id="prod_growth_monthly",
        stripe_price_id="price_growth_49usd_mo",
        razorpay_plan_id="plan_growth_4000inr_mo"
    ),
    PlanTier.SCALE: PlanDetails(
        tier=PlanTier.SCALE,
        name="Scale (Team)",
        description="For high-volume multi-agent workflows and customer fleets.",
        price_usd_monthly=249.0,
        price_inr_monthly=20500.0,
        monthly_quota_memories=1000000,
        monthly_quota_requests=5000000,
        rate_limit_rpm=1200,
        overage_allowed=True,
        overage_query_rate_usd_per_1k=0.06,   # $0.06 per 1,000 queries over limit
        overage_memory_rate_usd_per_1k=0.60,  # $0.60 per 1,000 memories over limit
        stripe_product_id="prod_scale_monthly",
        stripe_price_id="price_scale_249usd_mo",
        razorpay_plan_id="plan_scale_20500inr_mo"
    ),
    PlanTier.ENTERPRISE: PlanDetails(
        tier=PlanTier.ENTERPRISE,
        name="Enterprise",
        description="Dedicated database, SOC 2, HIPAA, 99.99% SLA, and custom limits.",
        price_usd_monthly=1999.0,
        price_inr_monthly=165000.0,
        monthly_quota_memories=10000000,
        monthly_quota_requests=50000000,
        rate_limit_rpm=5000,
        overage_allowed=True,
        overage_query_rate_usd_per_1k=0.03,
        overage_memory_rate_usd_per_1k=0.30,
        stripe_product_id="prod_enterprise_custom",
        stripe_price_id="price_enterprise_custom",
        razorpay_plan_id="plan_enterprise_custom"
    )
}


def get_plan(tier_name: Optional[str]) -> PlanDetails:
    """Retrieves plan details with safe fallback to Starter."""
    if not tier_name:
        return PLANS[PlanTier.STARTER]
    try:
        tier_enum = PlanTier(tier_name.lower())
        return PLANS[tier_enum]
    except Exception:
        return PLANS[PlanTier.STARTER]
