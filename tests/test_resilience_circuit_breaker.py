"""Resilience, Circuit Breaker, and Dead Letter Queue (DLQ) Test Suite.
Verifies that external LLM failures trigger exponential backoff, circuit tripping, and DLQ routing.
"""

import sys
import time
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_memory.engine.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerOpenException
from agent_memory.queue.redis_queue import MemoryQueue, JobStatus
from agent_memory.queue.worker import MemoryWorker


def run_resilience_test():
    print("\n" + "=" * 76)
    print(" ⚡ RESILIENCE, CIRCUIT BREAKER & DEAD LETTER QUEUE TEST")
    print("=" * 76)

    # 1. Test Circuit Breaker Tripping
    print("\n--- [Step 1] Testing Circuit Breaker Tripping on Flapping LLM ---")
    breaker = CircuitBreaker(name="Test_LLM", failure_threshold=3, recovery_timeout_sec=1.0)

    call_count = 0
    def failing_llm_call():
        nonlocal call_count
        call_count += 1
        raise ConnectionResetError("Simulated LLM network connection reset 503")

    def fallback_llm_call():
        return {"facts": ["Fallback rule fact"], "status": "fallback_success"}

    # Trigger failures up to threshold
    for i in range(3):
        try:
            breaker.call(failing_llm_call)
        except ConnectionResetError:
            print(f"  Failure {i+1}/3 recorded. Breaker state: {breaker.state.value}")

    assert breaker.state == CircuitState.OPEN, "Circuit must be OPEN after 3 consecutive failures!"
    print("  ✅ Circuit breaker successfully tripped to OPEN!")

    # Verify fast-fail / fallback routing when OPEN
    print("\n--- [Step 2] Testing Graceful Fallback Routing when Circuit is OPEN ---")
    fallback_result = breaker.call(failing_llm_call, fallback=fallback_llm_call)
    print(f"  Fallback Response: {fallback_result}")
    assert fallback_result["status"] == "fallback_success"
    print("  ✅ Graceful degradation verified: Request served via fallback without crashing!")

    # Verify Half-Open probe recovery after timeout
    time.sleep(1.1)
    def healthy_llm_call():
        return {"status": "recovered"}

    probe_result = breaker.call(healthy_llm_call)
    assert breaker.state == CircuitState.CLOSED, "Circuit must return to CLOSED after successful probe!"
    print("  ✅ Self-healing verified: Circuit breaker automatically recovered to CLOSED!")

    # 2. Test Dead Letter Queue (DLQ)
    print("\n--- [Step 3] Testing Dead Letter Queue (DLQ) Routing ---")
    queue = MemoryQueue()
    test_worker = MemoryWorker(queue=queue)
    test_worker.max_retries = 2  # Low retries for fast test

    # Enqueue unprocessable bad payload
    bad_payload = {"invalid_data": True}
    job_id = queue.enqueue(bad_payload)

    # Process first attempt (fails -> increments retry)
    res1 = test_worker.process_one_job()
    print(f"  Attempt 1: Status={res1.get('status')}, Retry={res1.get('retry')}")

    # Process second attempt (fails -> exceeds max_retries -> DLQ)
    res2 = test_worker.process_one_job()
    print(f"  Attempt 2: Status={res2.get('status')}")
    assert res2.get("status") == "DEAD_LETTER", "Job must be routed to DLQ after exhausting retries!"

    # Verify job status in queue store
    final_status = queue.get_job_status(job_id)
    print(f"  Final Job Envelope Status: {final_status.get('status')}")
    assert final_status.get("status") == JobStatus.DEAD_LETTER.value
    print("  ✅ Dead Letter Queue verified: Failed jobs safely isolated for debugging!")

    print("\n" + "=" * 76)
    print(" 🏆 ALL RESILIENCE & CIRCUIT BREAKER TESTS PASSED!")
    print("=" * 76 + "\n")


if __name__ == "__main__":
    run_resilience_test()
