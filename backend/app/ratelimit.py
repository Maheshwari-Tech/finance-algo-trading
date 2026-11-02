"""Per-client-IP rate limiting for the sign-in endpoints.

With REDIS_URL set (Valkey/Redis), counters are shared by every app replica. Without it, an in-process
sliding window is used, which is correct for a single container. If Redis is unreachable the limiter
fails open (logs and allows) so an outage of the cache never locks everyone out; the per-number and
global wrong-code limits in the database still apply.

The client IP comes from uvicorn's --proxy-headers, which trusts X-Forwarded-For from the reverse proxy only.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from fastapi import HTTPException, Request

from .observability import RATE_LIMITED

log = logging.getLogger("backtest.ratelimit")


class IpRateLimiter:
    def __init__(self, per_minute: int, redis_url: Optional[str] = None):
        self.per_minute = per_minute
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._redis = None
        if redis_url:
            import redis  # imported lazily so local runs don't need it configured

            self._redis = redis.Redis.from_url(redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)

    @property
    def redis(self):
        return self._redis

    def check(self, key: str) -> bool:
        if self._redis is not None:
            try:
                bucket = f"rl:{key}:{int(time.time() // 60)}"
                pipe = self._redis.pipeline()
                pipe.incr(bucket)
                pipe.expire(bucket, 120)
                count = pipe.execute()[0]
                return int(count) <= self.per_minute
            except Exception:  # noqa: BLE001 - fail open, see module docstring
                log.warning("Rate limiter: Redis unavailable, allowing request", exc_info=True)
                return True
        return self._check_local(key)

    def _check_local(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            if len(self._hits) > 50_000:  # drop idle keys so memory stays bounded
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > 60]:
                    del self._hits[k]
            return True


def limit_by_ip(request: Request) -> None:
    limiter: IpRateLimiter = request.app.state.ip_limiter
    ip = request.client.host if request.client else "unknown"
    if not limiter.check(ip):
        route = getattr(request.scope.get("route"), "path", "unknown")
        RATE_LIMITED.labels(route).inc()
        raise HTTPException(429, "Too many requests. Please wait a minute and try again")
