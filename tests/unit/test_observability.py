from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.observability import PublicRateLimitMiddleware, RequestObservabilityMiddleware


def test_public_rate_limit_returns_retry_metadata() -> None:
    app = FastAPI()
    app.add_middleware(
        PublicRateLimitMiddleware,
        search_limit=2,
        agent_limit=1,
    )

    @app.post("/api/v1/search")
    async def search() -> dict:
        return {"ok": True}

    with TestClient(app) as client:
        first = client.post("/api/v1/search")
        second = client.post("/api/v1/search")
        limited = client.post("/api/v1/search")

    assert first.headers["X-RateLimit-Remaining"] == "1"
    assert second.headers["X-RateLimit-Remaining"] == "0"
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0


def test_observability_adds_request_trace_headers() -> None:
    app = FastAPI()
    app.add_middleware(RequestObservabilityMiddleware)

    @app.get("/probe")
    async def probe() -> dict:
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/probe", headers={"X-Request-ID": "known-request"})

    assert response.headers["X-Request-ID"] == "known-request"
    assert response.headers["Server-Timing"].startswith("app;dur=")
