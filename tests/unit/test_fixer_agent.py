import asyncio
from dataclasses import dataclass

import pytest

from packages.agent_core.fixer import (
    FAILURE_PATCH_LOGIC,
    FAILURE_ROUNDS_EXHAUSTED,
    FAILURE_TEST_ENVIRONMENT,
    FAILURE_TOKEN_BUDGET,
    FixerAgent,
    FixerConfig,
)
from packages.agent_core.llm import ChatResult
from packages.agent_core.locator import LocatorCandidate
from packages.sandbox.base import ExecResult

DIFF_COMMAND = "git diff --binary HEAD"
TEST_COMMAND = "python -m pytest -q"
PATCH = "--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1 +1 @@\n-return token\n+return bool(token)\n"
REVISED_PATCH = PATCH.replace("bool(token)", "token is not None")
NEW_PATCH = "diff --git a/new.py b/new.py\nnew file mode 100644\n--- /dev/null\n+++ b/new.py\n"


class StubChat:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls = 0
        self.messages: list[list[dict]] = []

    async def complete(self, messages, *, temperature=0.2, max_tokens=4096):
        assert self.calls < len(self.replies), "Unexpected extra model round"
        self.messages.append([message.copy() for message in messages])
        content = self.replies[self.calls]
        self.calls += 1
        return ChatResult(
            content=content, input_tokens=10, output_tokens=5, model="stub-model",
        )


@dataclass
class Reply:
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    patch: str | None = None
    timed_out: bool = False


class MemorySandbox:
    """A deterministic workspace: no subprocesses, filesystem, network or real git."""

    def __init__(self, *, patch="", staged="", responses=None) -> None:
        self.patch = patch
        self.staged = staged
        self.untracked = ""
        self.responses = responses or {}
        self.calls: list[tuple[str, str | None, float]] = []

    @property
    def commands(self) -> list[str]:
        return [command for command, _, _ in self.calls]

    async def exec(self, command, *, stdin=None, timeout_s=120):
        self.calls.append((command, stdin, timeout_s))
        if self.responses.get(command):
            reply = self.responses[command].pop(0)
        elif command == DIFF_COMMAND:
            reply = Reply(stdout=self.staged + self.patch)
        elif command == "fix-bug":
            reply = Reply(patch=PATCH)
        elif command == "revise-bug":
            reply = Reply(patch=REVISED_PATCH)
        elif command == "create-file":
            self.untracked = NEW_PATCH
            reply = Reply()
        elif command == "git add new.py":
            self.staged, self.untracked = self.untracked, ""
            reply = Reply()
        elif command == "git apply --check --whitespace=nowarn -":
            assert stdin and stdin.endswith("\n")
            reply = Reply()
        elif command == "git apply --whitespace=nowarn -":
            assert self.patch != stdin, "Patch applied more than once"
            reply = Reply(patch=stdin)
        elif command == TEST_COMMAND:
            reply = Reply(stdout="2 passed")
        elif command in {"inspect", "cat src/auth.py", "sed -n '1,3p' src/auth.py"}:
            reply = Reply(stdout="return token")
        else:
            raise AssertionError(f"Unexpected sandbox command: {command!r}")
        if reply.patch is not None:
            self.patch = reply.patch
        return ExecResult(
            command=command, exit_code=reply.exit_code, stdout=reply.stdout,
            stderr=reply.stderr, duration_ms=7, timed_out=reply.timed_out,
        )


def make_candidate() -> LocatorCandidate:
    return LocatorCandidate(
        chunk_id=1, path="src/auth.py", name="login_user", kind="function",
        start_line=1, end_line=2, score=0.03, channels=("keyword",),
        snippet="def login_user(token):\n    return token",
    )


def make_agent(replies, *, sandbox=None, **config_kwargs):
    config_kwargs.setdefault("max_rounds", len(replies))
    return FixerAgent(
        chat_client=StubChat(replies), sandbox=sandbox or MemorySandbox(),
        issue_text="#1 login broken", locator_candidates=[make_candidate()],
        config=FixerConfig(model="stub-model", **config_kwargs),
    )


