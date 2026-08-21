import logging
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from packages.observability import runtime_metrics

logger = logging.getLogger("gitseek.requests")


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid4()))[:100]
        started = perf_counter()
        response = await call_next(request)
        duration_ms = (perf_counter() - started) * 1000
        runtime_metrics.record(request.url.path, response.status_code, duration_ms)
        response.headers["X-Request-ID"] = request_id
        response.headers["Server-Timing"] = f'app;dur={duration_ms:.1f}'
        logger.info(
            "request_complete method=%s path=%s status=%s duration_ms=%.1f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response


class PublicRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        search_limit: int,
        agent_limit: int,
    ) -> None:
        super().__init__(app)
        self._limits = {
            "/api/v1/search": max(1, search_limit),
            "/api/v1/agent/runs": max(1, agent_limit),
            "/api/v1/agent/runs/stream": max(1, agent_limit),
        }
        self._profile_match_limit = max(1, agent_limit)
        self._requests: dict[tuple[str, str], deque[datetime]] = defaultdict(deque)
        self._lock = Lock()

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        rate_path = request.url.path
        limit = self._limits.get(rate_path)
        if request.method == "GET" and "/issue-matches/" in rate_path:
            limit = self._profile_match_limit
            rate_path = "/api/v1/repos/:owner/:repo/issue-matches/:username"
        if limit is None or request.method not in {"GET", "POST"}:
            return await call_next(request)
        forwarded = request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for")
        client_id = (forwarded.split(",", 1)[0].strip() if forwarded else "") or (
            request.client.host if request.client else "unknown"
        )
        now = datetime.now(UTC)
        key = (client_id, rate_path)
        with self._lock:
            bucket = self._requests[key]
            cutoff = now - timedelta(minutes=1)
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, 60 - int((now - bucket[0]).total_seconds()))
                return JSONResponse(
                    status_code=429,
                    content={"detail": "请求过于频繁，请稍后再试。"},
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )
            bucket.append(now)
            remaining = limit - len(bucket)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
