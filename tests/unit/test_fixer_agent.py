import asyncio
import subprocess

import pytest

from packages.agent_core.fixer import (
    FAILURE_NO_PATCH,
    FAILURE_PATCH_LOGIC,
    FAILURE_PATCH_VALIDATION,
    FAILURE_ROUNDS_EXHAUSTED,
    FAILURE_TEST_MISSING,
    FAILURE_TOKEN_BUDGET,
    FixerAgent,
    FixerConfig,
)
from packages.agent_core.llm import ChatResult
from packages.agent_core.locator import LocatorCandidate
from packages.sandbox import LocalSandbox
from packages.sandbox.base import ExecResult


class StubChat:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls = 0
        self.received_messages = []

    async def complete(self, messages, *, temperature=0.2, max_tokens=4096):  # noqa: ANN001
        self.calls += 1
        self.received_messages.append([dict(message) for message in messages])
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


def test_finish_without_verified_patch_is_not_success(tmp_path):
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

    assert not result.success
    assert result.model_finished
    assert not result.test_executed
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
    assert not result.success
    assert result.model_finished
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
    assert not result.success
    assert result.model_finished
    assert result.rounds == 2


def test_nonfinal_round_executes_commands_and_patch_once(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    sandbox = LocalSandbox(tmp_path)
    sandbox.write_file("src/auth.py", "def login_user(token):\n    return token\n")
    subprocess.run(["git", "add", "src/auth.py"], cwd=tmp_path, check=True, capture_output=True)
    patch = (
        "--- a/src/auth.py\n+++ b/src/auth.py\n"
        "@@ -1,2 +1,2 @@\n def login_user(token):\n-    return token\n+    return bool(token)\n"
    )
    chat = StubChat([
        "VIEW src/auth.py\n```bash\necho tick >> marker.txt\n```\n"
        f"```diff\n{patch}```",
        "FINISH: patched after inspecting",
    ])
    steps = []

    async def collect(step):
        steps.append(step)

    result = run_agent(FixerAgent(
        chat_client=chat,
        sandbox=sandbox,
        issue_text="#1 login broken",
        locator_candidates=[],
        config=FixerConfig(model="stub-model"),
        on_step=collect,
    ))

    assert (tmp_path / "marker.txt").read_text().splitlines() == ["tick"]
    assert (tmp_path / "src/auth.py").read_text() == (
        "def login_user(token):\n    return bool(token)\n"
    )
    assert "-    return token" in result.diff
    assert "+    return bool(token)" in result.diff
    assert [step.tool for step in steps] == [
        "view_file", "run_bash", "apply_patch", "finish", "verify_patch",
    ]
    assert [step.seq for step in steps] == [1, 2, 3, 4, 5]
    assert result.apply_ok is True
    assert not result.success
    assert result.failure_category == FAILURE_TEST_MISSING
    feedback = chat.received_messages[1][-1]["content"]
    assert feedback.count('<tool name="view">') == 1
    assert feedback.count('<tool name="bash">') == 1
    assert feedback.count('<tool name="patch">') == 1
    assert "apply_failed" not in feedback


def test_finish_runs_prior_command_and_verification_once_ignores_later_tools(tmp_path):
    chat = StubChat([
        "```bash\necho before >> marker.txt\n```\n"
        "FINISH: done\n"
        "```bash\necho after >> marker.txt\n```\n"
        "FINISH: ignored summary",
    ])
    steps = []

    async def collect(step):
        steps.append(step)

    result = run_agent(FixerAgent(
        chat_client=chat,
        sandbox=LocalSandbox(tmp_path),
        issue_text="#1",
        locator_candidates=[],
        config=FixerConfig(model="stub-model", test_command="echo verified >> verification.txt"),
        on_step=collect,
    ))

    assert (tmp_path / "marker.txt").read_text().splitlines() == ["before"]
    assert (tmp_path / "verification.txt").read_text().splitlines() == ["verified"]
    assert [step.tool for step in steps] == ["run_bash", "finish", "run_tests"]
    assert result.summary == "done"
    assert chat.calls == 1


def test_failed_patch_is_reported_once_to_next_round(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    chat = StubChat([
        "```diff\n--- a/missing.py\n+++ b/missing.py\n@@ -1 +1 @@\n-old\n+new\n```",
        "FINISH: unable to apply",
    ])
    steps = []

    async def collect(step):
        steps.append(step)

    run_agent(FixerAgent(
        chat_client=chat,
        sandbox=LocalSandbox(tmp_path),
        issue_text="#1",
        locator_candidates=[],
        config=FixerConfig(model="stub-model"),
        on_step=collect,
    ))

    assert [step.tool for step in steps] == ["apply_patch", "finish"]
    assert chat.received_messages[1][-1]["content"].count("apply_failed") == 1


class VerificationSandbox:
    """Deterministic command boundary for verification failure cases."""

    def __init__(self, *, diff="--- a/a.py\n+++ b/a.py\n", test_exit=0,
                 timed_out=False, apply_exit=0, diff_exit=0):
        self.diff = diff
        self.test_exit = test_exit
        self.timed_out = timed_out
        self.apply_exit = apply_exit
        self.diff_exit = diff_exit
        self.commands = []

    async def exec(self, command, *, stdin=None, timeout_s=120):
        self.commands.append(command)
        if command.startswith("git diff"):
            return ExecResult(command, self.diff_exit, self.diff, "", 1)
        if command.startswith("git apply --reverse"):
            return ExecResult(command, self.apply_exit, "", "", 1)
        return ExecResult(command, self.test_exit, "test output", "test error", 1,
                          timed_out=self.timed_out)


@pytest.mark.parametrize(
    ("options", "test_command", "expected_success", "category", "test_ok"),
    [
        ({}, "pytest -q", True, None, True),
        ({}, None, False, FAILURE_TEST_MISSING, None),
        ({}, "  ", False, FAILURE_TEST_MISSING, None),
        ({"diff": ""}, "pytest -q", False, FAILURE_NO_PATCH, True),
        ({"test_exit": 1}, "pytest -q", False, FAILURE_PATCH_LOGIC, False),
        ({"test_exit": 124, "timed_out": True}, "pytest -q",
         False, "test_environment_error", False),
        ({"timed_out": True}, "pytest -q", False, "test_environment_error", False),
        ({"apply_exit": 1}, "pytest -q", False, FAILURE_PATCH_VALIDATION, True),
        ({"diff_exit": 1}, "pytest -q", False, FAILURE_PATCH_VALIDATION, True),
    ],
)
def test_success_requires_patch_check_and_explicit_test_evidence(
    options, test_command, expected_success, category, test_ok,
):
    result = run_agent(FixerAgent(
        chat_client=StubChat(["FINISH: fixed"]),
        sandbox=VerificationSandbox(**options),
        issue_text="#1",
        locator_candidates=[],
        config=FixerConfig(model="stub-model", test_command=test_command),
    ))
    assert result.success is expected_success
    assert result.failure_category == category
    assert result.test_ok is test_ok
    assert result.test_executed is bool(test_command and test_command.strip())
    assert result.verification()["scope"] == "workspace_tests"