def run_agent(agent: FixerAgent):
    return asyncio.run(agent.run())


def test_successful_run_collects_steps_and_diff():
    sandbox = MemorySandbox()
    agent = make_agent(
        [f"```bash\nfix-bug\n```\nTEST {TEST_COMMAND}\nFINISH: fixed the token check"],
        sandbox=sandbox, input_cost_per_million=2, output_cost_per_million=3,
    )
    callback_steps = []

    async def collect(step):
        callback_steps.append(step)

    agent._on_step = collect
    result = run_agent(agent)

    assert result.success and result.test_ok is True
    assert result.diff == PATCH
    assert result.summary == "fixed the token check"
    assert result.failure_category is None
    assert result.rounds == 1
    assert result.token_in == 10 and result.token_out == 5
    assert result.cost_usd == pytest.approx(35 / 1_000_000)
    assert result.steps == callback_steps
    assert [step.tool for step in result.steps] == [
        "run_bash", "select_test", "collect_diff", "run_tests", "collect_diff", "finish",
    ]
    assert [step.seq for step in result.steps] == list(range(1, len(result.steps) + 1))
    assert all(step.round == 1 for step in result.steps)
    assert sandbox.calls == [
        ("fix-bug", None, 180), (DIFF_COMMAND, None, 30),
        (TEST_COMMAND, None, 180), (DIFF_COMMAND, None, 30),
    ]


def test_each_action_and_patch_executes_once_in_order_across_rounds():
    sandbox = MemorySandbox()
    agent = make_agent([
        "VIEW src/auth.py 1 3\n```bash\ninspect\n```\n"
        f"```diff\n{PATCH}```\nTEST {TEST_COMMAND}",
        "FINISH: patched after inspecting",
    ], sandbox=sandbox)
    result = run_agent(agent)

    assert result.success and result.rounds == 2
    assert sandbox.commands == [
        "sed -n '1,3p' src/auth.py", "inspect",
        "git apply --check --whitespace=nowarn -", "git apply --whitespace=nowarn -",
        DIFF_COMMAND, TEST_COMMAND, DIFF_COMMAND,
    ]
    assert sandbox.calls[2][1] == PATCH and sandbox.calls[3][1] == PATCH
    feedback = agent._chat.messages[1][-1]["content"]
    assert feedback.count("applied") == 1
    assert "not executed yet" in feedback
    assert [step.round for step in result.steps if step.tool == "run_tests"] == [2]


def test_finish_ignores_all_following_text_and_actions():
    sandbox = MemorySandbox(patch=PATCH)
    result = run_agent(make_agent([
        f"TEST {TEST_COMMAND}\nFINISH: actual summary\n"
        "```bash\nrevise-bug\n```\nVIEW forbidden.py\nTEST false\n"
        "```diff\ninvalid patch\n```\nFINISH: ignore this summary",
    ], sandbox=sandbox))
    assert result.success and result.summary == "actual summary"
    assert result.diff == PATCH
    assert sandbox.commands == [DIFF_COMMAND, TEST_COMMAND, DIFF_COMMAND]


def test_failed_finish_also_ignores_later_actions_in_the_same_reply():
    sandbox = MemorySandbox()
    agent = make_agent([
        f"TEST {TEST_COMMAND}\nFINISH: missing patch\n```bash\nfix-bug\n```",
        "FINISH: still missing patch",
    ], sandbox=sandbox)
    result = run_agent(agent)
    assert not result.success and result.diff == ""
    assert sandbox.commands == [DIFF_COMMAND, DIFF_COMMAND]
    assert "no non-empty patch" in agent._chat.messages[1][-1]["content"]


