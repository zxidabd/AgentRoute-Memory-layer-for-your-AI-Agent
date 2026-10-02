"""Production database session management and connection pooling."""

import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from .config import settings
from .models.db_models import Base


# Configure connection pooling and URI normalization (e.g. Supabase postgres:// -> postgresql+psycopg2://)
def normalize_db_url(url: str) -> str:
    if not url:
        return url
    trimmed = url.strip()
    if trimmed.startswith("postgres://"):
        trimmed = trimmed.replace("postgres://", "postgresql+psycopg2://", 1)
    elif trimmed.startswith("postgresql://") and not trimmed.startswith("postgresql+"):
        trimmed = trimmed.replace("postgresql://", "postgresql+psycopg2://", 1)
    return trimmed

primary_db_url = normalize_db_url(settings.database_url)

connect_args = {}
if primary_db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    engine = create_engine(
        primary_db_url,
        connect_args=connect_args,
        echo=False
    )
else:
    # Production PostgreSQL / Supabase pool
    engine = create_engine(
        primary_db_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_timeout_seconds,
        pool_pre_ping=True,
        echo=False
    )

SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Read-Replica connection pool for high-throughput context recalls (falls back to primary engine)
replica_db_url = normalize_db_url(settings.read_database_url)
if replica_db_url:
    read_connect_args = {}
    if replica_db_url.startswith("sqlite"):
        read_connect_args["check_same_thread"] = False
        read_engine = create_engine(replica_db_url, connect_args=read_connect_args, echo=False)
    else:
        read_engine = create_engine(
            replica_db_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_timeout_seconds,
            pool_pre_ping=True,
            echo=False
        )
    ReadSessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=read_engine)
else:
    read_engine = engine
    ReadSessionFactory = SessionFactory


# Attach SOC 2 compliance immutability guards
from .compliance.immutability_guard import attach_immutability_guards
attach_immutability_guards(SessionFactory)
if ReadSessionFactory is not SessionFactory:
    attach_immutability_guards(ReadSessionFactory)


