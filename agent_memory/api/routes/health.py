"""Health probes, readiness checks, and Prometheus metrics endpoint."""

from fastapi import APIRouter, Response, status
from ...database import check_db_health
from ...observability.metrics import metrics_registry

router = APIRouter(tags=["Health & SRE"])


@router.get("/healthz/liveness", summary="Container & Database Liveness Probe")
def liveness():
    """
    Scraped by Better Uptime and Cloud Load Balancer.
    Performs active roundtrip query against the database; returns 503 if primary DB is down.
    """
    db_ok = check_db_health(timeout_seconds=3)
    if not db_ok:
        return Response(
            content='{"status": "unhealthy", "error": "Primary database connectivity lost"}',
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json"
        )
    return {"status": "alive", "database": "connected"}


@router.get("/healthz/readiness", summary="Load Balancer Traffic Readiness Probe")
def readiness():
    """
    Verifies that primary DB and read replica (if configured) are ready to receive live traffic.
    """
    from ...database import check_read_db_health
    primary_ok = check_db_health(timeout_seconds=3)
    replica_ok = check_read_db_health()

    if not primary_ok:
        return Response(
            content='{"status": "unready", "error": "Primary database unreachable"}',
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json"
        )

    return {
        "status": "ready",
        "primary_db": "healthy",
        "read_replica": "healthy" if replica_ok else "fallback_to_primary"
    }


@router.get("/healthz/startup", summary="Container Startup Initialization Probe")
def startup():
    """
    Used by Cloud Run and Kubernetes to delay traffic routing until tables and models are initialized.
    """
    primary_ok = check_db_health(timeout_seconds=3)
    if not primary_ok:
        return Response(
            content='{"status": "starting", "message": "Database not yet ready"}',
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json"
        )
    return {"status": "started", "initialized": True}


@router.get("/metrics", summary="Prometheus Metrics Scraper Endpoint")
def prometheus_metrics():
    """Exposes Prometheus text format metrics for Datadog / Grafana scraping."""
    content = metrics_registry.generate_metrics_text()
    return Response(content=content, media_type=metrics_registry.content_type)