def test_protocol_lines_in_bash_payload_do_not_finish_or_select_tests():
    command = "cat <<'EOF'\nFINISH: sample\nVIEW secret.py\nTEST false\nEOF"
    sandbox = MemorySandbox(responses={command: [Reply(stdout="sample")]})
    agent = make_agent([
        f"```bash\n{command}\n```",
        f"```bash\nfix-bug\n```\nTEST {TEST_COMMAND}\nFINISH: real fix",
    ], sandbox=sandbox)
    result = run_agent(agent)
    assert result.success and result.rounds == 2
    assert sandbox.commands == [command, "fix-bug", DIFF_COMMAND, TEST_COMMAND, DIFF_COMMAND]


@pytest.mark.parametrize("create_untracked", [False, True])
def test_no_diff_never_succeeds_or_runs_tests(create_untracked):
    sandbox = MemorySandbox()
    reply = f"TEST {TEST_COMMAND}\nFINISH: allegedly fixed"
    if create_untracked:
        reply = "```bash\ncreate-file\n```\n" + reply
    agent = make_agent([reply, "FINISH: allegedly fixed"], sandbox=sandbox)
    result = run_agent(agent)
    assert not result.success and result.test_ok is None
    assert result.diff == ""
    assert result.failure_category == FAILURE_PATCH_LOGIC
    assert result.summary.startswith("Failed: round limit exhausted.")
    assert "allegedly fixed" not in result.summary
    assert "no non-empty patch" in result.summary
    assert "no non-empty patch" in agent._chat.messages[1][-1]["content"]
    assert TEST_COMMAND not in sandbox.commands
    assert not any(command.startswith("git add") for command in sandbox.commands)


def test_nonempty_patch_without_test_selection_fails_even_after_manual_tests():
    sandbox = MemorySandbox(patch=PATCH)
    result = run_agent(make_agent([
        f"```bash\n{TEST_COMMAND}\n```\nFINISH: fixed",
    ], sandbox=sandbox))
    assert not result.success and result.test_ok is None
    assert result.diff == PATCH
    assert result.failure_category == FAILURE_PATCH_LOGIC
    assert "no test command selected" in result.summary
    assert not any(step.tool == "run_tests" for step in result.steps)


def test_missing_test_feedback_allows_selection_in_next_round():
    agent = make_agent([
        "FINISH: fixed", f"TEST {TEST_COMMAND}\nFINISH: verified fix",
    ], sandbox=MemorySandbox(patch=PATCH))
    result = run_agent(agent)
    assert result.success and result.rounds == 2
    assert "TEST <shell command>" in agent._chat.messages[1][-1]["content"]


def test_no_diff_feedback_allows_repair_in_next_round():
    agent = make_agent([
        f"TEST {TEST_COMMAND}\nFINISH: fixed",
        "```bash\nfix-bug\n```\nFINISH: verified fix",
    ])
    result = run_agent(agent)
    assert result.success and result.diff == PATCH
    assert "no non-empty patch" in agent._chat.messages[1][-1]["content"]


def test_failed_tests_are_reported_and_can_be_repaired():
    sandbox = MemorySandbox(patch=PATCH, responses={
        TEST_COMMAND: [Reply(exit_code=1, stdout="1 failed", stderr="AssertionError: token")],
    })
    agent = make_agent([
        f"TEST {TEST_COMMAND}\nFINISH: first attempt",
        "```bash\nrevise-bug\n```\nFINISH: corrected token semantics",
    ], sandbox=sandbox)
    result = run_agent(agent)

    feedback = agent._chat.messages[1][-1]["content"]
    assert "final tests failed" in feedback
    assert "exit=1" in feedback and "AssertionError: token" in feedback
    assert result.success and result.test_ok is True
    assert result.diff == REVISED_PATCH and result.rounds == 2
    assert result.summary == "corrected token semantics" and result.failure_category is None
    assert [step.output for step in result.steps if step.tool == "run_tests"] == [
        "exit=1\n1 failed\nAssertionError: token", "exit=0\n2 passed",
    ]
    assert sandbox.commands.count(TEST_COMMAND) == 2


