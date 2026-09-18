"""Request ID propagation middleware for distributed tracing and log correlation."""

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Ensures every HTTP request has an X-Request-ID attached to headers and response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = f"req_{uuid.uuid4().hex[:12]}"

        # Attach to request state
        request.state.request_id = request_id

        # Execute downstream handlers
        response = await call_next(request)

        # Inject into response headers
        response.headers["X-Request-ID"] = request_id
        return response
