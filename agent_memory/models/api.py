"""API request and response schemas for memory retrieval and ingestion."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class IngestMemoryRequest(BaseModel):
    """Payload sent by agent when recording conversational messages."""
    user_id: str = Field(..., description="Unique end-user identifier")
    messages: List[Dict[str, str]] = Field(..., description="Conversation messages [{'role': 'user', 'content': '...'}]")
    agent_id: Optional[str] = Field(default=None, description="Optional agent identifier")


class SearchMemoryRequest(BaseModel):
    """Payload sent by agent when searching for memories."""
    user_id: str = Field(..., description="Unique end-user identifier")
    query: str = Field(..., description="The question or topic to search memories for")
    limit: int = Field(default=5, ge=1, le=20, description="Max number of memories to return")
    token_limit: int = Field(default=300, ge=50, le=2000, description="Max token budget for prompt injection")


class MemoryItemResponse(BaseModel):
    """A single retrieved memory item with scoring metrics."""
    id: str
    statement: str
    category: str
    importance: float
    relevance_score: float
    created_at: str


class SearchResponse(BaseModel):
    """Search results with relevance scores."""
    memories: List[MemoryItemResponse]
    query: str
    total_found: int


class ContextResponse(BaseModel):
    """Ready-to-inject prompt context string clamped to token budget."""
    user_id: str
    context: str = Field(..., description="Formatted string ready to paste directly into LLM system prompt")
    token_count: int = Field(..., description="Estimated token count of the context string")
    memory_count: int = Field(..., description="Number of memories included")
