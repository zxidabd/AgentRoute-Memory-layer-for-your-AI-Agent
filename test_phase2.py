"""Verification script for Phase 2: Fast Recall, Search, and Decay System.
Tests multi-factor relevance ranking, Ebbinghaus forgetting curves, and token budget clamping.
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Fix Windows console encoding for Unicode/emojis
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_memory.engine.embeddings import EmbeddingService
from agent_memory.engine.ranking import MemoryRanker
from agent_memory.models.memory import MemoryRecord


def run_phase2_test():
    print("\n" + "=" * 70)
    print(" 🚀 RUNNING PHASE 2 TEST: FAST RECALL, SEARCH & DECAY")
    print("=" * 70)

    embeddings = EmbeddingService()
    ranker = MemoryRanker(embedding_service=embeddings)

    now = datetime.now(timezone.utc)
    user_id = "user_bob"

    # 1. Setup sample memories with different ages, importance, and topics
    memories = [
        # Memory 1: Highly relevant to coding query, recent, high importance
        MemoryRecord(
            id="mem_1",
            user_id=user_id,
            statement="User backend stack is Go microservices and gRPC on Google Cloud",
            category="DECISION",
            entity="project",
            importance=0.9,
            created_at=now - timedelta(days=2),
            embedding=embeddings.embed_text("User backend stack is Go microservices and gRPC on Google Cloud")
        ),
        # Memory 2: Moderately relevant, but created 180 days ago (should decay)
        MemoryRecord(
            id="mem_2",
            user_id=user_id,
            statement="User looked at Docker setup for Go apps",
            category="FACT",
            entity="project",
            importance=0.5,
            created_at=now - timedelta(days=180),
            embedding=embeddings.embed_text("User looked at Docker setup for Go apps")
        ),
        # Memory 3: Completely irrelevant (dietary preference)
        MemoryRecord(
            id="mem_3",
            user_id=user_id,
            statement="User is vegetarian and allergic to peanuts",
            category="CONSTRAINT",
            entity="user",
            importance=0.95,
            created_at=now - timedelta(hours=1),
            embedding=embeddings.embed_text("User is vegetarian and allergic to peanuts")
        )
    ]

    # 2. Test Multi-Factor Search
    query = "What backend stack does Bob use for his services?"
    print(f"\n--- [Step 1] Query: '{query}' ---")
    
    ranked = ranker.rank(query=query, memories=memories, limit=3)
    print(f"Total returned after ranking & threshold filter: {len(ranked)}")
    for mem, score in ranked:
        print(f"  Score: {score:.3f} | Statement: '{mem.statement}'")

    # Assert Memory 1 is top ranked
    assert len(ranked) > 0, "At least one memory should match!"
    assert ranked[0][0].id == "mem_1", "Go microservice memory should be top ranked!"
    assert not any(m.id == "mem_3" for m, _ in ranked), "Peanut allergy must NOT be retrieved for a tech stack query!"
    print("✅ Search precision and topic isolation verified!")

    # 3. Test Ebbinghaus Decay Math
    print("\n--- [Step 2] Testing Ebbinghaus Forgetting Decay Curve ---")
    mem_fresh = MemoryRecord(user_id=user_id, statement="test fresh", created_at=now)
    mem_old = MemoryRecord(user_id=user_id, statement="test old", created_at=now - timedelta(days=60))
    mem_reinforced = MemoryRecord(user_id=user_id, statement="test reinforced", created_at=now - timedelta(days=60), access_count=5)

    decay_fresh = ranker.calculate_decay(mem_fresh, now)
    decay_old = ranker.calculate_decay(mem_old, now)
    decay_reinf = ranker.calculate_decay(mem_reinforced, now)

    print(f"  Fresh Memory Decay (Day 0)               : {decay_fresh:.3f} (1.0 = full recall)")
    print(f"  Old Memory Decay (Day 60, zero accesses)  : {decay_old:.3f} (decayed)")
    print(f"  Old Memory Reinforced (Day 60, 5 accesses): {decay_reinf:.3f} (retained due to practice)")

    assert decay_fresh > decay_old, "Fresh memory must have higher score than old memory"
    assert decay_reinf > decay_old, "Repeatedly accessed memory must resist decay"
    print("✅ Ebbinghaus forgetting and access reinforcement math verified!")

    # 4. Test Token Budget Clamping (/context output)
    print("\n--- [Step 3] Testing Token Budget Clamping for Prompt Context ---")
    context_resp = ranker.build_context_string(user_id=user_id, ranked_memories=ranked, token_limit=25)
    
    print(f"  Prompt-Ready Context:\n{context_resp.context}")
    print(f"  Token Count : {context_resp.token_count} (Limit: 25)")
    print(f"  Memory Count: {context_resp.memory_count}")

    assert context_resp.token_count <= 25, "Must strictly respect the token budget limit!"
    print("✅ Prompt token clamping verified!")

    print("\n" + "=" * 70)
    print(" 🎉 PHASE 2 VERIFICATION COMPLETED SUCCESSFULLY!")
    print("    - Multi-factor ranking brings the right memories to the top")
    print("    - Irrelevant memories are prevented from polluting context")
    print("    - Ebbinghaus decay fades old trivia")
    print("    - Token clamping protects the developer's prompt window")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_phase2_test()
