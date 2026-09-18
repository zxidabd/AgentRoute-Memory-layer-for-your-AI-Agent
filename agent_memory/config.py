"""Production configuration and environment variable management."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # AI Models
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    extraction_model: str = os.getenv("EXTRACTION_MODEL", "gemini-2.5-flash")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-004")

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{Path(__file__).resolve().parent.parent / 'memory_store.db'}"
    )
    read_database_url: str = os.getenv("READ_DATABASE_URL", "")
    database_path: str = os.getenv(
        "DATABASE_PATH",
        str(Path(__file__).resolve().parent.parent / "agent_memory_local.db")
    )
    database_pool_size: int = int(os.getenv("DATABASE_POOL_SIZE", "20"))
    database_max_overflow: int = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
    database_timeout_seconds: int = int(os.getenv("DATABASE_TIMEOUT_SECONDS", "10"))

    # Redis Queue & Caching
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    queue_name: str = "memory_extraction_jobs"
    dlq_name: str = "memory_extraction_dlq"
    max_worker_retries: int = int(os.getenv("MAX_WORKER_RETRIES", "3"))

    # Security & Encryption at Rest
    # Default key provided for out-of-the-box local testing; must override in production
    memory_encryption_key: str = os.getenv(
        "MEMORY_ENCRYPTION_KEY",
        "v_s4K3-x1g_bS9c6vT7rU9yP8wL4zM2aN0oP3eR6tY8="
    )
    jwt_secret: str = os.getenv("JWT_SECRET", "super_secret_production_jwt_key_9812")

    # Server & Operations
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    environment: str = os.getenv("ENVIRONMENT", "production")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    rate_limit_default_rpm: int = int(os.getenv("RATE_LIMIT_DEFAULT_RPM", "120"))
    max_payload_size_bytes: int = int(os.getenv("MAX_PAYLOAD_SIZE_BYTES", "1048576"))

    # B2B Billing & Subscriptions (Stripe & Razorpay)
    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "sk_test_mock_secret_key_12345")
    stripe_publishable_key: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_mock_key_12345")
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_mock_stripe_webhook_secret")
    razorpay_key_id: str = os.getenv("RAZORPAY_KEY_ID", "rzp_test_mock_key_id_123")
    razorpay_key_secret: str = os.getenv("RAZORPAY_KEY_SECRET", "mock_razorpay_secret_key_456")
    razorpay_webhook_secret: str = os.getenv("RAZORPAY_WEBHOOK_SECRET", "mock_razorpay_webhook_secret")
    billing_success_url: str = os.getenv("BILLING_SUCCESS_URL", "http://localhost:8000/dashboard?billing=success")
    billing_cancel_url: str = os.getenv("BILLING_CANCEL_URL", "http://localhost:8000/dashboard?billing=cancel")

    # Step 2: Auth & Team Workspaces (Clerk & RBAC)
    clerk_secret_key: str = os.getenv("CLERK_SECRET_KEY", "mock_clerk_secret_key")
    clerk_webhook_secret: str = os.getenv("CLERK_WEBHOOK_SECRET", "whsec_mock_clerk_webhook_secret")
    clerk_publishable_key: str = os.getenv("CLERK_PUBLISHABLE_KEY", "pk_test_mock_clerk_publishable_key")
    rbac_emergency_bypass: bool = os.getenv("RBAC_EMERGENCY_BYPASS", "false").lower() in ("true", "1", "yes")

    # Resend Transactional Email Configuration
    resend_api_key: str = os.getenv("RESEND_API_KEY", "")
    resend_from_email: str = os.getenv("RESEND_FROM_EMAIL", "MemoryBrain <onboarding@resend.dev>")
    app_base_url: str = os.getenv("APP_BASE_URL", "http://localhost:8000")

    # Memory Engine Hyperparameters
    decay_rate_lambda: float = 0.005  # Ebbinghaus decay per day
    relevance_threshold: float = 0.40  # Minimum hybrid score
    default_token_limit: int = 300

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
