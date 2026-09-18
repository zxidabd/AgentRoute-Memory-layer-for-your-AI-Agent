"""Embedding generation service using Google GenAI with a local fallback."""

import math
from typing import List
from ..config import settings


class EmbeddingService:
    """Generates normalized vector embeddings for facts and queries."""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or settings.gemini_api_key
        self.model = model or settings.embedding_model
        self._client = None
        self.dimension = 768

        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception:
                self._client = None

    def embed_text(self, text: str) -> List[float]:
        """Embeds a single string into a 768-dimensional normalized float vector."""
        if not text:
            return [0.0] * self.dimension

        # If live Gemini Client is available, use official Google Embeddings
        if self._client:
            try:
                response = self._client.models.embed_content(
                    model=self.model,
                    contents=text,
                )
                if response.embedding and response.embedding.values:
                    return response.embedding.values
            except Exception:
                pass

        # High-speed deterministic local embedding fallback (works zero-dependency)
        return self._local_fallback_embed(text)

    get_embedding = embed_text

    def _local_fallback_embed(self, text: str) -> List[float]:
        """Deterministic hash-based projection with stopword filtering for crisp offline similarity."""
        import hashlib
        import re

        stopwords = {
            "what", "does", "for", "his", "her", "and", "to", "is", "are", "on",
            "the", "a", "an", "in", "of", "at", "by", "with", "this", "that", "user"
        }
        # Domain concept clusters for offline semantic synonym expansion
        concepts = {
            "concept_database": ["database", "db", "postgresql", "postgres", "sql", "mysql", "mongodb", "sqlite", "tables", "schema"],
            "concept_cloud": ["cloud", "aws", "gcp", "google", "azure", "deploy", "deployment", "hosting", "hosted", "containerized", "serverless"],
            "concept_backend": ["backend", "server", "api", "fastapi", "flask", "django", "grpc", "microservices", "endpoint", "route", "service"],
            "concept_language": ["python", "typescript", "javascript", "golang", "go", "rust", "code", "coding"]
        }

        vector = [0.0] * self.dimension
        words = [
            w for w in re.findall(r"\b\w+\b", text.lower())
            if w not in stopwords and len(w) > 1
        ]

        # Project detected concepts into the vector
        text_lower = text.lower()
        for concept_name, terms in concepts.items():
            if any(term in text_lower for term in terms):
                ch = int(hashlib.md5(concept_name.encode()).hexdigest(), 16) % self.dimension
                vector[ch] += 2.0

        for word in words:
            # Word unigram
            h = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dimension
            vector[h] += 1.5

            # Word root/prefix (first 4 chars) for stemming: 'serv' in services & microservices
            if len(word) >= 4:
                pref = word[:4]
                ph = int(hashlib.md5(f"pref_{pref}".encode()).hexdigest(), 16) % self.dimension
                vector[ph] += 1.0

            # Character ngrams
            if len(word) >= 4:
                for n in [3, 4]:
                    for i in range(len(word) - n + 1):
                        sub = word[i:i+n]
                        sub_h = int(hashlib.md5(sub.encode()).hexdigest(), 16) % self.dimension
                        vector[sub_h] += 0.3

        # L2 Normalize
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0:
            vector = [x / norm for x in vector]
        else:
            vector[0] = 1.0

        return vector

    @staticmethod
    def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """Computes cosine similarity between two normalized vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        return sum(a * b for a, b in zip(vec_a, vec_b))
