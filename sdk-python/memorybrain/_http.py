"""Robust zero-dependency HTTP client with exponential backoff retries and error parsing."""

import json
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, Any, Optional
from .exceptions import (
    MemoryBrainError,
    AuthError,
    PermissionDeniedError,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    ServerError
)


class HTTPClient:
    """Internal HTTP transport layer for MemoryBrain SDK."""

    DEFAULT_BASE_URL = "https://api.memorybrain.ai"

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5
    ):
        self.api_key = api_key.strip()
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Executes an HTTP request with automatic retries on transient errors."""
        url = f"{self.base_url}{path}"
        if params:
            query_str = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if query_str:
                url = f"{url}?{query_str}"

        req_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "MemoryBrain-Python-SDK/1.0.0",
            "Accept": "application/json"
        }
        if headers:
            req_headers.update(headers)

        data = json.dumps(json_body).encode("utf-8") if json_body is not None else None

        last_error = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    raw_content = response.read().decode("utf-8")
                    req_id = response.headers.get("X-Request-ID")
                    if not raw_content:
                        return {"status": "ok"}
                    try:
                        parsed = json.loads(raw_content)
                        if isinstance(parsed, dict) and req_id and "meta" not in parsed:
                            parsed["_request_id"] = req_id
                        return parsed
                    except Exception:
                        return {"content": raw_content}

            except urllib.error.HTTPError as err:
                status_code = err.code
                err_content = err.read().decode("utf-8")
                req_id = err.headers.get("X-Request-ID")
                parsed_err = {}
                try:
                    parsed_err = json.loads(err_content)
                except Exception:
                    pass

                err_message = self._extract_error_message(parsed_err, err_content, status_code)

                # 401 Unauthorized
                if status_code == 401:
                    raise AuthError(message=err_message, response_body=parsed_err, request_id=req_id)

                # 403 Forbidden
                if status_code == 403:
                    raise PermissionDeniedError(message=err_message, response_body=parsed_err, request_id=req_id)

                # 404 Not Found
                if status_code == 404:
                    raise NotFoundError(message=err_message, response_body=parsed_err, request_id=req_id)

                # 429 Rate Limit vs Quota Cap
                if status_code == 429:
                    msg_lower = err_message.lower()
                    if "limit reached" in msg_lower or "quota" in msg_lower or "upgrade" in msg_lower or "frozen" in msg_lower:
                        raise QuotaExceededError(message=err_message, response_body=parsed_err, request_id=req_id)
                    # Transient rate limit: retry with backoff if attempts remain
                    if attempt < self.max_retries:
                        sleep_time = self.backoff_factor * (2 ** attempt)
                        time.sleep(sleep_time)
                        continue
                    raise RateLimitError(message=err_message, response_body=parsed_err, request_id=req_id)

                # 5xx Server Error: retry if attempts remain
                if 500 <= status_code < 600:
                    last_error = ServerError(message=err_message, status_code=status_code, response_body=parsed_err, request_id=req_id)
                    if attempt < self.max_retries:
                        sleep_time = self.backoff_factor * (2 ** attempt)
                        time.sleep(sleep_time)
                        continue
                    raise last_error

                # Other HTTP errors (e.g. 400 Bad Request)
                raise MemoryBrainError(
                    message=err_message,
                    status_code=status_code,
                    response_body=parsed_err,
                    request_id=req_id
                )

            except (urllib.error.URLError, TimeoutError) as err:
                last_error = err
                if attempt < self.max_retries:
                    sleep_time = self.backoff_factor * (2 ** attempt)
                    time.sleep(sleep_time)
                    continue
                raise MemoryBrainError(f"Network connection failed: {str(err)}")

        if last_error:
            raise last_error
        raise MemoryBrainError("Request failed after retries.")

    def _extract_error_message(self, parsed: Dict[str, Any], raw: str, code: int) -> str:
        """Extracts human-readable error description from RFC 7807 or FastAPI responses."""
        if isinstance(parsed, dict):
            # Format: {"error": {"message": "..."}}
            if "error" in parsed and isinstance(parsed["error"], dict) and "message" in parsed["error"]:
                return str(parsed["error"]["message"])
            # Format: {"detail": "..."}
            if "detail" in parsed:
                return str(parsed["detail"])
            if "message" in parsed:
                return str(parsed["message"])
        return raw or f"HTTP {code} Error"
