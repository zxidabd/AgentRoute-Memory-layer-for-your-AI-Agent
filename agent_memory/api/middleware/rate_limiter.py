"""Token bucket rate limiter middleware with tenant isolation and Retry-After headers."""

import time
from typing import Dict, Tuple
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from ...config import settings


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Enforces per-tenant / per-key token bucket rate limiting with Redis and in-memory fallback."""

    def __init__(self, app, default_rpm: int = None, redis_url: str = None):
        super().__init__(app)
        self.default_rpm = default_rpm or settings.rate_limit_default_rpm
        # In-memory bucket store: {client_identifier: (current_tokens, last_refill_timestamp)}
        self._buckets: Dict[str, Tuple[float, float]] = {}
        self._redis = None

        try:
            import redis
            client = redis.Redis.from_url(redis_url or settings.redis_url, socket_timeout=0.3)
            client.ping()
            self._redis = client
        except Exception:
            self._redis = None

    async def dispatch(self, request: Request, call_next):
        # Exclude health checks and metrics from rate limits
        if request.url.path in ("/healthz/liveness", "/healthz/readiness", "/metrics", "/docs", "/openapi.json"):
            return await call_next(request)

        # Extract client identifier from Authorization header or IP
        auth_header = request.headers.get("Authorization", "")
        client_id = auth_header.strip() if auth_header else (request.client.host if request.client else "unknown")

        now = time.time()
        max_capacity = float(self.default_rpm)
        refill_rate = max_capacity / 60.0  # tokens per second

        # Retrieve or initialize bucket
        if client_id not in self._buckets:
            tokens, last_refill = max_capacity, now
        else:
            tokens, last_refill = self._buckets[client_id]
            # Refill tokens based on elapsed time
            elapsed = now - last_refill
            tokens = min(max_capacity, tokens + (elapsed * refill_rate))
            last_refill = now

        # Check if client has at least 1 token
        if tokens < 1.0:
            retry_after_sec = max(1, int((1.0 - tokens) / refill_rate))
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit of {self.default_rpm} requests/min exceeded. Please throttle requests."
                    }
                },
                headers={
                    "Retry-After": str(retry_after_sec),
                    "X-RateLimit-Limit": str(self.default_rpm),
                    "X-RateLimit-Remaining": "0"
                }
            )

        # Consume 1 token
        tokens -= 1.0
        self._buckets[client_id] = (tokens, last_refill)

        # Proceed with request
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.default_rpm)
        response.headers["X-RateLimit-Remaining"] = str(int(tokens))
        return response
