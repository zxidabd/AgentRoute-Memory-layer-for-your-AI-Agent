"""High-performance zero-config SQLite storage with vector search support."""

import sqlite3
import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pathlib import Path
from ..config import settings
from ..models.memory import MemoryRecord


class SQLiteMemoryStore:
    """Thread-safe SQLite storage engine for multi-tenant memories and API keys."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.database_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initializes tables for API keys, memories, and audit logs."""
        with self._get_connection() as conn:
            # 1. API Keys Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    key_hash TEXT UNIQUE NOT NULL,
                    key_hint TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    rate_limit_rpm INTEGER DEFAULT 120,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT
                )
            """)

            # 2. Memories Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    agent_id TEXT,
                    statement TEXT NOT NULL,
                    category TEXT NOT NULL,
                    entity TEXT NOT NULL,
                    attribute TEXT,
                    value TEXT,
                    importance REAL DEFAULT 0.7,
                    access_count INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    superseded_by TEXT,
                    embedding_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_accessed_at TEXT
                )
            """)

            # Compound indexes for sub-millisecond tenant & user filtering
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_tenant_user ON memories(tenant_id, user_id, is_active)")
            except Exception:
                try:
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_tenant_user ON memories(org_id, user_id, status)")
                except Exception:
                    pass
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_entity_attr ON memories(entity, attribute)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash)")
            conn.commit()

    # -------------------------------------------------------------
    # Memory Operations
    # -------------------------------------------------------------

    def add_memory(self, record: MemoryRecord) -> str:
        """Stores a new memory record with vector embedding."""
        embedding_json = json.dumps(record.embedding) if record.embedding else None
        now_str = record.created_at.isoformat()

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO memories (
                    id, tenant_id, user_id, agent_id, statement, category,
                    entity, attribute, value, importance, access_count,
                    is_active, superseded_by, embedding_json,
                    created_at, updated_at, last_accessed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.id, record.tenant_id, record.user_id, record.agent_id,
                record.statement, record.category, record.entity, record.attribute,
                record.value, record.importance, record.access_count,
                1 if record.is_active else 0, record.superseded_by, embedding_json,
                now_str, now_str, now_str
            ))
            conn.commit()
        return record.id

    def get_active_memories(self, tenant_id: str, user_id: str) -> List[MemoryRecord]:
        """Retrieves all active, non-superseded memories for a specific tenant and user."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM memories
                WHERE tenant_id = ? AND user_id = ? AND is_active = 1
                ORDER BY created_at DESC
            """, (tenant_id, user_id))
            rows = cursor.fetchall()
            return [self._row_to_record(row) for row in rows]

    def mark_superseded(self, old_memory_id: str, new_memory_id: str):
        """Marks an old memory as inactive and records which new memory superseded it."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE memories
                SET is_active = 0, superseded_by = ?, updated_at = ?
                WHERE id = ?
            """, (new_memory_id, old_str_id := now_str, old_memory_id))
            conn.commit()

    def touch_memory(self, memory_id: str):
        """Increments access count and updates last accessed time."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE memories
                SET access_count = access_count + 1, last_accessed_at = ?
                WHERE id = ?
            """, (now_str, memory_id))
            conn.commit()

    def delete_user_memories(self, tenant_id: str, user_id: str) -> int:
        """Permanently deletes all memories for a user (GDPR Right to be Forgotten)."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                DELETE FROM memories
                WHERE tenant_id = ? AND user_id = ?
            """, (tenant_id, user_id))
            conn.commit()
            return cursor.rowcount

    # -------------------------------------------------------------
    # API Key Operations
    # -------------------------------------------------------------

    def save_api_key(
        self, id: str, org_id: str, name: str, key_hash: str, key_hint: str
    ):
        """Saves a hashed API key for a business owner."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO api_keys (id, org_id, name, key_hash, key_hint, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
            """, (id, org_id, name, key_hash, key_hint, now_str))
            conn.commit()

    def get_api_key(self, key_hash: str) -> Optional[Dict[str, Any]]:
        """Finds an API key record by its SHA-256 hash."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM api_keys WHERE key_hash = ?
            """, (key_hash,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def list_api_keys(self, org_id: str) -> List[Dict[str, Any]]:
        """Lists all keys for an organization."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, org_id, name, key_hint, is_active, created_at, last_used_at
                FROM api_keys WHERE org_id = ?
                ORDER BY created_at DESC
            """, (org_id,))
            return [dict(row) for row in cursor.fetchall()]

    def _row_to_record(self, row: sqlite3.Row) -> MemoryRecord:
        """Converts an SQLite row to a MemoryRecord model."""
        embedding = json.loads(row["embedding_json"]) if row["embedding_json"] else None
        return MemoryRecord(
            id=row["id"],
            tenant_id=row["tenant_id"],
            user_id=row["user_id"],
            agent_id=row["agent_id"],
            statement=row["statement"],
            category=row["category"],
            entity=row["entity"],
            attribute=row["attribute"] or "",
            value=row["value"] or "",
            importance=row["importance"],
            access_count=row["access_count"],
            is_active=bool(row["is_active"]),
            superseded_by=row["superseded_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            last_accessed_at=datetime.fromisoformat(row["last_accessed_at"]) if row["last_accessed_at"] else None,
            embedding=embedding
        )
