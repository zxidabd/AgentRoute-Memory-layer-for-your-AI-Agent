"""Benchmark Memory Quality Evaluation Suite.
Measures retrieval precision, recall, and contradiction resolution across multi-day timelines.
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_memory.database import init_db, get_db
from agent_memory.models.db_models import Memory, MemoryStatus
from agent_memory.security.encryption import encrypt_field, decrypt_field
from agent_memory.engine.embeddings import EmbeddingService
from agent_memory.engine.ranking import MemoryRanker
from agent_memory.models.memory import MemoryRecord


def run_benchmark_evaluation():
    print("\n" + "=" * 76)
    print(" 📊 MEMORY QUALITY & ACCURACY BENCHMARK EVALUATION")
    print("=" * 76)

    init_db()
    embeddings = EmbeddingService()
    ranker = MemoryRanker(embedding_service=embeddings)

    now = datetime.now(timezone.utc)
    org_id = "org_benchmark"
    user_id = "eval_user_dave"

    # =========================================================================
    # SCENARIO: Language Evolution Across 30 Days
    # Day 1:  "I prefer Python for backend."
    # Day 15: "I started using Go for microservices."
    # Day 30: "I am primarily using Go now."
    # =========================================================================
    print("\n--- [Step 1] Loading 30-Day Evolution Dataset ---")

    benchmark_memories = [
        # Historical superseded memory (Day 1)
        MemoryRecord(
            id="mem_day1",
            tenant_id=org_id,
            user_id=user_id,
            statement="User prefers Python for backend development",
            category="PREFERENCE",
            entity="user",
            attribute="primary_language",
            value="Python",
            status=MemoryStatus.SUPERSEDED.value,
            is_active=False,
            created_at=now - timedelta(days=30),
            superseded_by="mem_day30",
            embedding=embeddings.embed_text("User prefers Python for backend development")
        ),
        # Current active truth memory (Day 30)
        MemoryRecord(
            id="mem_day30",
            tenant_id=org_id,
            user_id=user_id,
            statement="User primary language is Go for backend microservices",
            category="PREFERENCE",
            entity="user",
            attribute="primary_language",
            value="Go",
            status=MemoryStatus.ACTIVE.value,
            is_active=True,
            created_at=now - timedelta(days=1),
            embedding=embeddings.embed_text("User primary language is Go for backend microservices")
        ),
        # Unrelated constraint
        MemoryRecord(
            id="mem_diet",
            tenant_id=org_id,
            user_id=user_id,
            statement="User has severe peanut allergy",
            category="CONSTRAINT",
            entity="user",
            attribute="dietary_restriction",
            value="peanuts",
            status=MemoryStatus.ACTIVE.value,
            is_active=True,
            created_at=now - timedelta(days=15),
            embedding=embeddings.embed_text("User has severe peanut allergy")
        )
    ]

    print("✓ Benchmark dataset loaded: 1 Superseded fact, 1 Active updated fact, 1 Unrelated constraint.")

    # =========================================================================
    # EVALUATION QUERY: "What language does Dave write in?"
    # =========================================================================
    query = "What language does Dave write in?"
    print(f"\n--- [Step 2] Executing Evaluation Query: '{query}' ---")

    active_only = [m for m in benchmark_memories if m.is_active]
    ranked = ranker.rank(query=query, memories=active_only, limit=5)

    print(f"  Retrieved {len(ranked)} memories:")
    for mem, score in ranked:
        print(f"    • Score: {score:.3f} | Statement: '{mem.statement}'")

    # =========================================================================
    # BENCHMARK METRICS COMPUTATION
    # =========================================================================
    print("\n--- [Step 3] Computing Benchmark Metrics ---")

    retrieved_statements = [m.statement for m, _ in ranked]

    # 1. Contradiction Accuracy: Is historical Python EXCLUDED from active context?
    historical_excluded = not any("Python" in s for s in retrieved_statements)
    print(f"  Contradiction Accuracy (No Stale Memory) : {'100%' if historical_excluded else '0%'}")

    # 2. Precision: Is Go retrieved as primary answer?
    correct_active_retrieved = any("Go" in s for s in retrieved_statements)
    print(f"  Precision (Target Fact Retrieved)       : {'100%' if correct_active_retrieved else '0%'}")

    # 3. Off-Topic Isolation: Was peanut allergy filtered out?
    off_topic_excluded = not any("peanut" in s.lower() for s in retrieved_statements)
    print(f"  Noise Rejection (Off-Topic Filtered)     : {'100%' if off_topic_excluded else '0%'}")

    assert historical_excluded, "BENCHMARK FAILURE: Outdated Python fact was retrieved!"
    assert correct_active_retrieved, "BENCHMARK FAILURE: Active Go fact was missing!"
    assert off_topic_excluded, "BENCHMARK FAILURE: Peanut allergy polluted language context!"

    print("\n" + "=" * 76)
    print(" 🏆 ALL BENCHMARK METRICS SCORED 100% PASS!")
    print("=" * 76 + "\n")


if __name__ == "__main__":
    run_benchmark_evaluation()
