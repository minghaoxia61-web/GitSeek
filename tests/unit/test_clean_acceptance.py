import asyncio
import copy
import hashlib
import shlex
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from packages.agent_core.acceptance import AcceptanceError, CleanAcceptance, acceptance_passed
from packages.agent_core.execution import AcceptanceSpec, ExecutionSpec, local_runtime_identity
from packages.agent_core.ingestion import clone_repository
from packages.sandbox.base import ExecResult
from tests.unit.test_execution_identity import create_history, git

GOOD_PATCH = (
    "--- a/src/auth.py\n+++ b/src/auth.py\n"
    "@@ -1,2 +1,2 @@\n def login_user(token):\n-    return token\n+    return bool(token)\n"
)


def acceptance_protocol():
    files = {
        "_gitseek_acceptance/test_hidden.py": (
            "# EVALUATOR_ONLY: must never be provided to the repair model\n"
            "import unittest\nfrom src.auth import login_user\n"
            "class HiddenTest(unittest.TestCase):\n"
            "    def test_boolean(self):\n"
            "        self.assertIs(type(login_user('yes')), bool)\n"
        ),
        "_gitseek_acceptance/test_regression.py": (
            "import unittest\nfrom src.auth import login_user\n"
            "class RegressionTest(unittest.TestCase):\n"
            "    def test_empty_token(self):\n"
            "        self.assertFalse(login_user(''))\n"
        ),
    }
    python = shlex.quote(Path(sys.executable).as_posix())
    return {
        "files": [
            {
                "path": path,
                "content": content,
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
            for path, content in files.items()
        ],
        "target_command": f"{python} -m unittest _gitseek_acceptance.test_hidden -v",
        "regression_command": f"{python} -m unittest _gitseek_acceptance.test_regression -v",
        "failure_marker": "FAIL: test_boolean",
        "success_marker": "OK",
        "regression_success_marker": "OK",
        "timeout_s": 30,
    }


@pytest.fixture()
def clean_case(tmp_path):
    source = tmp_path / "source"
    base, _, lock_sha = create_history(source)
    workspace = tmp_path / "agent"
    clone_repository(source.as_uri(), workspace, base_commit=base)
    spec = ExecutionSpec.model_validate(
        {
            "dataset_version": "test-v1",
            "base_commit": base,
            "dependency_lock": {"path": "requirements.lock", "sha256": lock_sha},
            "environment": {
                "backend": "local",
                "runtime_sha256": local_runtime_identity()["runtime_sha256"],
            },
            "acceptance": acceptance_protocol(),
        }
    )
    return workspace, spec


def test_clean_acceptance_reproduces_then_applies_and_verifies(clean_case):
    workspace, spec = clean_case
    check = CleanAcceptance(workspace, spec)
    try:
        asyncio.run(check.prepare())
    except AcceptanceError as exc:
        raise AssertionError(check.receipt) from exc
    assert check.receipt["baseline_target"]["exit_code"] == 1
    assert not (workspace / "_gitseek_acceptance").exists()
    # No matching working-tree state is copied from the repair workspace.
    asyncio.run(check.verify(GOOD_PATCH))
    assert acceptance_passed(check.receipt)
    assert check.receipt["isolated"] is False
    assert "bool(token)" not in (workspace / "src/auth.py").read_text()
    assert "bool(token)" in (check.final / "src/auth.py").read_text()
    check.cleanup()
    assert not check.root.exists()
    assert workspace.exists()


def test_regression_failure_rejects_superficial_fix(clean_case):
    workspace, spec = clean_case
    check = CleanAcceptance(workspace, spec)
    asyncio.run(check.prepare())
    bad_patch = GOOD_PATCH.replace("return bool(token)", "return True")
    with pytest.raises(AcceptanceError, match="acceptance tests failed"):
        asyncio.run(check.verify(bad_patch))
    assert check.receipt["final_target"]["exit_code"] == 0
    assert check.receipt["final_regression"]["exit_code"] == 1
    assert not acceptance_passed(check.receipt)


@pytest.mark.parametrize("kind", ["already_passes", "broken_test", "timeout"])
def test_baseline_must_reproduce_specific_failure(clean_case, kind):
    workspace, spec = clean_case
    protocol = spec.acceptance.model_dump()
    if kind != "timeout":
        content = protocol["files"][0]["content"]
        content = (
            content.replace(
                "self.assertIs(type(login_user('yes')), bool)", "self.assertTrue(login_user('yes'))"
            )
            if kind == "already_passes"
            else "this is invalid python !!\n"
        )
        protocol["files"][0]["content"] = content
        protocol["files"][0]["sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        spec = spec.model_copy(update={"acceptance": AcceptanceSpec.model_validate(protocol)})
    if kind == "timeout":

        class TimeoutSandbox:
            async def exec(self, command, **kwargs):
                return ExecResult(command, 1, "FAIL: test_boolean", "", 1, timed_out=True)

        check = CleanAcceptance(
            workspace, spec, sandbox_factory=lambda *args, **kwargs: TimeoutSandbox()
        )
    else:
        check = CleanAcceptance(workspace, spec)
    with pytest.raises(AcceptanceError) as error:
        asyncio.run(check.prepare())
    assert error.value.category == "baseline_not_reproduced"
    assert not check.receipt["baseline_reproduced"]


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_auth.py",
        "Tests/auth_checks.py",
        "src/tests/test_auth.py",
        "pytest.ini",
        "_gitseek_acceptance/fake.py",
        "requirements.lock",
    ],
)
def test_patch_cannot_add_or_change_protected_files(clean_case, path):
    workspace, spec = clean_case
    check = CleanAcceptance(workspace, spec)
    asyncio.run(check.prepare())
    # A diff can come from an external producer; inspect applied paths as well as agent paths.
    if path == "requirements.lock":
        diff = (
            "--- a/requirements.lock\n+++ b/requirements.lock\n@@ -1 +1 @@\n-pytest==8.4.2\n+bad\n"
        )
    else:
        diff = f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n+assert True\n"
    with pytest.raises(AcceptanceError) as error:
        asyncio.run(check.verify(diff))
    assert error.value.category == "protected_test_modified"
    assert not check.receipt["passed"]


def test_staged_test_edits_in_agent_workspace_are_rejected(clean_case):
    workspace, spec = clean_case
    check = CleanAcceptance(workspace, spec)
    asyncio.run(check.prepare())
    (workspace / "tests").mkdir()
    (workspace / "tests/test_fake.py").write_text("assert True\n")
    git(workspace, "add", "tests/test_fake.py")
    with pytest.raises(AcceptanceError) as error:
        asyncio.run(check.verify(GOOD_PATCH))
    assert error.value.category == "protected_test_modified"


def test_cleanup_never_removes_preexisting_acceptance_directory(clean_case):
    workspace, spec = clean_case
    check = CleanAcceptance(workspace, spec)
    check.root.mkdir()
    marker = check.root / "keep.txt"
    marker.write_text("historical evidence")
    with pytest.raises(AcceptanceError):
        asyncio.run(check.prepare())
    check.cleanup()
    assert marker.read_text() == "historical evidence"


def test_bundle_hash_and_reserved_path_are_validated():
    protocol = acceptance_protocol()
    for key, value in [("sha256", "0" * 64), ("path", "../test.py")]:
        invalid = copy.deepcopy(protocol)
        invalid["files"][0][key] = value
        with pytest.raises(ValidationError):
            AcceptanceSpec.model_validate(invalid)


def test_standalone_passed_flag_is_not_accepted():
    assert not acceptance_passed({"version": "clean-acceptance-v1", "passed": True})