def test_failed_tests_remain_failure_at_round_limit():
    sandbox = MemorySandbox(patch=PATCH, responses={
        TEST_COMMAND: [Reply(exit_code=1, stderr="assertion failed")],
    })
    result = run_agent(make_agent([
        f"TEST {TEST_COMMAND}\nFINISH: fixed everything",
    ], sandbox=sandbox))
    assert not result.success and result.test_ok is False
    assert result.failure_category == FAILURE_PATCH_LOGIC
    assert "assertion failed" in result.summary and "fixed everything" not in result.summary


@pytest.mark.parametrize("changed_patch", [REVISED_PATCH, ""])
def test_test_mutation_invalidates_success_and_saves_latest_patch(changed_patch):
    sandbox = MemorySandbox(patch=PATCH, responses={
        TEST_COMMAND: [Reply(stdout="passed but rewrote source", patch=changed_patch)],
    })
    result = run_agent(make_agent([
        f"TEST {TEST_COMMAND}\nFINISH: fixed",
    ], sandbox=sandbox))
    assert not result.success and result.test_ok is None
    assert result.diff == changed_patch
    assert result.failure_category == FAILURE_PATCH_LOGIC
    assert "patch changed during final tests" in result.summary
    assert sandbox.commands == [DIFF_COMMAND, TEST_COMMAND, DIFF_COMMAND]


@pytest.mark.parametrize("second_exit", [0, 1])
def test_changed_patch_requires_a_new_independent_test(second_exit):
    sandbox = MemorySandbox(patch=PATCH, responses={
        TEST_COMMAND: [
            Reply(stdout="passed old patch", patch=REVISED_PATCH),
            Reply(exit_code=second_exit, stdout="tested revised patch"),
        ],
    })
    agent = make_agent([
        f"TEST {TEST_COMMAND}\nFINISH: first patch", "FINISH: revised patch",
    ], sandbox=sandbox)
    result = run_agent(agent)
    assert result.success is (second_exit == 0)
    assert result.test_ok is (second_exit == 0)
    assert result.diff == REVISED_PATCH and result.rounds == 2
    assert sandbox.commands.count(TEST_COMMAND) == 2
    assert "patch changed" in agent._chat.messages[1][-1]["content"]


def test_edit_after_failed_verification_invalidates_old_result_at_exhaustion():
    sandbox = MemorySandbox(patch=PATCH, responses={TEST_COMMAND: [Reply(exit_code=1)]})
    result = run_agent(make_agent([
        f"TEST {TEST_COMMAND}\nFINISH: first patch", "```bash\nrevise-bug\n```",
    ], sandbox=sandbox))
    assert not result.success and result.test_ok is None
    assert result.diff == REVISED_PATCH
    assert sandbox.commands.count(TEST_COMMAND) == 1


def test_manual_passing_tests_before_an_edit_cannot_verify_the_final_patch():
    sandbox = MemorySandbox(patch=PATCH, responses={
        TEST_COMMAND: [
            Reply(stdout="old patch passed"), Reply(exit_code=1, stderr="new patch fails"),
        ],
    })
    result = run_agent(make_agent([
        f"```bash\n{TEST_COMMAND}\n```\n```bash\nrevise-bug\n```\nFINISH: fixed",
    ], sandbox=sandbox, test_command=TEST_COMMAND))
    assert not result.success and result.test_ok is False
    assert result.diff == REVISED_PATCH
    assert sandbox.commands == [
        TEST_COMMAND, "revise-bug", DIFF_COMMAND, TEST_COMMAND, DIFF_COMMAND,
    ]
    assert "new patch fails" in result.summary


def test_trusted_config_command_cannot_be_overridden_by_model():
    sandbox = MemorySandbox(patch=PATCH)
    agent = make_agent([
        "TEST true", "TEST false\nFINISH: verified",
    ], sandbox=sandbox, test_command=TEST_COMMAND)
    result = run_agent(agent)
    assert result.success and result.test_ok is True
    assert sandbox.commands == [DIFF_COMMAND, TEST_COMMAND, DIFF_COMMAND]
    assert agent.config.test_command == TEST_COMMAND
    assert "trusted project test command" in agent._chat.messages[1][-1]["content"]
    assert all("ignored" in step.output for step in result.steps if step.tool == "select_test")


