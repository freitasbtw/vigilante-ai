"""Structured logging + Prometheus metrics.

`configure_logging()` runs once at app startup. `metrics_router` exposes
/metrics for Prometheus scraping.
"""

from __future__ import annotations

import logging
import sys

import structlog
from fastapi import APIRouter, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


def configure_logging(level: str = "INFO") -> None:
    """Configure stdlib + structlog to emit JSON lines."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


# --- Prometheus metrics ---

stream_fps = Gauge(
    "vigilante_stream_fps",
    "Current FPS per camera",
    labelnames=["camera_id"],
)

inference_latency = Histogram(
    "vigilante_inference_latency_seconds",
    "Detector inference latency",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0),
)

alerts_total = Counter(
    "vigilante_alerts_total",
    "Total alerts generated",
    labelnames=["camera_id", "violation_type"],
)

stream_reconnects = Counter(
    "vigilante_stream_reconnects_total",
    "Total RTSP/webcam reconnects",
    labelnames=["camera_id"],
)

stream_online = Gauge(
    "vigilante_stream_online",
    "1 if the stream is currently producing frames, else 0",
    labelnames=["camera_id"],
)


metrics_router = APIRouter()


@metrics_router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
