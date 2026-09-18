"""Typed exceptions for the MemoryBrain Python SDK."""

from typing import Optional, Dict, Any


class MemoryBrainError(Exception):
    """Base exception for all MemoryBrain SDK operations."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
        response_body: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code or "UNKNOWN_ERROR"
        self.response_body = response_body or {}
        self.request_id = request_id

    def __str__(self) -> str:
        parts = [f"[{self.code}] {self.message}"]
        if self.status_code:
            parts.append(f"(HTTP {self.status_code})")
        if self.request_id:
            parts.append(f"[req_id: {self.request_id}]")
        return " ".join(parts)


class AuthError(MemoryBrainError):
    """Raised when authentication fails (HTTP 401). Invalid, expired, or missing API key."""

    def __init__(self, message: str = "Invalid, expired, or revoked API key. Please check your MEMORYBRAIN_API_KEY.", **kwargs):
        super().__init__(message, status_code=401, code="AUTH_ERROR", **kwargs)


class PermissionDeniedError(MemoryBrainError):
    """Raised when an operation is forbidden for the current role (HTTP 403)."""

    def __init__(self, message: str = "Permission denied for this operation.", **kwargs):
        super().__init__(message, status_code=403, code="PERMISSION_DENIED", **kwargs)


class NotFoundError(MemoryBrainError):
    """Raised when a requested memory or entity does not exist (HTTP 404)."""

    def __init__(self, message: str = "Resource not found.", **kwargs):
        super().__init__(message, status_code=404, code="NOT_FOUND", **kwargs)


class QuotaExceededError(MemoryBrainError):
    """Raised when account memory cap or monthly request quota is exceeded (HTTP 429)."""

    def __init__(self, message: str = "Plan limit reached. Upgrade your subscription or enable overages in the dashboard.", **kwargs):
        super().__init__(message, status_code=429, code="QUOTA_EXCEEDED", **kwargs)


class RateLimitError(MemoryBrainError):
    """Raised when request rate limit (RPM) is exceeded (HTTP 429)."""

    def __init__(self, message: str = "Rate limit exceeded. Please back off and retry.", **kwargs):
        super().__init__(message, status_code=429, code="RATE_LIMIT_EXCEEDED", **kwargs)


class ServerError(MemoryBrainError):
    """Raised when MemoryBrain encounters an unexpected 5xx server error."""

    def __init__(self, message: str = "Internal server error. Our engineering team has been alerted.", status_code: int = 500, **kwargs):
        super().__init__(message, status_code=status_code, code="SERVER_ERROR", **kwargs)