def test_trusted_command_does_not_need_model_test_selection():
    result = run_agent(make_agent([
        "FINISH: verified",
    ], sandbox=MemorySandbox(patch=PATCH), test_command=TEST_COMMAND))
    assert result.success and result.test_ok is True


def test_last_selected_command_runs_only_at_finish_without_trusted_config():
    sandbox = MemorySandbox(patch=PATCH)
    result = run_agent(make_agent([
        f"TEST false\nTEST {TEST_COMMAND}", "FINISH: verified",
    ], sandbox=sandbox, test_command="  "))
    assert result.success
    assert sandbox.commands == [DIFF_COMMAND, TEST_COMMAND, DIFF_COMMAND]
    assert [step.round for step in result.steps if step.tool == "run_tests"] == [2]


@pytest.mark.parametrize("after_tests", [False, True])
def test_git_diff_failure_is_not_a_success_even_with_stdout(after_tests):
    diffs = [Reply(stdout=PATCH)] if after_tests else []
    diffs.append(Reply(exit_code=128, stdout="unusable partial diff", stderr="fatal: bad HEAD"))
    sandbox = MemorySandbox(patch=PATCH, responses={DIFF_COMMAND: diffs})
    result = run_agent(make_agent([
        f"TEST {TEST_COMMAND}\nFINISH: fixed",
    ], sandbox=sandbox))
    assert not result.success and result.test_ok is None
    assert result.diff == ""
    assert result.failure_category == FAILURE_TEST_ENVIRONMENT
    assert "exit=128" in result.summary and "fatal: bad HEAD" in result.summary
    assert sandbox.commands.count(TEST_COMMAND) == int(after_tests)


def test_git_diff_failure_feedback_allows_retry():
    sandbox = MemorySandbox(patch=PATCH, responses={
        DIFF_COMMAND: [Reply(exit_code=128, stderr="fatal: transient repository error")],
    })
    agent = make_agent([
        f"TEST {TEST_COMMAND}\nFINISH: fixed", "FINISH: verified after retry",
    ], sandbox=sandbox)
    result = run_agent(agent)
    assert result.success and result.rounds == 2
    assert "fatal: transient repository error" in agent._chat.messages[1][-1]["content"]


def test_staged_new_files_are_included_without_automatic_git_add():
    sandbox = MemorySandbox(patch=PATCH)
    result = run_agent(make_agent([
        "```bash\ncreate-file\n```\n```bash\ngit add new.py\n```\n"
        f"TEST {TEST_COMMAND}\nFINISH: added missing module",
    ], sandbox=sandbox))
    assert result.success and result.diff == NEW_PATCH + PATCH
    assert sandbox.commands.count("git add new.py") == 1
    assert sandbox.commands == [
        "create-file", "git add new.py", DIFF_COMMAND, TEST_COMMAND, DIFF_COMMAND,
    ]


def test_staged_only_binary_patch_is_preserved():
    binary_patch = "diff --git a/icon b/icon\nGIT binary patch\nliteral 3\nKcmZQzWC8#H2LJ>B\n"
    sandbox = MemorySandbox(staged=binary_patch)
    result = run_agent(make_agent([
        f"TEST {TEST_COMMAND}\nFINISH: repaired asset",
    ], sandbox=sandbox))
    assert result.success and result.diff == binary_patch


@pytest.mark.parametrize("max_rounds", [1, 5])
def test_token_budget_stops_the_loop_and_records_actual_round_count(max_rounds):
    agent = make_agent(["```bash\ninspect\n```"], token_budget=15, max_rounds=max_rounds)
    result = run_agent(agent)
    assert not result.success
    assert result.failure_category == FAILURE_TOKEN_BUDGET
    assert result.rounds == agent._chat.calls == 1
    assert "token budget exhausted" in result.summary


