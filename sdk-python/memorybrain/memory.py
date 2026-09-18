"""Memory resource handling store, recall, delete, and list operations."""

from typing import Dict, Any, List, Optional, Union
from ._http import HTTPClient


class MemoryResource:
    """Manages memory lifecycle operations on the MemoryBrain platform."""

    def __init__(self, http: HTTPClient):
        self._http = http

    def store(
        self,
        user_id: str,
        content: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        category: str = "FACT",
        metadata: Optional[Dict[str, Any]] = None,
        sync: bool = False
    ) -> Dict[str, Any]:
        """
        Stores a fact, instruction, preference, or conversation turns in long-term memory.

        Args:
            user_id: Stable identifier for the end user or agent.
            content: Direct statement to remember (e.g. "Prefers dark mode").
            messages: Optional chat history turns to extract facts from.
            category: FACT, PREFERENCE, DECISION, or INSTRUCTION.
            metadata: Optional custom JSON metadata dictionary.
            sync: Wait for synchronous ingestion processing (default False).
        """
        payload: Dict[str, Any] = {"user_id": user_id}

        if messages:
            payload["messages"] = messages
        elif content:
            payload["statement"] = content
            payload["category"] = category
            # Also format as turn for robust processing
            payload["messages"] = [
                {"role": "user", "content": content},
                {"role": "assistant", "content": "Acknowledged and stored in memory."}
            ]
        else:
            raise ValueError("Either 'content' or 'messages' must be provided.")

        if metadata:
            payload["metadata"] = metadata

        params = {"sync": "true"} if sync else {}
        return self._http.request("POST", "/v1/memories", params=params, json_body=payload)

    def recall(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        token_limit: int = 300
    ) -> Dict[str, Any]:
        """
        Retrieves relevant memories using multi-factor semantic ranking and Ebbinghaus decay.

        Args:
            user_id: Target user identifier.
            query: Natural language question or search phrase.
            limit: Maximum memories to return.
            token_limit: Maximum prompt token budget to clamp the context to.

        Returns:
            Dict containing 'context' string ready for LLM prompt injection,
            'token_count', and 'memory_count'.
        """
        payload = {
            "user_id": user_id,
            "query": query,
            "limit": limit,
            "token_limit": token_limit
        }
        return self._http.request("POST", "/v1/context", json_body=payload)

    def delete(
        self,
        user_id: str,
        memory_id: Optional[str] = None,
        purge: bool = False
    ) -> Dict[str, Any]:
        """
        Deletes a specific memory or wipes all memories for a user (GDPR).

        Args:
            user_id: Target user identifier.
            memory_id: Optional specific memory ID. If omitted, wipes all memories for user.
            purge: Permanently delete instead of soft-delete (default False).
        """
        if memory_id:
            params = {"purge": "true"} if purge else {}
            return self._http.request("DELETE", f"/v1/memories/{memory_id}", params=params)
        else:
            return self._http.request("DELETE", f"/v1/users/{user_id}/memories")

    def list(
        self,
        user_id: str,
        limit: int = 20,
        category: Optional[str] = None,
        status: str = "ACTIVE",
        cursor: Optional[str] = None
    ) -> Dict[str, Any]:
        """Lists memories for a user with cursor pagination."""
        params = {
            "user_id": user_id,
            "limit": limit,
            "status": status
        }
        if category:
            params["category"] = category
        if cursor:
            params["cursor"] = cursor

        return self._http.request("GET", "/v1/memories", params=params)
