import asyncio
import hashlib
import json

import pytest

from packages.agent_core.evidence import EvidenceArchive
from packages.agent_core.fixer import FixerAgent, FixerConfig, FixerRunError
from packages.observability.calls import ReceiptPersistenceError
from packages.sandbox.base import ExecResult
from tests.unit.test_fixer_agent import StubChat, VerificationSandbox


def test_tool_error_keeps_partial_usage_steps_and_diff():
    class BrokenSandbox:
        async def exec(self, command, **kwargs):
            if command.startswith("git diff"):
                return ExecResult(command, 0, "--- a/x.py\n+++ b/x.py\n", "", 1)
            raise OSError("tool stopped")

    agent = FixerAgent(
        chat_client=StubChat(["```bash\necho work\n```"]),
        sandbox=BrokenSandbox(),
        issue_text="issue",
        locator_candidates=[],
        config=FixerConfig(model="stub", input_cost_per_million=1, output_cost_per_million=2),
    )
    with pytest.raises(FixerRunError) as error:
        asyncio.run(agent.run())
    partial = error.value.result
    assert partial.failure_category == "tool_error"
    assert partial.token_in == 10 and partial.token_out == 5
    assert partial.cost_usd == 0.00002
    assert partial.patch_present
    assert partial.steps[0].tool == "tool_error"


def test_tool_log_truncation_retains_original_hash_and_exit_code():
    class LongOutput(VerificationSandbox):
        async def exec(self, command, **kwargs):
            if command == "echo output":
                return ExecResult(command, 0, "x" * 6000, "", 5)
            return await super().exec(command, **kwargs)

    result = asyncio.run(
        FixerAgent(
            chat_client=StubChat(["```bash\necho output\n```\nFINISH: done"]),
            sandbox=LongOutput(),
            issue_text="issue",
            locator_candidates=[],
            config=FixerConfig(model="stub"),
        ).run()
    )
    step = result.steps[0]
    expected = "exit=0\n" + "x" * 6000
    assert step.input["exit_code"] == 0
    assert step.input["_evidence"]["output_truncated"] is True
    assert step.input["_evidence"]["output_sha256"] == hashlib.sha256(expected.encode()).hexdigest()
    assert step.input["_evidence"]["output_chars"] == len(expected)


def test_archive_preserves_utf8_patch_and_separates_attempts(tmp_path):
    first = EvidenceArchive(tmp_path, "same-run")
    second = EvidenceArchive(tmp_path, "same-run")
    assert first.root != second.root
    first.event("provider_call", {"kind": "chat", "status": "started"})
    diff = "--- a/文本.py\n+++ b/文本.py\n"
    patch = first.patch(diff)
    first.receipt({"stage": "failed", "patch": patch})
    assert (first.root / "patch.diff").read_bytes() == diff.encode("utf-8")
    event = json.loads((first.root / "events.jsonl").read_text(encoding="utf-8"))
    assert event["event"] == "provider_call" and event["kind"] == "chat"
    assert (
        json.loads((first.root / "receipt.json").read_text(encoding="utf-8"))["stage"] == "failed"
    )
    assert not (first.root / "receipt.tmp").exists()


def test_receipt_failure_is_not_misreported_as_tool_or_model_failure():
    class BrokenReceipt:
        async def complete(self, *args, **kwargs):
            raise ReceiptPersistenceError("storage unavailable")

    agent = FixerAgent(
        chat_client=BrokenReceipt(),
        sandbox=VerificationSandbox(),
        issue_text="issue",
        locator_candidates=[],
        config=FixerConfig(model="stub"),
    )
    with pytest.raises(FixerRunError) as error:
        asyncio.run(agent.run())
    assert error.value.result.failure_category == "evidence_error"
