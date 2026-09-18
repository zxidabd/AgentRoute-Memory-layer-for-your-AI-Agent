"""Universal Developer Client SDK for AI Agents.
Give ANY AI agent (OpenAI, Claude, Gemini, Llama, LangChain, etc.) persistent memory in 2 API calls.
"""

import json
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional
from ..storage.sqlite_store import SQLiteMemoryStore
from ..engine.sanitizer import sanitize_text
from ..engine.extractor import FactExtractor
from ..engine.resolver import ConflictResolver
from ..engine.embeddings import EmbeddingService
from ..engine.ranking import MemoryRanker
from ..models.memory import MemoryRecord


class MemoryClient:
    """
    Plug-and-play client for the Agent Memory Platform.
    
    Usage:
        from agent_memory import MemoryClient
        
        memory = MemoryClient(api_key="mem_live_...")
        
        # 1. Fetch relevant memory context before prompting your LLM:
        context = memory.get_context(user_id="user_123", query="How should I structure my app?")
        
        # 2. Record conversation turns asynchronously:
        memory.add(user_id="user_123", messages=[...])
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000",
        local_mode: bool = False
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.local_mode = local_mode

        # If running in local in-process mode (for instant testing without running server)
        if self.local_mode:
            self._store = SQLiteMemoryStore()
            self._extractor = FactExtractor()
            self._embeddings = EmbeddingService()
            self._resolver = ConflictResolver(self._embeddings)
            self._ranker = MemoryRanker(self._embeddings)
            self._tenant_id = "local_tenant"

    def get_context(
        self,
        user_id: str,
        query: str,
        token_limit: int = 300,
        limit: int = 5
    ) -> str:
        """
        Retrieves a clean, ready-to-inject bulleted string of facts for system prompts.
        Guaranteed to stay within the requested token_limit.
        """
        if self.local_mode:
            active = self._store.get_active_memories(self._tenant_id, user_id)
            ranked = self._ranker.rank(query, active, limit=limit)
            for m, _ in ranked:
                self._store.touch_memory(m.id)
            resp = self._ranker.build_context_string(user_id, ranked, token_limit=token_limit)
            return resp.context

        payload = {
            "user_id": user_id,
            "query": query,
            "token_limit": token_limit,
            "limit": limit
        }
        res = self._post("/v1/context", payload)
        return res.get("context", "")

    def add(
        self,
        user_id: str,
        messages: List[Dict[str, str]],
        agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Asynchronously sends conversation messages for fact extraction & conflict resolution.
        """
        if self.local_mode:
            sanitized_messages = []
            for m in messages:
                clean, _ = sanitize_text(m.get("content", ""))
                sanitized_messages.append({"role": m.get("role", "user"), "content": clean})

            extraction = self._extractor.extract(sanitized_messages)
            if not extraction.facts:
                return {"status": "ignored", "facts_extracted": 0}

            existing = self._store.get_active_memories(self._tenant_id, user_id)
            saved = []
            for f in extraction.facts:
                conflicts = self._resolver.detect_conflicts(f, existing)
                embed = self._embeddings.embed_text(f.statement)
                rec = MemoryRecord(
                    tenant_id=self._tenant_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    statement=f.statement,
                    category=f.category.value,
                    entity=f.entity,
                    attribute=f.attribute,
                    value=f.value,
                    importance=f.importance,
                    embedding=embed
                )
                new_id = self._store.add_memory(rec)
                saved.append(rec)
                for old_mem, _ in conflicts:
                    self._store.mark_superseded(old_mem.id, new_id)

            return {
                "status": "recorded",
                "facts_extracted": len(saved),
                "facts": [r.statement for r in saved]
            }

        payload = {
            "user_id": user_id,
            "messages": messages,
            "agent_id": agent_id
        }
        return self._post("/v1/memories", payload)

    def search(
        self,
        user_id: str,
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Searches memories and returns scored memory items."""
        if self.local_mode:
            active = self._store.get_active_memories(self._tenant_id, user_id)
            ranked = self._ranker.rank(query, active, limit=limit)
            return [
                {
                    "id": m.id,
                    "statement": m.statement,
                    "category": m.category,
                    "score": round(score, 3)
                }
                for m, score in ranked
            ]

        payload = {"user_id": user_id, "query": query, "limit": limit}
        res = self._post("/v1/memories/search", payload)
        return res.get("memories", [])

    def get_profile(self, user_id: str) -> Dict[str, Any]:
        """Retrieves permanent user profile statements."""
        if self.local_mode:
            active = self._store.get_active_memories(self._tenant_id, user_id)
            return {
                "user_id": user_id,
                "total_memories": len(active),
                "statements": [m.statement for m in active]
            }
        return self._get(f"/v1/users/{user_id}/profile")

    def delete_user(self, user_id: str) -> bool:
        """GDPR Right to be Forgotten: Permanently deletes all memories for a user."""
        if self.local_mode:
            deleted = self._store.delete_user_memories(self._tenant_id, user_id)
            return deleted > 0
        res = self._delete(f"/v1/users/{user_id}")
        return res.get("status") == "deleted"

    # -------------------------------------------------------------
    # Low-level Zero-Dependency HTTP Transport
    # -------------------------------------------------------------

    def _post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise RuntimeError(f"Memory API Error ({e.code}): {error_body}")

    def _get(self, endpoint: str) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def _delete(self, endpoint: str) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            method="DELETE"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
