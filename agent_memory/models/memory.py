"""Pydantic data models for facts, memory records, and extraction results."""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
import uuid


class MemoryCategory(str, Enum):
    PREFERENCE = "PREFERENCE"    # User likes/dislikes, habits, coding styles
    FACT = "FACT"                # Identity, location, biography, environment
    DECISION = "DECISION"        # Project decisions, architecture choices, approved plans
    CONSTRAINT = "CONSTRAINT"    # Hard limitations (allergies, budgets, system restrictions)
    EPISODIC = "EPISODIC"        # Milestones, past actions, completed tasks


class Fact(BaseModel):
    """An atomic extracted proposition about the user or task."""
    statement: str = Field(..., description="Crisp, clear sentence stating the fact (e.g. 'User prefers TypeScript over JavaScript')")
    category: MemoryCategory = Field(default=MemoryCategory.FACT, description="Category of the memory")
    entity: str = Field(default="user", description="The subject of the fact (e.g. 'user', 'database', 'project')")
    attribute: str = Field(default="", description="The specific property (e.g. 'preferred_language', 'location', 'tech_stack')")
    value: str = Field(default="", description="The value of the attribute (e.g. 'TypeScript', 'Tokyo', 'FastAPI')")
    importance: float = Field(default=0.7, ge=0.0, le=1.0, description="Significance score from 0.0 (trivial) to 1.0 (vital)")
    temporal_anchor: Optional[str] = Field(default=None, description="Real-world date this fact applies to (e.g. '2026-09-12')")


class ExtractionResult(BaseModel):
    """Result returned by the Gemini 2.5 Flash fact extractor."""
    facts: List[Fact] = Field(default_factory=list, description="Extracted atomic facts")
    has_meaningful_content: bool = Field(default=True, description="False if conversation was 100% small talk or filler")
    summary_of_interaction: str = Field(default="", description="One-line summary of what took place")


class MemoryRecord(BaseModel):
    """The fully persisted memory record in storage with audit and vector metadata."""
    id: str = Field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:12]}")
    tenant_id: str = Field(default="default_tenant")
    user_id: str = Field(...)
    agent_id: Optional[str] = Field(default=None)
    statement: str = Field(...)
    category: str = Field(default="FACT")
    entity: str = Field(default="user")
    attribute: str = Field(default="")
    value: str = Field(default="")
    importance: float = Field(default=0.7)
    access_count: int = Field(default=0)
    is_active: bool = Field(default=True)
    superseded_by: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed_at: Optional[datetime] = Field(default=None)
    embedding: Optional[List[float]] = Field(default=None)
