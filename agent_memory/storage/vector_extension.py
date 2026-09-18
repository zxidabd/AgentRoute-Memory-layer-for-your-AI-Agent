"""
Database Vector Extension & HNSW Indexing Management.
Handles pgvector initialization and HNSW cosine similarity index creation on PostgreSQL,
with safe no-op fallback on SQLite.
"""

import logging
from typing import List, Dict, Any
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger("memorybrain.database.vector")


def get_pgvector_ddl(dimension: int = 768, m: int = 16, ef_construction: int = 64) -> List[str]:
    """Generates PostgreSQL DDL statements for pgvector extension and HNSW index."""
    return [
        "CREATE EXTENSION IF NOT EXISTS vector;",
        f"ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding vector({dimension});",
        f"""
        CREATE INDEX IF NOT EXISTS ix_memories_embedding_hnsw 
        ON memories USING hnsw (embedding vector_cosine_ops) 
        WITH (m = {m}, ef_construction = {ef_construction});
        """.strip()
    ]


def setup_vector_support(engine: Engine, dimension: int = 768) -> Dict[str, Any]:
    """
    Configures vector similarity search support on the target database engine.
    - PostgreSQL: Enables pgvector and creates HNSW index.
    - SQLite: Preserves JSON vector storage without failing.
    """
    dialect = engine.dialect.name.lower()

    if dialect == "postgresql":
        logger.info(f"Applying pgvector extension and HNSW index (dimension: {dimension}) to PostgreSQL...")
        try:
            with engine.connect() as conn:
                for stmt in get_pgvector_ddl(dimension=dimension):
                    conn.execute(text(stmt))
                conn.commit()
            return {
                "dialect": "postgresql",
                "pgvector_enabled": True,
                "index_type": "hnsw",
                "dimension": dimension,
                "status": "CONFIGURED"
            }
        except Exception as e:
            logger.warning(f"Could not initialize pgvector (may lack superuser extension privileges): {e}")
            return {
                "dialect": "postgresql",
                "pgvector_enabled": False,
                "error": str(e),
                "status": "FALLBACK_TO_JSON"
            }
    else:
        # SQLite / other dialects: JSON vector string fallback
        logger.info(f"Database dialect is '{dialect}'. Using native JSON vector embedding fallback.")
        return {
            "dialect": dialect,
            "pgvector_enabled": False,
            "index_type": "json_fallback",
            "dimension": dimension,
            "status": "SQLITE_JSON_MODE"
        }
