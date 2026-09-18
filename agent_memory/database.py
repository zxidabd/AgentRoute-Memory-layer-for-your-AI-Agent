"""Production database session management and connection pooling."""

import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from .config import settings
from .models.db_models import Base


# Configure connection pooling
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    engine = create_engine(
        settings.database_url,
        connect_args=connect_args,
        echo=False
    )
else:
    # Production PostgreSQL pool
    engine = create_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_timeout_seconds,
        pool_pre_ping=True,
        echo=False
    )

SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Read-Replica connection pool for high-throughput context recalls (falls back to primary engine)
if settings.read_database_url and settings.read_database_url.strip():
    read_connect_args = {}
    if settings.read_database_url.startswith("sqlite"):
        read_connect_args["check_same_thread"] = False
        read_engine = create_engine(settings.read_database_url, connect_args=read_connect_args, echo=False)
    else:
        read_engine = create_engine(
            settings.read_database_url,
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
    if not settings.database_url.startswith("sqlite"):
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
