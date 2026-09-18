"""Verification script for Phase 1: The Smart Notebook Engine.
Tests PII sanitization, fact extraction, SQLite storage, and contradiction resolution.
"""

import sys
from pathlib import Path

# Fix Windows console encoding for Unicode/emojis
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_memory.engine.sanitizer import sanitize_text
from agent_memory.engine.extractor import FactExtractor
from agent_memory.engine.resolver import ConflictResolver
from agent_memory.engine.embeddings import EmbeddingService
from agent_memory.storage.sqlite_store import SQLiteMemoryStore
from agent_memory.models.memory import MemoryRecord


def run_phase1_test():
    print("\n" + "=" * 70)
    print(" 🚀 RUNNING PHASE 1 TEST: THE SMART NOTEBOOK ENGINE")
    print("=" * 70)

    # 1. Test PII Sanitization
    print("\n--- [Step 1] Testing Enterprise PII & Secret Sanitization ---")
    dirty_text = "My OpenAI key is sk-abcdef12345678901234567890123456 and my email is test@example.com"
    clean_text, redacted = sanitize_text(dirty_text)
    print(f"Original Text : {dirty_text}")
    print(f"Sanitized Text: {clean_text}")
    assert redacted is True
    assert "sk-" not in clean_text
    print("✅ PII & Secrets successfully scrubbed!")

    # 2. Setup Storage & Engine
    test_db = Path(__file__).resolve().parent / "test_phase1.db"
    if test_db.exists():
        test_db.unlink()

    store = SQLiteMemoryStore(db_path=str(test_db))
    extractor = FactExtractor()
    embeddings = EmbeddingService()
    resolver = ConflictResolver(embeddings)

    tenant_id = "org_acme_corp"
    user_id = "developer_alice"

    # 3. Test Initial Conversation Ingestion (Day 1)
    print("\n--- [Step 2] Day 1: User Conversation (Small Talk + Facts) ---")
    day1_messages = [
        {"role": "user", "content": "Hey there! Good morning! Can you help me out?"},
        {"role": "assistant", "content": "Good morning! How can I assist you today?"},
        {"role": "user", "content": "I live in Chicago and I prefer TypeScript for all my projects."},
        {"role": "assistant", "content": "Got it! Noted that you are based in Chicago and use TypeScript."}
    ]

    extraction = extractor.extract(day1_messages)
    print(f"Extracted {len(extraction.facts)} atomic facts:")
    for f in extraction.facts:
        print(f"  • [{f.category}] {f.statement} (Entity: {f.entity}, Attr: {f.attribute}, Val: {f.value})")

    # Store them
    for f in extraction.facts:
        embed = embeddings.embed_text(f.statement)
        record = MemoryRecord(
            tenant_id=tenant_id,
            user_id=user_id,
            statement=f.statement,
            category=f.category.value,
            entity=f.entity,
            attribute=f.attribute,
            value=f.value,
            importance=f.importance,
            embedding=embed
        )
        store.add_memory(record)

    active_day1 = store.get_active_memories(tenant_id, user_id)
    print(f"\nActive Memories in Database after Day 1: {len(active_day1)}")
    for m in active_day1:
        print(f"  ID: {m.id} | Active: {m.is_active} | Fact: {m.statement}")

    # 4. Test Contradiction & Conflict Resolution (Day 15)
    print("\n--- [Step 3] Day 15: Conflict Resolution (State Update) ---")
    print("User states: 'I moved to London recently.'")

    day15_messages = [
        {"role": "user", "content": "Hey, just a quick update: I moved to London recently."}
    ]

    extraction_day15 = extractor.extract(day15_messages)
    print(f"Extracted new fact: {extraction_day15.facts[0].statement}")

    new_fact = extraction_day15.facts[0]
    existing_memories = store.get_active_memories(tenant_id, user_id)

    # Check for conflicts
    conflicts = resolver.detect_conflicts(new_fact, existing_memories)
    assert len(conflicts) > 0, "Conflict should be detected for location!"

    print(f"⚡ Conflict Detected!")
    for old_mem, reason in conflicts:
        print(f"  Reason: {reason}")
        print(f"  Old memory to supersede: '{old_mem.statement}' (ID: {old_mem.id})")

    # Save new memory and mark old memory as superseded
    new_embed = embeddings.embed_text(new_fact.statement)
    new_record = MemoryRecord(
        tenant_id=tenant_id,
        user_id=user_id,
        statement=new_fact.statement,
        category=new_fact.category.value,
        entity=new_fact.entity,
        attribute=new_fact.attribute,
        value=new_fact.value,
        importance=new_fact.importance,
        embedding=new_embed
    )
    new_id = store.add_memory(new_record)

    for old_mem, _ in conflicts:
        store.mark_superseded(old_mem.id, new_id)

    # 5. Verify Final State
    active_final = store.get_active_memories(tenant_id, user_id)
    print(f"\n--- [Step 4] Final Active Memories for {user_id} ---")
    for m in active_final:
        print(f"  • {m.statement} [Active: {m.is_active}]")

    # Assertions
    statements = [m.statement for m in active_final]
    assert any("London" in s for s in statements), "London must be active!"
    assert not any("Chicago" in s for s in statements), "Chicago must be superseded and inactive!"

    print("\n" + "=" * 70)
    print(" 🎉 PHASE 1 VERIFICATION COMPLETED SUCCESSFULLY!")
    print("    - PII scrubbing works")
    print("    - Fact extraction works")
    print("    - Conflict resolution supersedes old memories without amnesia")
    print("    - SQLite persistence is verified")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_phase1_test()
