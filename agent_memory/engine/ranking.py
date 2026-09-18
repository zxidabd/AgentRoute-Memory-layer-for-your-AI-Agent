"""Multi-Factor Relevance Ranking & Ebbinghaus Forgetting Engine.
Ranks memories by combining semantic similarity, importance, recency decay, and access frequency.
"""

import math
from datetime import datetime, timezone
from typing import List, Tuple
from ..config import settings
from ..models.memory import MemoryRecord
from ..models.api import MemoryItemResponse, ContextResponse
from .embeddings import EmbeddingService


class MemoryRanker:
    """Calculates relevance scores, applies decay curves, and formats token-budgeted prompt contexts."""

    def __init__(
        self,
        embedding_service: EmbeddingService = None,
        decay_lambda: float = None,
        threshold: float = None,
    ):
        self.embeddings = embedding_service or EmbeddingService()
        self.decay_lambda = decay_lambda if decay_lambda is not None else settings.decay_rate_lambda
        self.threshold = threshold if threshold is not None else settings.relevance_threshold

    def calculate_decay(self, record: MemoryRecord, now: datetime = None) -> float:
        """
        Calculates Ebbinghaus forgetting decay curve:
        Decay = exp(-lambda * delta_days) * (1.0 + 0.05 * min(access_count, 10))
        """
        now = now or datetime.now(timezone.utc)
        created_at = record.created_at
        if created_at and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        elif not created_at:
            created_at = now
        delta_seconds = (now - created_at).total_seconds()
        delta_days = max(0.0, delta_seconds / 86400.0)

        # Base exponential decay
        base_decay = math.exp(-self.decay_lambda * delta_days)

        # Access reinforcement bonus (human memory gets stronger with repetition)
        reinforcement = 1.0 + 0.05 * min(record.access_count, 10)

        return min(1.0, base_decay * reinforcement)

    def rank(
        self, query: str, memories: List[MemoryRecord], limit: int = 5
    ) -> List[Tuple[MemoryRecord, float]]:
        """
        Scores and ranks active memories against a search query.
        
        Final Score = (0.60 * CosineSimilarity) + (0.20 * Importance) + (0.20 * RecencyDecay)
        """
        if not memories or not query:
            return []

        query_vec = self.embeddings.embed_text(query)
        now = datetime.now(timezone.utc)
        scored: List[Tuple[MemoryRecord, float]] = []

        for mem in memories:
            if not mem.is_active:
                continue

            # 1. Semantic Similarity (0.0 to 1.0)
            mem_vec = mem.embedding or self.embeddings.embed_text(mem.statement)
            sim = max(0.0, self.embeddings.cosine_similarity(query_vec, mem_vec))

            # Off-topic gate: If similarity is too low, do not retrieve regardless of importance
            if sim < 0.15:
                continue

            # 2. Importance (0.0 to 1.0)
            imp = max(0.0, min(1.0, mem.importance))

            # 3. Recency & Access Decay (0.0 to 1.0)
            decay = self.calculate_decay(mem, now)

            # Combined multi-factor weighted score
            final_score = (0.60 * sim) + (0.20 * imp) + (0.20 * decay)

            if final_score >= self.threshold or sim > 0.30:
                scored.append((mem, final_score))

        # Sort descending by final score
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def build_context_string(
        self, user_id: str, ranked_memories: List[Tuple[MemoryRecord, float]], token_limit: int = 300
    ) -> ContextResponse:
        """
        Converts top ranked memories into a clean prompt string clamped strictly within token budget.
        """
        if not ranked_memories:
            return ContextResponse(
                user_id=user_id,
                context="",
                token_count=0,
                memory_count=0
            )

        lines: List[str] = []
        estimated_tokens = 0

        for mem, score in ranked_memories:
            line = f"• {mem.statement}"
            # Fast token approximation (1 token ≈ 4 characters in English)
            line_tokens = max(1, len(line) // 4)

            if estimated_tokens + line_tokens > token_limit:
                break  # Enforce hard token budget clamp

            lines.append(line)
            estimated_tokens += line_tokens

        context_str = "\n".join(lines)
        return ContextResponse(
            user_id=user_id,
            context=context_str,
            token_count=estimated_tokens,
            memory_count=len(lines)
        )
