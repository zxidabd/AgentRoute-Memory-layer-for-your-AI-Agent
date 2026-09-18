"""MemoryBrain Python Client."""

import os
from typing import Optional, Dict, Any, List
from ._http import HTTPClient
from .memory import MemoryResource
from .assets import DataAssetResource, MetricResource


class MemoryBrain:
    """
    Main entry point for the MemoryBrain Python SDK.

    Usage:
        from memorybrain import MemoryBrain

        mb = MemoryBrain(api_key="mb_live_...")
        mb.store(user_id="alice", content="Prefers TypeScript")
        context = mb.recall(user_id="alice", query="frontend language")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 10.0,
        max_retries: int = 3
    ):
        key = api_key or os.getenv("MEMORYBRAIN_API_KEY")
        if not key:
            raise ValueError(
                "MemoryBrain API key required. Pass api_key='mb_...' or set the MEMORYBRAIN_API_KEY environment variable."
            )

        self._http = HTTPClient(
            api_key=key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries
        )
        self.memories = MemoryResource(self._http)
        self.assets = DataAssetResource(self._http)
        self.metrics = MetricResource(self._http)

    # -------------------------------------------------------------
    # Top-Level 2-Line Ergonomic Convenience Shortcuts
    # -------------------------------------------------------------

    def store(
        self,
        user_id: str,
        content: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        category: str = "FACT",
        metadata: Optional[Dict[str, Any]] = None,
        sync: bool = False
    ) -> Dict[str, Any]:
        """Convenience alias for mb.memories.store()."""
        return self.memories.store(
            user_id=user_id,
            content=content,
            messages=messages,
            category=category,
            metadata=metadata,
            sync=sync
        )

    def recall(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        token_limit: int = 300
    ) -> Dict[str, Any]:
        """Convenience alias for mb.memories.recall()."""
        return self.memories.recall(
            user_id=user_id,
            query=query,
            limit=limit,
            token_limit=token_limit
        )

    def delete(
        self,
        user_id: str,
        memory_id: Optional[str] = None,
        purge: bool = False
    ) -> Dict[str, Any]:
        """Convenience alias for mb.memories.delete()."""
        return self.memories.delete(user_id=user_id, memory_id=memory_id, purge=purge)