def test_over_budget_completion_cannot_claim_success():
    sandbox = MemorySandbox(patch=PATCH)
    result = run_agent(make_agent([
        f"TEST {TEST_COMMAND}\nFINISH: fixed",
    ], sandbox=sandbox, token_budget=14))
    assert not result.success and result.test_ok is None
    assert result.failure_category == FAILURE_TOKEN_BUDGET
    assert TEST_COMMAND not in sandbox.commands


def test_zero_budget_does_not_call_model():
    agent = make_agent([], token_budget=0, max_rounds=5)
    result = run_agent(agent)
    assert not result.success and result.failure_category == FAILURE_TOKEN_BUDGET
    assert result.rounds == agent._chat.calls == 0


def test_failed_finish_at_budget_limit_does_not_retry_or_claim_success():
    agent = make_agent([
        "FINISH: allegedly fixed",
    ], token_budget=15, max_rounds=5)
    result = run_agent(agent)
    assert not result.success and result.failure_category == FAILURE_TOKEN_BUDGET
    assert result.rounds == 1 and result.test_ok is None
    assert "no non-empty patch" in result.summary


def test_rounds_exhaustion_marks_failure_and_saves_unverified_diff():
    agent = make_agent(["```bash\nfix-bug\n```", "VIEW src/auth.py"])
    result = run_agent(agent)
    assert not result.success and result.test_ok is None
    assert result.failure_category == FAILURE_ROUNDS_EXHAUSTED
    assert result.rounds == 2 and result.diff == PATCH
    assert result.summary == "Failed: round limit exhausted."
    assert [step.tool for step in result.steps] == ["run_bash", "view_file", "collect_diff"]


def test_no_tool_call_gets_reminder_then_real_verification():
    agent = make_agent([
        "I will look around first.",
        f"```bash\nfix-bug\n```\nTEST {TEST_COMMAND}\nFINISH: ok after reminder",
    ])
    result = run_agent(agent)
    assert result.success and result.rounds == 2
    assert result.steps[0].tool == "no_action"
    assert "No tool call detected" in agent._chat.messages[1][-1]["content"]
    assert "TEST <shell command>" in agent._chat.messages[1][-1]["content"]


def test_patch_check_failure_is_recorded_once_and_allows_repair():
    sandbox = MemorySandbox(responses={
        "git apply --check --whitespace=nowarn -": [Reply(exit_code=1, stderr="bad hunk")],
    })
    agent = make_agent([
        f"```diff\n{PATCH}```",
        f"```bash\nfix-bug\n```\nTEST {TEST_COMMAND}\nFINISH: repaired",
    ], sandbox=sandbox)
    result = run_agent(agent)
    assert result.success
    assert sandbox.commands.count("git apply --check --whitespace=nowarn -") == 1
    assert "git apply --whitespace=nowarn -" not in sandbox.commands
    patches = [step for step in result.steps if step.tool == "apply_patch"]
    assert len(patches) == 1 and "bad hunk" in patches[0].output
    assert "bad hunk" in agent._chat.messages[1][-1]["content"]


def test_test_timeout_is_failure_with_real_feedback():
    sandbox = MemorySandbox(patch=PATCH, responses={
        TEST_COMMAND: [Reply(exit_code=124, stderr="command timed out", timed_out=True)],
    })
    result = run_agent(make_agent([
        f"TEST {TEST_COMMAND}\nFINISH: fixed",
    ], sandbox=sandbox))
    assert not result.success and result.test_ok is False
    assert result.failure_category == FAILURE_TEST_ENVIRONMENT
    assert "command timed out" in result.summary
    assert (TEST_COMMAND, None, 180) in sandbox.calls


def test_system_prompt_describes_final_verification_and_staging_contract():
    prompt = make_agent([]).system_prompt()
    assert "TEST <shell command>" in prompt
    assert "does NOT run it immediately" in prompt
    assert "cannot be overridden" in prompt
    assert "git add" in prompt and "git diff --binary HEAD" in prompt
    assert "Never commit" in prompt
    assert "180s timeout" in prompt
