import asyncio
import json

import httpx
import pytest

from packages.model_planning import ModelPlanningError, OpenAIQueryPlanner


def test_openai_query_planner_uses_structured_output_and_sanitizes_terms() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "gpt-5.6-luna"
        assert payload["max_output_tokens"] == 2048
        assert payload["text"]["format"]["type"] == "json_schema"
        result = {
            "summary": "寻找用于桌面笔记的 TypeScript 应用",
            "language": "TypeScript",
            "technologies": ["Electron", "local-first"],
            "github_terms": ["desktop notes", "electron", "stars:>1000"],
            "licenses": [],
            "purpose": "learning",
            "exclude_archived": True,
            "pushed_after": None,
            "weekly_hours": None,
            "platform": "Windows",
            "project_size": "medium",
        }
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": json.dumps(result)}
                        ],
                    }
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await OpenAIQueryPlanner("test-key", client=client).plan(
                "我想学习做一个 Windows 桌面笔记应用"
            )

    plan = asyncio.run(run())
    assert plan.language == "TypeScript"
    assert plan.technologies == ["Electron", "local-first"]
    assert plan.github_terms == ["desktop notes", "electron", "stars1000"]
    assert plan.project_size == "medium"


def test_openai_query_planner_reports_safe_provider_error() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "Authentication failed"}},
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await OpenAIQueryPlanner("secret-key", client=client).plan("Find a project")

    with pytest.raises(ModelPlanningError) as captured:
        asyncio.run(run())

    assert str(captured.value) == (
        "model provider returned HTTP 401: Authentication failed"
    )
    assert "secret-key" not in str(captured.value)


def test_openai_query_planner_reports_incomplete_response() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
                "output": [{"type": "reasoning", "content": []}],
            },
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await OpenAIQueryPlanner("secret-key", client=client).plan("Find a project")

    with pytest.raises(ModelPlanningError) as captured:
        asyncio.run(run())

    assert str(captured.value) == "model response was incomplete: max_output_tokens"


def test_openai_query_planner_reuses_recent_parse() -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        result = {
            "summary": "Find a small FastAPI project",
            "language": "Python",
            "technologies": ["FastAPI"],
            "github_terms": ["fastapi"],
            "licenses": ["MIT"],
            "purpose": "learning",
            "exclude_archived": True,
            "pushed_after": None,
            "weekly_hours": None,
            "platform": None,
            "project_size": "small",
        }
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(result)}],
                    }
                ]
            },
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            planner = OpenAIQueryPlanner("test-key", model="cache-test-model", client=client)
            first = await planner.plan("Unique cache test query")
            second = await planner.plan("  unique   CACHE test QUERY ")
            assert first == second

    asyncio.run(run())
    assert calls == 1
