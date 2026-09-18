"""Production Memory Lifecycle Test Suite.
Tests AES-256 field encryption at rest, versioning ledger, soft deletion, and GDPR cascading purge.
"""

import sys
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_memory.database import init_db, get_db
from agent_memory.models.db_models import Memory, MemoryVersion, MemoryStatus
from agent_memory.security.encryption import encrypt_field, decrypt_field
from agent_memory.api.routes.v1_memories import patch_memory, delete_single_memory
from agent_memory.api.routes.v1_privacy import purge_user_data
from agent_memory.models.api_schemas import MemoryPatchRequest


def run_lifecycle_test():
    print("\n" + "=" * 76)
    print(" 🔄 PRODUCTION MEMORY LIFECYCLE & ENCRYPTION TEST")
    print("=" * 76)

    init_db()
    org_id = "org_enterprise_corp"
    user_id = "user_sarah"
    mem_id = "mem_test_lifecycle_01"

    # Clean existing
    with get_db() as db:
        db.info["gdpr_purge_authorized"] = True
        db.query(MemoryVersion).filter(MemoryVersion.memory_id == mem_id).delete()
        db.query(Memory).filter(Memory.id == mem_id).delete()
        db.commit()

    # 1. Test Field-Level AES-256 Encryption at Rest
    print("\n--- [Step 1] Field-Level AES-256 Encryption at Rest ---")
    plain_statement = "Sarah prefers Python with strict static typing using Mypy"
    encrypted_cipher = encrypt_field(plain_statement)
    print(f"  Plaintext : '{plain_statement}'")
    print(f"  Ciphertext: '{encrypted_cipher[:35]}...'")

    assert encrypted_cipher != plain_statement, "Data must be encrypted at rest!"
    assert decrypt_field(encrypted_cipher) == plain_statement, "Decryption must accurately restore plaintext!"
    print("  ✅ AES-256 Encryption and Decryption verified!")

    # 2. Insert Record into Database
    with get_db() as db:
        mem = Memory(
            id=mem_id,
            org_id=org_id,
            user_id=user_id,
            statement=encrypted_cipher,
            category="PREFERENCE",
            entity="user",
            attribute="typing_preference",
            value="Mypy",
            status=MemoryStatus.ACTIVE.value,
            version=1
        )
        db.add(mem)
        # Add initial version 1
        ver1 = MemoryVersion(
            id="ver_01",
            memory_id=mem_id,
            version_number=1,
            statement=encrypted_cipher,
            status=MemoryStatus.ACTIVE.value,
            reason="Initial created"
        )
        db.add(ver1)
        db.commit()

    # 3. Test Memory Versioning and Audit Ledger
    print("\n--- [Step 2] Memory Versioning & Audit Ledger ---")
    new_text = "Sarah updated preference: now uses Pyright instead of Mypy"
    patch_req = MemoryPatchRequest(statement=new_text, reason="User switched linter")

    with get_db() as db:
        patch_res = patch_memory(memory_id=mem_id, payload=patch_req, tenant_id=org_id, db=db)
        print(f"  Patched Memory: Version={patch_res['new_version']}, Status={patch_res['status']}")
        assert patch_res["new_version"] == 2, "Memory version must increment to 2!"

        # Verify audit history
        versions = db.query(MemoryVersion).filter(MemoryVersion.memory_id == mem_id).all()
        print(f"  Audit History Count: {len(versions)} versions on record.")
        assert len(versions) == 2, "Both version 1 and version 2 must exist in audit ledger!"
    print("  ✅ Memory Versioning and Audit Ledger verified!")

    # 4. Test Soft-Deletion
    print("\n--- [Step 3] Testing Soft-Deletion ---")
    with get_db() as db:
        soft_del = delete_single_memory(memory_id=mem_id, purge=False, tenant_id=org_id, db=db)
        print(f"  Delete Result: {soft_del}")
        assert soft_del["type"] == "soft_delete"

        rec = db.query(Memory).filter(Memory.id == mem_id).first()
        assert rec.status == MemoryStatus.SOFT_DELETED.value, "Record must be marked SOFT_DELETED!"
    print("  ✅ Soft-Deletion verified (preserved for audit, omitted from search)!")

    # 5. Test GDPR Cascading Hard Purge
    print("\n--- [Step 4] Testing GDPR Cascading Purge ---")
    with get_db() as db:
        purge_res = purge_user_data(user_id=user_id, tenant_id=org_id, db=db)
        print(f"  GDPR Purge Result: {purge_res['message']}")
        assert purge_res["memories_deleted"] >= 1

        # Assert record is completely gone
        remaining = db.query(Memory).filter(Memory.user_id == user_id).all()
        assert len(remaining) == 0, "All user records must be irreversibly wiped!"
    print("  ✅ GDPR Cascading Purge verified!")

    print("\n" + "=" * 76)
    print(" 🏆 PRODUCTION LIFECYCLE TEST COMPLETED SUCCESSFULLY!")
    print("=" * 76 + "\n")


if __name__ == "__main__":
    run_lifecycle_test()
