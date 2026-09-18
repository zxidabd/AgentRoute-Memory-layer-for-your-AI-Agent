"""Production ORM models for 5-Tier Tenancy, Memory Lifecycle, and Metering."""

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class MemoryStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"
    SOFT_DELETED = "SOFT_DELETED"


class SourceType(str, Enum):
    DIRECT_USER = "DIRECT_USER"
    INFERRED = "INFERRED"
    TOOL_OUTPUT = "TOOL_OUTPUT"
    EXTERNAL_SYNC = "EXTERNAL_SYNC"


class Organization(Base):
    """Tier 1: The paying business entity."""
    __tablename__ = "organizations"

    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    tier = Column(String(50), default="starter")          # starter, growth, scale, enterprise
    subscription_status = Column(String(50), default="active") # active, trialing, past_due, canceled, unpaid
    billing_gateway = Column(String(50), default="stripe")     # stripe, razorpay
    stripe_customer_id = Column(String(128), nullable=True, index=True)
    stripe_subscription_id = Column(String(128), nullable=True, index=True)
    razorpay_customer_id = Column(String(128), nullable=True, index=True)
    razorpay_subscription_id = Column(String(128), nullable=True, index=True)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end = Column(Boolean, default=False)
    overage_billing_enabled = Column(Boolean, default=True)
    past_due_since = Column(DateTime(timezone=True), nullable=True)
    monthly_quota_memories = Column(Integer, default=5000)
    monthly_quota_requests = Column(Integer, default=25000)
    clerk_org_id = Column(String(128), unique=True, nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    projects = relationship("Project", back_populates="organization", cascade="all, delete-orphan")
    api_keys = relationship("APIKey", back_populates="organization", cascade="all, delete-orphan")
    memberships = relationship("Membership", back_populates="organization", cascade="all, delete-orphan")
    invitations = relationship("Invitation", back_populates="organization", cascade="all, delete-orphan")


class Project(Base):
    """Tier 2: Environment or sub-application (e.g. 'SupportBot-Prod')."""
    __tablename__ = "projects"

    id = Column(String(64), primary_key=True)
    org_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    environment = Column(String(50), default="dev")  # dev, staging, prod
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", back_populates="projects")
    memories = relationship("Memory", back_populates="project", cascade="all, delete-orphan")
    api_keys = relationship("APIKey", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_project_org_name_env", "org_id", "name", "environment", unique=True),
    )


class UserAccount(Base):
    """Native developer user account with email confirmation & password authentication."""
    __tablename__ = "user_accounts"

    id = Column(String(64), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)
    is_verified = Column(Boolean, default=False)
    verification_code = Column(String(32), nullable=True)
    verification_code_expires_at = Column(DateTime(timezone=True), nullable=True)
    reset_token = Column(String(128), nullable=True, index=True)
    reset_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Membership(Base):
    """Users & membership/roles within an organization."""
    __tablename__ = "memberships"


    id = Column(String(64), primary_key=True)
    org_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    clerk_user_id = Column(String(128), nullable=False, index=True)
    email = Column(String(255), nullable=True)
    name = Column(String(255), nullable=True)
    role = Column(String(50), default="developer")  # owner, developer, viewer
    invited_by_id = Column(String(64), ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", back_populates="memberships")

    __table_args__ = (
        Index("ix_membership_org_clerk_user", "org_id", "clerk_user_id", unique=True),
    )


class Invitation(Base):
    """Team invitation tokens for joining an organization."""
    __tablename__ = "invitations"

    id = Column(String(64), primary_key=True)
    org_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    role = Column(String(50), default="developer")  # owner, developer, viewer
    token = Column(String(128), unique=True, nullable=False, index=True)
    invited_by_id = Column(String(64), ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", back_populates="invitations")


class APIKey(Base):
    """Hashed and scoped API keys, bound to a specific Project environment."""
    __tablename__ = "api_keys"

    id = Column(String(64), primary_key=True)
    org_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    key_prefix = Column(String(64), default="mb_live")    # e.g. "mb_live_a1b2"
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    key_hint = Column(String(32), nullable=False)
    environment = Column(String(50), default="dev")       # dev, staging, prod
    created_by_id = Column(String(64), nullable=True)
    role = Column(String(50), default="developer")
    scopes_json = Column(Text, default="[]")
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization", back_populates="api_keys")
    project = relationship("Project", back_populates="api_keys")


class Memory(Base):
    """Tier 5: Core Memory record with full lifecycle, encryption, and scores."""
    __tablename__ = "memories"

    id = Column(String(64), primary_key=True)
    org_id = Column(String(64), nullable=False, index=True)
    project_id = Column(String(64), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    agent_id = Column(String(128), nullable=True, index=True)
    user_id = Column(String(128), nullable=False, index=True)

    # Core Statement (AES-256 encrypted at rest)
    statement = Column(Text, nullable=False)
    category = Column(String(50), default="FACT", nullable=False)
    entity = Column(String(128), default="user", index=True)
    attribute = Column(String(128), nullable=True, index=True)
    value = Column(String(255), nullable=True)

    # Bi-Temporal Lifecycle
    valid_from = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    valid_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)

    # Scores & Lineage
    status = Column(String(50), default=MemoryStatus.ACTIVE.value, index=True)
    version = Column(Integer, default=1)
    confidence_score = Column(Float, default=0.90)
    importance_score = Column(Float, default=0.70)
    freshness_score = Column(Float, default=1.00)
    access_count = Column(Integer, default=0)
    superseded_by_id = Column(String(64), nullable=True)
    source_type = Column(String(50), default=SourceType.DIRECT_USER.value)
    source_event_id = Column(String(128), nullable=True)

    # Vector Embeddings (stored as JSON string in SQLite / vector(768) in PostgreSQL)
    embedding_json = Column(Text, nullable=True)

    project = relationship("Project", back_populates="memories")
    versions = relationship("MemoryVersion", back_populates="memory", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_mem_tenant_user_active", "org_id", "user_id", "status"),
        Index("ix_mem_entity_attr", "entity", "attribute"),
    )


class MemoryVersion(Base):
    """Immutable ledger of all memory edits and supersessions for auditing & rollback."""
    __tablename__ = "memory_versions"

    id = Column(String(64), primary_key=True)
    memory_id = Column(String(64), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    statement = Column(Text, nullable=False)
    status = Column(String(50), nullable=False)
    superseded_by_id = Column(String(64), nullable=True)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    memory = relationship("Memory", back_populates="versions")


class UsageEvent(Base):
    """Usage metering table for billing and quota enforcement."""
    __tablename__ = "usage_events"

    id = Column(String(64), primary_key=True)
    org_id = Column(String(64), nullable=False, index=True)
    project_id = Column(String(64), nullable=True, index=True)
    endpoint = Column(String(128), nullable=False)
    event_type = Column(String(64), default="RECALL_QUERY", index=True)
    units_billed = Column(Integer, default=1)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    latency_ms = Column(Float, default=0.0)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class Webhook(Base):
    """Customer outbound webhook subscription."""
    __tablename__ = "webhooks"

    id = Column(String(64), primary_key=True)
    org_id = Column(String(64), nullable=False, index=True)
    url = Column(String(512), nullable=False)
    secret_key = Column(String(128), nullable=False)  # For HMAC-SHA256 signature verification
    events_json = Column(Text, default='["memory.created", "memory.superseded", "user.deleted"]')
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PlanDowngrade(Base):
    """Tracks 14-day grace window, write freezing, and auto-archiving on tier demotions."""
    __tablename__ = "plan_downgrades"

    id = Column(String(64), primary_key=True)
    org_id = Column(String(64), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    from_tier = Column(String(50), nullable=False)
    to_tier = Column(String(50), nullable=False)
    effective_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    grace_expires_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)  # Null until re-upgraded or soft-archived
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class StripeMeterSubmission(Base):
    """Guarantees idempotent submission of billable events to the Stripe Meter Events API."""
    __tablename__ = "stripe_meter_submissions"

    usage_event_id = Column(String(64), ForeignKey("usage_events.id", ondelete="CASCADE"), primary_key=True)
    org_id = Column(String(64), nullable=False, index=True)
    meter_event_name = Column(String(128), nullable=False)
    units_submitted = Column(Integer, default=1)
    stripe_meter_event_id = Column(String(128), nullable=True)
    submitted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AssetType(str, Enum):
    WAREHOUSE = "WAREHOUSE"
    DATABASE = "DATABASE"
    SCHEMA = "SCHEMA"
    TABLE = "TABLE"
    VIEW = "VIEW"
    PIPELINE = "PIPELINE"


class AssetHealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    STALE = "STALE"
    FAILING = "FAILING"
    DEPRECATED = "DEPRECATED"


class LineageEdgeType(str, Enum):
    TRANSFORMS_INTO = "TRANSFORMS_INTO"
    JOINS_WITH = "JOINS_WITH"
    FEEDS_DASHBOARD = "FEEDS_DASHBOARD"
    PIPELINE_DEPENDENCY = "PIPELINE_DEPENDENCY"


class DataAsset(Base):
    """Enterprise Data Asset: Tables, Views, Warehouses, Pipelines, and Schemas."""
    __tablename__ = "data_assets"

    id = Column(String(64), primary_key=True)
    org_id = Column(String(64), nullable=False, index=True)
    project_id = Column(String(64), nullable=True, index=True)
    asset_type = Column(String(50), default=AssetType.TABLE.value, index=True)
    platform = Column(String(50), default="snowflake", index=True)
    name = Column(String(255), nullable=False, index=True)
    fqn = Column(String(512), nullable=False, index=True)
    description = Column(Text, nullable=True)
    columns_json = Column(Text, default="[]")
    owner = Column(String(255), nullable=True)
    is_certified = Column(Boolean, default=False, index=True)
    certified_by = Column(String(255), nullable=True)
    health_status = Column(String(50), default=AssetHealthStatus.HEALTHY.value, index=True)
    freshness_timestamp = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(Text, default="{}")
    embedding_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_synced_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_data_asset_org_fqn", "org_id", "fqn", unique=True),
        Index("ix_data_asset_org_platform_type", "org_id", "platform", "asset_type"),
    )


class BusinessMetric(Base):
    """Enterprise Business Metric: Certified KPIs, SQL expressions, and join paths."""
    __tablename__ = "business_metrics"

    id = Column(String(64), primary_key=True)
    org_id = Column(String(64), nullable=False, index=True)
    project_id = Column(String(64), nullable=True, index=True)
    name = Column(String(128), nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    definition = Column(Text, nullable=False)
    formula = Column(Text, nullable=True)
    sql_expression = Column(Text, nullable=True)
    primary_table_fqn = Column(String(512), nullable=True, index=True)
    join_recipe = Column(Text, nullable=True)
    is_certified = Column(Boolean, default=False, index=True)
    steward = Column(String(255), nullable=True)
    tags_json = Column(Text, default="[]")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_metric_org_name", "org_id", "name", unique=True),
    )


class DataLineageEdge(Base):
    """Lineage dependency edge connecting upstream sources to downstream assets."""
    __tablename__ = "data_lineage_edges"

    id = Column(String(64), primary_key=True)
    org_id = Column(String(64), nullable=False, index=True)
    upstream_asset_fqn = Column(String(512), nullable=False, index=True)
    downstream_asset_fqn = Column(String(512), nullable=False, index=True)
    edge_type = Column(String(50), default=LineageEdgeType.TRANSFORMS_INTO.value)
    transformation_logic = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_lineage_org_upstream", "org_id", "upstream_asset_fqn"),
        Index("ix_lineage_org_downstream", "org_id", "downstream_asset_fqn"),
    )
