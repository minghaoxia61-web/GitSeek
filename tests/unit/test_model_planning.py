import asyncio
import json

import httpx

from packages.model_planning import OpenAIQueryPlanner


def test_openai_query_planner_uses_structured_output_and_sanitizes_terms() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "gpt-5.6-luna"
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
