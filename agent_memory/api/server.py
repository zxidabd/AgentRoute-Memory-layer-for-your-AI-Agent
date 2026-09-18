"""Hardened Production FastAPI Application Server."""

import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from .middleware.request_id import RequestIDMiddleware
from .middleware.idempotency import IdempotencyMiddleware
from .middleware.rate_limiter import RateLimiterMiddleware
from .routes.v1_memories import router as v1_memories_router
from .routes.v1_keys import router as v1_keys_router
from .routes.v1_privacy import router as v1_privacy_router
from .routes.v1_webhooks import router as v1_webhooks_router
from .routes.v1_billing import router as v1_billing_router
from .routes.v1_workspaces import router as v1_workspaces_router
from .routes.v1_compliance import router as v1_compliance_router
from .routes.v1_analytics import router as v1_analytics_router
from .routes.v1_data_assets import router as v1_data_assets_router
from .routes.health import router as health_router
from ..mcp.sse_router import router as mcp_router
from ..database import init_db
from ..observability.metrics import record_api_request
from ..observability.logging import log_event
from .. import __version__

app = FastAPI(
    title="MemoryBrain Platform API (Production v1)",
    description="Enterprise-grade, high-performance Long-Term Memory Layer for AI Agents.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 1. Middlewares (Order: Outermost to Innermost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimiterMiddleware)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(RequestIDMiddleware)


# 2. Timing & Metrics Middleware
@app.middleware("http")
async def metrics_and_logging_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_sec = time.time() - start_time
    duration_ms = duration_sec * 1000.0

    # Record Prometheus metrics
    record_api_request(
        endpoint=request.url.path,
        method=request.method,
        status=response.status_code,
        latency_sec=duration_sec
    )

    # Structured JSON log
    req_id = getattr(request.state, "request_id", None)
    log_event(
        message=f"{request.method} {request.url.path} -> {response.status_code} in {duration_ms:.2f}ms",
        request_id=req_id,
        latency_ms=duration_ms
    )

    return response


# 3. Standardized RFC 7807 Error Envelope Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", "unknown")
    status_code = getattr(exc, "status_code", 500)
    detail = getattr(exc, "detail", str(exc))

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR" if status_code == 500 else "REQUEST_ERROR",
                "message": detail,
            },
            "meta": {
                "request_id": req_id,
                "timestamp": str(time.time()),
                "path": request.url.path
            }
        },
        headers={"X-Request-ID": req_id}
    )


# 4. Route Registration
app.include_router(v1_memories_router)
app.include_router(v1_keys_router)
app.include_router(v1_privacy_router)
app.include_router(v1_webhooks_router)
app.include_router(v1_billing_router)
app.include_router(v1_workspaces_router)
app.include_router(v1_compliance_router)
app.include_router(v1_analytics_router)
app.include_router(v1_data_assets_router)
app.include_router(mcp_router)
app.include_router(health_router)


# 5. Application Startup
@app.on_event("startup")
def on_startup():
    init_db()
    log_event("MemoryBrain production engine initialized and database verified.")


from pathlib import Path
from fastapi.responses import JSONResponse, FileResponse

LANDING_FILE = Path(__file__).resolve().parent.parent.parent / "landing.html"
DASHBOARD_FILE = Path(__file__).resolve().parent.parent.parent / "dashboard.html"
PLAYGROUND_FILE = Path(__file__).resolve().parent.parent.parent / "docs" / "playground.html"


@app.get("/dashboard", include_in_schema=False)
def serve_dashboard():
    if DASHBOARD_FILE.exists():
        return FileResponse(str(DASHBOARD_FILE), media_type="text/html")
    return JSONResponse(status_code=404, content={"error": "dashboard.html not found"})


@app.get("/playground", include_in_schema=False)
def serve_playground():
    if PLAYGROUND_FILE.exists():
        return FileResponse(str(PLAYGROUND_FILE), media_type="text/html")
    return JSONResponse(status_code=404, content={"error": "playground.html not found"})


@app.get("/landing", include_in_schema=False)
@app.get("/", include_in_schema=False)
def serve_landing_or_root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept or request.url.path == "/landing" or request.url.path == "/":
        if LANDING_FILE.exists():
            return FileResponse(str(LANDING_FILE), media_type="text/html")
    return {
        "service": "MemoryBrain Platform",
        "version": "1.0.0",
        "status": "online",
        "docs_url": "/docs",
        "mcp_sse": "/mcp/sse",
        "landing": "/landing",
        "dashboard": "/dashboard",
        "playground": "/playground",
        "docs": "/docs",
        "metrics": "/metrics"
    }
