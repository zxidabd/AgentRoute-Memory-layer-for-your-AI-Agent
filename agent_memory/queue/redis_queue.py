"""Production async queue with Redis streams and thread-safe in-memory fallback."""

import json
import uuid
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional
from queue import Queue, Empty
from ..config import settings


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


class MemoryQueue:
    """Manages asynchronous job queueing with Redis and automatic local fallback."""

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or settings.redis_url
        self.queue_name = settings.queue_name
        self.dlq_name = settings.dlq_name
        self._redis = None
        self._local_queue = Queue()
        self._local_dlq = Queue()
        self._job_store: Dict[str, Dict[str, Any]] = {}

        try:
            import redis
            client = redis.Redis.from_url(self.redis_url, socket_timeout=1)
            client.ping()
            self._redis = client
        except Exception:
            # Fall back to thread-safe in-memory queue for offline local dev/testing
            self._redis = None

    def enqueue(self, payload: Dict[str, Any]) -> str:
        """Enqueues a memory ingestion payload and returns an immutable job_id."""
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        envelope = {
            "job_id": job_id,
            "status": JobStatus.QUEUED.value,
            "payload": payload,
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
            "retry_count": 0,
            "error": None
        }

        if self._redis:
            try:
                self._redis.rpush(self.queue_name, json.dumps(envelope))
                self._redis.set(f"job:{job_id}", json.dumps(envelope), ex=86400)
                return job_id
            except Exception:
                pass

        # In-memory queue fallback
        self._job_store[job_id] = envelope
        self._local_queue.put(envelope)
        return job_id

    def re_enqueue(self, envelope: Dict[str, Any]):
        """Re-enqueues an existing job envelope with its current retry count and job_id."""
        job_id = envelope["job_id"]
        envelope["status"] = JobStatus.QUEUED.value
        if self._redis:
            try:
                self._redis.rpush(self.queue_name, json.dumps(envelope))
                self._redis.set(f"job:{job_id}", json.dumps(envelope), ex=86400)
                return
            except Exception:
                pass

        self._job_store[job_id] = envelope
        self._local_queue.put(envelope)

    def dequeue(self, timeout_sec: int = 1) -> Optional[Dict[str, Any]]:
        """Pulls the next job from the queue."""
        if self._redis:
            try:
                raw = self._redis.blpop(self.queue_name, timeout=timeout_sec)
                if raw:
                    envelope = json.loads(raw[1].decode("utf-8"))
                    envelope["status"] = JobStatus.PROCESSING.value
                    self._redis.set(f"job:{envelope['job_id']}", json.dumps(envelope), ex=86400)
                    return envelope
            except Exception:
                pass

        try:
            envelope = self._local_queue.get(timeout=timeout_sec)
            envelope["status"] = JobStatus.PROCESSING.value
            self._job_store[envelope["job_id"]] = envelope
            return envelope
        except Empty:
            return None

    def mark_completed(self, job_id: str, result: Dict[str, Any] = None):
        """Marks a job as successfully processed."""
        if self._redis:
            try:
                raw = self._redis.get(f"job:{job_id}")
                if raw:
                    envelope = json.loads(raw.decode("utf-8"))
                    envelope["status"] = JobStatus.COMPLETED.value
                    envelope["completed_at"] = datetime.now(timezone.utc).isoformat()
                    envelope["result"] = result
                    self._redis.set(f"job:{job_id}", json.dumps(envelope), ex=86400)
                    return
            except Exception:
                pass

        if job_id in self._job_store:
            self._job_store[job_id]["status"] = JobStatus.COMPLETED.value
            self._job_store[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._job_store[job_id]["result"] = result

    def send_to_dlq(self, envelope: Dict[str, Any], error_msg: str):
        """Moves permanently failed job to Dead Letter Queue (DLQ) for forensic review."""
        envelope["status"] = JobStatus.DEAD_LETTER.value
        envelope["error"] = error_msg
        envelope["failed_at"] = datetime.now(timezone.utc).isoformat()

        if self._redis:
            try:
                self._redis.rpush(self.dlq_name, json.dumps(envelope))
                self._redis.set(f"job:{envelope['job_id']}", json.dumps(envelope), ex=604800)  # Keep 7 days
                return
            except Exception:
                pass

        self._local_dlq.put(envelope)
        self._job_store[envelope["job_id"]] = envelope

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Retrieves status and metadata of an enqueued job."""
        if self._redis:
            try:
                raw = self._redis.get(f"job:{job_id}")
                if raw:
                    return json.loads(raw.decode("utf-8"))
            except Exception:
                pass

        if job_id in self._job_store:
            return self._job_store[job_id]

        return {"job_id": job_id, "status": "NOT_FOUND"}


# Global queue singleton
memory_queue = MemoryQueue()
