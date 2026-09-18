"""Circuit Breaker & Resilience wrapper for external LLM and embedding providers."""

import time
from enum import Enum
from typing import Callable, Any, Optional


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal health: requests pass through
    OPEN = "OPEN"            # Tripped: requests immediately routed to fallback
    HALF_OPEN = "HALF_OPEN"  # Testing recovery with single probe request


class CircuitBreakerOpenException(Exception):
    """Raised when the circuit breaker is OPEN and no fallback is available."""
    pass


class CircuitBreaker:
    """Protects against cascading external service failures with auto-recovery."""

    def __init__(
        self,
        name: str = "LLM_Provider",
        failure_threshold: int = 3,
        recovery_timeout_sec: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_sec
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0

    def call(self, func: Callable, fallback: Optional[Callable] = None, *args, **kwargs) -> Any:
        """Executes a function through the circuit breaker guard."""
        now = time.time()

        # Check if recovery timeout has passed to attempt HALF_OPEN probe
        if self.state == CircuitState.OPEN:
            if now - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
            else:
                if fallback:
                    return fallback(*args, **kwargs)
                raise CircuitBreakerOpenException(
                    f"Circuit breaker '{self.name}' is OPEN. Fast-failing request."
                )

        try:
            result = func(*args, **kwargs)
            # Success in CLOSED or HALF_OPEN resets the breaker
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
            return result

        except Exception as exc:
            self.failure_count += 1
            self.last_failure_time = now

            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN

            if fallback:
                return fallback(*args, **kwargs)

            raise exc


# Global circuit breaker singleton for LLM calls
llm_circuit_breaker = CircuitBreaker(name="Gemini_2.5_Flash", failure_threshold=3, recovery_timeout_sec=30.0)
