"""Logging and Prometheus metrics.

Metrics are served on /metrics. The reverse proxy (deploy/Caddyfile) blocks that path from the internet;
Prometheus scrapes it over the internal Docker network.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Callable

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
HTTP_IN_PROGRESS = Gauge("http_requests_in_progress", "Requests being served")
BACKTESTS = Counter("backtests_total", "Backtests run", ["strategy", "outcome"])
BACKTEST_SECONDS = Histogram("backtest_duration_seconds", "Time to run one backtest",
                             buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60))
BACKTEST_BARS = Histogram("backtest_bars", "Bars in a backtest window", buckets=(30, 100, 250, 500, 1000, 2500, 5000, 10000, 50000))
OTP_REQUESTS = Counter("otp_requests_total", "OTP requests", ["outcome"])
LOGINS = Counter("logins_total", "OTP verifications", ["outcome"])
RATE_LIMITED = Counter("rate_limited_total", "Requests refused by the per-IP limiter", ["route"])
UPLOADS = Counter("dataset_uploads_total", "Admin CSV uploads", ["outcome"])
DB_UP = Gauge("db_up", "1 if the last readiness check reached the database")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname,
               "logger": record.name, "msg": record.getMessage()}
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out)


def setup_logging(level: str, as_json: bool) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter() if as_json else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


def _route_template(request: Request) -> str:
    """Use the route pattern (/api/admin/datasets/{symbol}), never the raw path, to keep label cardinality bounded."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path is None:
        return "unmatched"
    return "/{spa}" if path == "/{path:path}" else path


def install_metrics(app: FastAPI) -> None:
    @app.middleware("http")
    async def _measure(request: Request, call_next: Callable):
        if request.url.path == "/metrics":
            return await call_next(request)
        start = time.perf_counter()
        HTTP_IN_PROGRESS.inc()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            HTTP_IN_PROGRESS.dec()
            route = _route_template(request)
            HTTP_LATENCY.labels(request.method, route).observe(time.perf_counter() - start)
            HTTP_REQUESTS.labels(request.method, route, str(status)).inc()

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
