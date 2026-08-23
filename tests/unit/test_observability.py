from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.observability import PublicRateLimitMiddleware, RequestObservabilityMiddleware
from packages.observability.runtime import RuntimeMetrics


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


def test_profile_matching_uses_one_shared_dynamic_route_bucket() -> None:
    app = FastAPI()
    app.add_middleware(PublicRateLimitMiddleware, search_limit=10, agent_limit=1)

    @app.get("/api/v1/repos/{owner}/{repo}/issue-matches/{username}")
    async def match(owner: str, repo: str, username: str) -> dict:
        return {"owner": owner, "repo": repo, "username": username}

    with TestClient(app) as client:
        first = client.get("/api/v1/repos/a/one/issue-matches/user-a")
        limited = client.get("/api/v1/repos/b/two/issue-matches/user-b")

    assert first.status_code == 200
    assert limited.status_code == 429


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


def test_runtime_metrics_report_percentiles_errors_tokens_and_cost() -> None:
    metrics = RuntimeMetrics()
    for duration in (10.0, 20.0, 30.0, 100.0):
        metrics.record("/search", 500 if duration == 100 else 200, duration)
    metrics.record_external(
        "model:test",
        duration_ms=50,
        error=False,
        input_tokens=1_000,
        output_tokens=200,
        estimated_cost_usd=0.0014,
    )
    now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    metrics.record_search(
        cache_hit=False,
        github_attempted=True,
        github_degraded=False,
        total_duration_ms=120,
        channel_latency_ms={"local_keyword": 10, "github_live": 80},
        recorded_at=now,
    )
    metrics.record_search(
        cache_hit=True,
        github_attempted=False,
        github_degraded=False,
        total_duration_ms=15,
        recorded_at=now + timedelta(minutes=1),
    )
    metrics.record_search(
        cache_hit=False,
        github_attempted=True,
        github_degraded=True,
        total_duration_ms=200,
        channel_latency_ms={"local_keyword": 20, "github_live": 150},
        recorded_at=now + timedelta(minutes=1),
    )

    snapshot = metrics.snapshot()
    assert snapshot["paths"]["/search"]["p50_duration_ms"] == 30.0
    assert snapshot["paths"]["/search"]["p95_duration_ms"] == 100.0
    assert snapshot["paths"]["/search"]["error_rate"] == 0.25
    assert snapshot["external_services"]["model:test"]["input_tokens"] == 1_000
    assert snapshot["external_services"]["model:test"]["estimated_cost_usd"] == 0.0014
    assert snapshot["search"]["searches"] == 3
    assert snapshot["search"]["cache_hit_rate"] == 0.3333
    assert snapshot["search"]["github_degradation_rate"] == 0.5
    assert snapshot["search"]["p50_duration_ms"] == 120
    assert snapshot["search"]["p95_duration_ms"] == 200
    assert snapshot["search"]["channels"]["github_live"]["p95_duration_ms"] == 150
    assert len(snapshot["search"]["trend"]) == 2
