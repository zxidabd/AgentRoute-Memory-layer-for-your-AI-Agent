"""Structured JSON Logging with request and tenant correlation IDs."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Dict, Any, Optional


class JSONFormatter(logging.Formatter):
    """Formats log records into structured JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation IDs if provided in record
        if hasattr(record, "request_id"):
            log_obj["request_id"] = record.request_id
        if hasattr(record, "org_id"):
            log_obj["org_id"] = record.org_id
        if hasattr(record, "project_id"):
            log_obj["project_id"] = record.project_id
        if hasattr(record, "latency_ms"):
            log_obj["latency_ms"] = record.latency_ms

        return json.dumps(log_obj)


def setup_logger(name: str = "memorybrain", level: str = "INFO") -> logging.Logger:
    """Configures structured JSON logger."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

    return logger


logger = setup_logger()


def get_logger(name: str = "memorybrain") -> logging.Logger:
    return logging.getLogger(name)


def log_event(
    message: str,
    level: str = "info",
    request_id: Optional[str] = None,
    org_id: Optional[str] = None,
    latency_ms: Optional[float] = None,
    extra: Optional[Dict[str, Any]] = None,
):
    """Helper to log structured events with metadata tags."""
    log_data = extra or {}
    if request_id:
        log_data["request_id"] = request_id
    if org_id:
        log_data["org_id"] = org_id
    if latency_ms is not None:
        log_data["latency_ms"] = latency_ms

    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn(message, extra=log_data)
