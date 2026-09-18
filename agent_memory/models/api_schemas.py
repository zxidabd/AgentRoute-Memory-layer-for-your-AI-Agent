"""Standardized API request/response schemas, pagination envelopes, and RFC 7807 error formats."""

from datetime import datetime
from typing import Generic, TypeVar, List, Optional, Any, Dict
from pydantic import BaseModel, Field

T = TypeVar("T")


class APIErrorDetail(BaseModel):
    """RFC 7807-compliant structured error format."""
    code: str = Field(..., description="Machine-readable error code (e.g. 'UNAUTHORIZED', 'NOT_FOUND')")
    message: str = Field(..., description="Human-readable explanation")
    field: Optional[str] = Field(default=None, description="Request parameter that caused the error")


class ResponseMeta(BaseModel):
    """Metadata envelope attached to all API responses."""
    request_id: str
    timestamp: str
    tenant_id: Optional[str] = None
    count: Optional[int] = None
    next_cursor: Optional[str] = None


class StandardResponse(BaseModel, Generic[T]):
    """Standardized production API response envelope."""
    data: Optional[T] = None
    error: Optional[APIErrorDetail] = None
    meta: ResponseMeta


class IngestJobResponse(BaseModel):
    job_id: str
    status: str
    enqueued_at: str
    message: str


class MemoryItem(BaseModel):
    id: str
    statement: str
    category: str
    entity: str
    attribute: Optional[str] = None
    value: Optional[str] = None
    status: str
    version: int
    importance_score: float
    confidence_score: float
    created_at: str
    valid_from: str
    valid_until: Optional[str] = None


class PaginatedMemories(BaseModel):
    memories: List[MemoryItem]
    total_count: int
    has_more: bool
    next_cursor: Optional[str] = None


class MemoryPatchRequest(BaseModel):
    statement: Optional[str] = None
    importance_score: Optional[float] = None
    reason: Optional[str] = "Manual correction"
