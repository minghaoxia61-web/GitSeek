import asyncio
import os
import shutil
import subprocess

import pytest

from packages.agent_core.fixer import FixerAgent, FixerConfig
from packages.agent_core.llm import ChatResult
from packages.sandbox import DockerSandbox


def test_fixer_repairs_trusted_fixture_in_isolated_docker(tmp_path):
    if shutil.which("docker") is None:
        pytest.skip("Docker is not installed")
    available = subprocess.run(
        ["docker", "info", "--format", "{{.OSType}}"], capture_output=True, timeout=15,
    )
    if available.returncode or available.stdout.strip() != b"linux":
        pytest.skip("Linux Docker daemon is not running")

    (tmp_path / "calculator.py").write_text(
        "def add(left, right):\n    return left - right\n", encoding="utf-8",
    )
    (tmp_path / "test_calculator.py").write_text(
        "import unittest\nfrom calculator import add\n\n"
        "class AdditionTests(unittest.TestCase):\n"
        "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n",
        encoding="utf-8",
    )
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    }
    for command in [
        ["git", "init", "--initial-branch=main"],
        ["git", "add", "calculator.py", "test_calculator.py"],
        ["git", "commit", "-m", "Create isolated repair fixture"],
    ]:
        subprocess.run(command, cwd=tmp_path, env=environment, check=True, capture_output=True)

    class FixtureChat:
        calls = 0

        async def complete(self, messages, **kwargs):
            self.calls += 1
            return ChatResult(
                content=(
                    "```diff\n"
                    "diff --git a/calculator.py b/calculator.py\n"
                    "--- a/calculator.py\n+++ b/calculator.py\n"
                    "@@ -1,2 +1,2 @@\n def add(left, right):\n"
                    "-    return left - right\n+    return left + right\n"
                    "```\nTEST python -m unittest -v\nFINISH: Repair addition"
                ),
                input_tokens=10, output_tokens=20, model="fixture",
            )

    async def exercise():
        sandbox = DockerSandbox(tmp_path)
        baseline = await sandbox.exec("python -m unittest -v", timeout_s=180)
        assert baseline.exit_code == 1 and "FAIL: test_add" in baseline.stderr
        chat = FixtureChat()
        result = await FixerAgent(
            chat_client=chat, sandbox=sandbox, issue_text="add(2, 3) must return 5",
            locator_candidates=[], config=FixerConfig(model="fixture", max_rounds=1),
        ).run()
        assert result.success, result.summary
        assert result.test_ok is True
        assert "+    return left + right" in result.diff
        assert chat.calls == 1
        assert sum(step.tool == "apply_patch" for step in result.steps) == 1
        assert sum(step.tool == "run_tests" for step in result.steps) == 1

    asyncio.run(exercise())