def init_db():
    """Initializes all database tables and indexes."""
    # If on PostgreSQL, ensure pgvector extension exists
    if not primary_db_url.startswith("sqlite"):
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                conn.commit()

        except Exception:
            pass

    Base.metadata.create_all(bind=engine)

    # Safe automated schema migration for newly added billing & auth columns
    with engine.connect() as conn:
        new_cols_org = [
            ("subscription_status", "VARCHAR(50) DEFAULT 'active'"),
            ("billing_gateway", "VARCHAR(50) DEFAULT 'stripe'"),
            ("stripe_customer_id", "VARCHAR(128)"),
            ("stripe_subscription_id", "VARCHAR(128)"),
            ("razorpay_customer_id", "VARCHAR(128)"),
            ("razorpay_subscription_id", "VARCHAR(128)"),
            ("current_period_start", "TIMESTAMP"),
            ("current_period_end", "TIMESTAMP"),
            ("cancel_at_period_end", "BOOLEAN DEFAULT 0"),
            ("overage_billing_enabled", "BOOLEAN DEFAULT 1"),
            ("past_due_since", "TIMESTAMP"),
            ("clerk_org_id", "VARCHAR(128)"),
        ]
        for col_name, col_def in new_cols_org:
            try:
                conn.execute(text(f"ALTER TABLE organizations ADD COLUMN {col_name} {col_def};"))
                conn.commit()
            except Exception:
                pass

        new_cols_projects = [
            ("environment", "VARCHAR(50) DEFAULT 'dev'"),
        ]
        for col_name, col_def in new_cols_projects:
            try:
                conn.execute(text(f"ALTER TABLE projects ADD COLUMN {col_name} {col_def};"))
                conn.commit()
            except Exception:
                pass

        new_cols_api_keys = [
            ("project_id", "VARCHAR(64)"),
            ("key_prefix", "VARCHAR(64) DEFAULT 'mb_live'"),
            ("environment", "VARCHAR(50) DEFAULT 'dev'"),
            ("created_by_id", "VARCHAR(64)"),
            ("revoked_at", "TIMESTAMP"),
        ]
        for col_name, col_def in new_cols_api_keys:
            try:
                conn.execute(text(f"ALTER TABLE api_keys ADD COLUMN {col_name} {col_def};"))
                conn.commit()
            except Exception:
                pass

        # Auth system columns
        new_cols_users = [
            ("last_login_at", "TIMESTAMP"),
            ("is_super_user", "BOOLEAN DEFAULT 0"),
            ("subscription_status", "VARCHAR(50) DEFAULT 'trialing'"),
            ("plan_tier", "VARCHAR(50) DEFAULT 'free_trial'"),
            ("trial_ends_at", "TIMESTAMP"),
            ("failed_login_attempts", "INTEGER DEFAULT 0"),
            ("locked_until", "TIMESTAMP"),
            ("totp_secret", "VARCHAR(64)"),
            ("totp_enabled", "BOOLEAN DEFAULT 0"),
        ]
        for col_name, col_def in new_cols_users:
            try:
                conn.execute(text(f"ALTER TABLE user_accounts ADD COLUMN {col_name} {col_def};"))
                conn.commit()
            except Exception:
                pass

        # Ensure superuser status for designated admin
        try:
            conn.execute(text("UPDATE user_accounts SET is_super_user = 1 WHERE email = 'abdullahzaid509@gmail.com';"))
            conn.commit()
        except Exception:
            pass

        # Create refresh_tokens table if not exists
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    id VARCHAR(64) PRIMARY KEY,
                    user_id VARCHAR(64) NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
                    token_hash VARCHAR(128) UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    revoked_at TIMESTAMP,
                    user_agent VARCHAR(512),
                    ip_address VARCHAR(64)
                );
            """))
            conn.commit()
        except Exception:
            pass

        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens(user_id);"))
            conn.commit()
        except Exception:
            pass

        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_refresh_tokens_token_hash ON refresh_tokens(token_hash);"))
            conn.commit()
        except Exception:
            pass

        # Create email_verification_tokens table if not exists
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS email_verification_tokens (
                    id VARCHAR(64) PRIMARY KEY,
                    user_id VARCHAR(64) NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
                    token_hash VARCHAR(128) UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    consumed BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.commit()
        except Exception:
            pass

        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_email_verif_tokens_user ON email_verification_tokens(user_id);"))
            conn.commit()
        except Exception:
            pass

        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_email_verif_tokens_hash ON email_verification_tokens(token_hash);"))
            conn.commit()
        except Exception:
            pass

        # Create contact_messages table if not exists
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS contact_messages (
                    id VARCHAR(64) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    subject VARCHAR(255) NOT NULL,
                    message TEXT NOT NULL,
                    user_id VARCHAR(64),
                    ip_address VARCHAR(64),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.commit()
        except Exception:
            pass

        new_cols_usage = [
            ("event_type", "VARCHAR(64) DEFAULT 'RECALL_QUERY'"),
            ("units_billed", "INTEGER DEFAULT 1"),
        ]
        for col_name, col_def in new_cols_usage:
            try:
                conn.execute(text(f"ALTER TABLE usage_events ADD COLUMN {col_name} {col_def};"))
                conn.commit()
            except Exception:
                pass

        # ── Cleanup: Remove auto-generated Session Key / Google Session Key records ──
        # Step 1: For orgs that have NO "Default Live Key", promote one session key
        try:
            conn.execute(text("""
                UPDATE api_keys
                SET name = 'Default Live Key'
                WHERE id IN (
                    SELECT MIN(k.id) FROM api_keys k
                    WHERE (k.name LIKE 'Session Key %' OR k.name LIKE 'Google Session Key %')
                    AND k.is_active = 1
                    GROUP BY k.org_id
                    HAVING k.org_id NOT IN (
                        SELECT org_id FROM api_keys WHERE name = 'Default Live Key'
                    )
                );
            """))
            conn.commit()
        except Exception:
            pass

        # Step 2: Delete all remaining session keys (each org now has a Default Live Key)
        try:
            conn.execute(text("""
                DELETE FROM api_keys
                WHERE (name LIKE 'Session Key %' OR name LIKE 'Google Session Key %');
            """))
            conn.commit()
        except Exception:
            pass


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context manager for database sessions with automatic commit & rollback."""
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency for write/primary database session injection."""
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_read_db_session() -> Generator[Session, None, None]:
    """
    FastAPI dependency for high-throughput read session injection.
    Routes queries to Read Replica if configured; seamlessly falls back to primary on error.
    """
    try:
        session = ReadSessionFactory()
        try:
            yield session
        finally:
            session.close()
    except Exception:
        # Fallback to primary writer session
        session = SessionFactory()
        try:
            yield session
        finally:
            session.close()


def check_db_health(timeout_seconds: int = 3) -> bool:
    """Verifies active connectivity to the primary database with an active roundtrip."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def check_read_db_health() -> bool:
    """Verifies active connectivity to the read replica."""
    try:
        with read_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


from .storage.vector_extension import get_pgvector_ddl, setup_vector_support
