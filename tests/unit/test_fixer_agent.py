import asyncio

from packages.agent_core.fixer import (
    FAILURE_ROUNDS_EXHAUSTED,
    FAILURE_TOKEN_BUDGET,
    FixerAgent,
    FixerConfig,
)
from packages.agent_core.llm import ChatResult
from packages.agent_core.locator import LocatorCandidate
from packages.sandbox import LocalSandbox


class StubChat:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls = 0

    async def complete(self, messages, *, temperature=0.2, max_tokens=4096):  # noqa: ANN001
        self.calls += 1
        return ChatResult(
            content=self.replies[min(self.calls - 1, len(self.replies) - 1)],
            input_tokens=10,
            output_tokens=5,
            model="stub-model",
        )


def make_candidate(path: str = "src/auth.py") -> LocatorCandidate:
    return LocatorCandidate(
        chunk_id=1,
        path=path,
        name="login_user",
        kind="function",
        start_line=1,
        end_line=2,
        score=0.03,
        channels=("keyword",),
        snippet="def login_user(token):\n    return token",
    )


def run_agent(agent: FixerAgent):
    return asyncio.run(agent.run())


def test_successful_run_collects_steps_and_diff(tmp_path):
    chat = StubChat([
        "```bash\necho investigating\n```\nFINISH: fixed the token check",
    ])
    sandbox = LocalSandbox(tmp_path)
    sandbox.write_file("src/auth.py", "def login_user(token):\n    return token\n")
    agent = FixerAgent(
        chat_client=chat,
        sandbox=sandbox,
        issue_text="#1 login broken",
        locator_candidates=[make_candidate()],
        config=FixerConfig(model="stub-model"),
    )
    steps: list = []

    async def collect(step) -> None:  # noqa: ANN001 - FixerStepTrace
        steps.append(step)

    agent._on_step = collect
    result = run_agent(agent)

    assert result.success
    assert result.summary == "fixed the token check"
    assert result.rounds == 1
    assert result.token_in == 10 and result.token_out == 5
    assert [step.tool for step in steps] == ["run_bash", "finish"]


def test_multi_round_reflection_then_finish(tmp_path):
    chat = StubChat([
        "VIEW src/auth.py",
        "FINISH: patched after inspecting",
    ])
    sandbox = LocalSandbox(tmp_path)
    sandbox.write_file("src/auth.py", "def login_user(token):\n    return token\n")
    agent = FixerAgent(
        chat_client=chat,
        sandbox=sandbox,
        issue_text="#1 login broken",
        locator_candidates=[],
        config=FixerConfig(model="stub-model"),
    )
    result = run_agent(agent)
    assert result.success
    assert result.rounds == 2


def test_token_budget_stops_the_loop(tmp_path):
    chat = StubChat(["```bash\necho round-one\n```"])
    agent = FixerAgent(
        chat_client=chat,
        sandbox=LocalSandbox(tmp_path),
        issue_text="#1",
        locator_candidates=[],
        config=FixerConfig(model="stub-model", token_budget=15, max_rounds=5),
    )
    result = run_agent(agent)
    assert not result.success
    assert result.failure_category == FAILURE_TOKEN_BUDGET
    assert chat.calls == 1


def test_rounds_exhaustion_marks_failure(tmp_path):
    chat = StubChat(["```bash\necho still trying\n```"])
    agent = FixerAgent(
        chat_client=chat,
        sandbox=LocalSandbox(tmp_path),
        issue_text="#1",
        locator_candidates=[],
        config=FixerConfig(model="stub-model", max_rounds=2),
    )
    result = run_agent(agent)
    assert not result.success
    assert result.failure_category == FAILURE_ROUNDS_EXHAUSTED
    assert result.rounds == 2


def test_no_tool_call_gets_reminder_not_failure(tmp_path):
    chat = StubChat(["I will look around first.", "FINISH: ok after reminder"])
    agent = FixerAgent(
        chat_client=chat,
        sandbox=LocalSandbox(tmp_path),
        issue_text="#1",
        locator_candidates=[],
        config=FixerConfig(model="stub-model"),
    )
    result = run_agent(agent)
    assert result.success
    assert result.rounds == 2
