"""Prometheus metrics instrumentation for SRE, latency percentiles, and cost tracking."""

from typing import Dict, Any


class MetricsRegistry:
    """Collects and formats Prometheus metrics for scraping."""

    def __init__(self):
        self._counters: Dict[str, float] = {}
        self._latencies: Dict[str, list] = {}
        self._gauges: Dict[str, float] = {}
        self._has_prom = False

        try:
            from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
            self._prom_requests = Counter(
                "memory_api_requests_total",
                "Total incoming API requests",
                ["endpoint", "method", "status_code"]
            )
            self._prom_latency = Histogram(
                "memory_api_latency_seconds",
                "Request latency in seconds",
                ["endpoint"],
                buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)
            )
            self._prom_tokens = Counter(
                "memory_tokens_consumed_total",
                "Total LLM tokens consumed",
                ["model", "type"]
            )
            self._generate_latest = generate_latest
            self.content_type = CONTENT_TYPE_LATEST
            self._has_prom = True
        except ImportError:
            self._has_prom = False
            self.content_type = "text/plain; version=0.0.4"

    def record_request(self, endpoint: str, method: str, status_code: int, latency_sec: float):
        """Records an API request and its latency."""
        if self._has_prom:
            try:
                self._prom_requests.labels(endpoint=endpoint, method=method, status_code=str(status_code)).inc()
                self._prom_latency.labels(endpoint=endpoint).observe(latency_sec)
                return
            except Exception:
                pass

        # In-memory tracking fallback
        key = f"{method}_{endpoint}_{status_code}"
        self._counters[key] = self._counters.get(key, 0) + 1
        if endpoint not in self._latencies:
            self._latencies[endpoint] = []
        self._latencies[endpoint].append(latency_sec)
        if len(self._latencies[endpoint]) > 1000:
            self._latencies[endpoint].pop(0)

    def record_tokens(self, model: str, token_type: str, count: int):
        """Records LLM input/output tokens for cost tracking."""
        if self._has_prom:
            try:
                self._prom_tokens.labels(model=model, type=token_type).inc(count)
                return
            except Exception:
                pass

        key = f"tokens_{model}_{token_type}"
        self._counters[key] = self._counters.get(key, 0) + count

    def generate_metrics_text(self) -> bytes:
        """Generates Prometheus-compatible text output for /metrics endpoint."""
        if self._has_prom:
            try:
                return self._generate_latest()
            except Exception:
                pass

        lines = ["# HELP memory_api_requests_total Total API requests", "# TYPE memory_api_requests_total counter"]
        for k, v in self._counters.items():
            lines.append(f'memory_api_requests_total{{label="{k}"}} {v}')
        return "\n".join(lines).encode("utf-8")


metrics_registry = MetricsRegistry()


def record_api_request(endpoint: str, method: str, status: int, latency_sec: float):
    metrics_registry.record_request(endpoint, method, status, latency_sec)


def record_token_usage(model: str, token_type: str, count: int):
    metrics_registry.record_tokens(model, token_type, count)
