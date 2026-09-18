"""Idempotency-Key middleware to prevent duplicate operations on network retries."""

import time
from typing import Dict, Tuple
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Caches responses for requests containing an Idempotency-Key header."""

    def __init__(self, app, ttl_seconds: int = 86400):
        super().__init__(app)
        self.ttl_seconds = ttl_seconds
        # In-memory store: {idempotency_key: (cached_body, status_code, timestamp)}
        self._cache: Dict[str, Tuple[bytes, int, float]] = {}

    async def dispatch(self, request: Request, call_next) -> Response:
        # Idempotency is only enforced on mutating HTTP methods (POST, PATCH)
        if request.method not in ("POST", "PATCH"):
            return await call_next(request)

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return await call_next(request)

        # Check if key is already cached and valid
        now = time.time()
        if idempotency_key in self._cache:
            body, status_code, cached_time = self._cache[idempotency_key]
            if now - cached_time < self.ttl_seconds:
                response = Response(content=body, status_code=status_code, media_type="application/json")
                response.headers["Idempotency-Replay"] = "true"
                return response

        # Execute request and capture response
        response = await call_next(request)

        # Only cache successful or accepted mutations
        if 200 <= response.status_code < 300:
            response_body = [section async for section in response.body_iterator]
            full_body = b"".join(response_body)
            self._cache[idempotency_key] = (full_body, response.status_code, now)
            # Reconstruct response to return to client
            return Response(
                content=full_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )

        return response
