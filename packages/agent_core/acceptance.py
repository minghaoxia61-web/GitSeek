"""Evaluator-owned fail-before/pass-after checks in separate fixed-revision checkouts."""

import hashlib
import shutil
import stat
import subprocess
from pathlib import Path, PurePosixPath

from packages.agent_core.execution import (
    ExecutionSpec,
    canonical_sha256,
    verify_dependency_lock,
    verify_environment,
)
from packages.agent_core.ingestion import clone_repository, verify_checkout
from packages.sandbox import create_sandbox
from packages.sandbox.base import transport_evidence

ACCEPTANCE_VERSION = "clean-acceptance-v1"


class AcceptanceError(RuntimeError):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


def _git(root: Path, *args: str, stdin: str | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        input=stdin.encode("utf-8") if stdin is not None else None,
        capture_output=True,
        timeout=60,
    )
    if result.returncode:
        raise AcceptanceError(
            "acceptance_patch_error", result.stderr.decode("utf-8", errors="replace")[-2000:]
        )
    return result.stdout


def acceptance_passed(receipt: dict) -> bool:
    """Require concrete evidence; a standalone passed=true flag is insufficient."""
    return (
        receipt.get("version") == ACCEPTANCE_VERSION
        and receipt.get("scope") == "clean_checkout_tests"
        and receipt.get("baseline_reproduced") is True
        and receipt.get("patch_applied") is True
        and receipt.get("protected_files_unchanged") is True
        and receipt.get("environment_verified") is True
        and receipt.get("passed") is True
        and all(
            receipt.get(name, {}).get("exit_code") == code
            and receipt.get(name, {}).get("timed_out") is False
            and receipt.get(name, {}).get("marker_found") is True
            for name, code in (
                ("baseline_target", 1),
                ("baseline_regression", 0),
                ("final_target", 0),
                ("final_regression", 0),
            )
        )
    )


class CleanAcceptance:
    def __init__(self, workspace: Path, spec: ExecutionSpec, *, sandbox_factory=create_sandbox):
        if spec.acceptance is None:
            raise ValueError("acceptance spec is required")
        self.workspace = workspace.resolve()
        self.spec = spec
        self.protocol = spec.acceptance
        self.root = self.workspace.parent / (self.workspace.name + ".acceptance")
        self.baseline = self.root / "baseline"
        self.final = self.root / "final"
        self.sandbox_factory = sandbox_factory
        self._owns_root = False
        self.receipt = {
            "version": ACCEPTANCE_VERSION,
            "scope": "clean_checkout_tests",
            "base_commit": spec.base_commit,
            "backend": spec.environment.backend,
            "isolated": spec.environment.backend == "docker",
            "passed": False,
            "baseline_reproduced": False,
            "patch_applied": False,
            "protected_files_unchanged": False,
            "environment_verified": False,
            "bundle_sha256": canonical_sha256(
                [{"path": item.path, "sha256": item.sha256} for item in self.protocol.files]
            ),
        }

    def _protected(self, path: str) -> bool:
        path = path.casefold()
        parts = PurePosixPath(path).parts
        name = parts[-1] if parts else ""
        return (
            any(part in {"tests", "test", "testing", "_gitseek_acceptance"} for part in parts)
            or name.startswith("test_")
            or name.endswith("_test.py")
            or name in {"conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml"}
            or path == self.spec.dependency_lock.path.casefold()
            or any(
                path == prefix.casefold() or path.startswith(prefix.rstrip("/").casefold() + "/")
                for prefix in self.protocol.protected_paths
            )
        )

    def _snapshot(self, root: Path) -> dict:
        tracked = _git(root, "ls-files", "-z").decode("utf-8").split("\0")
        paths = {path for path in tracked if path and self._protected(path)}
        paths.update(item.path for item in self.protocol.files)
        snapshot = {}
        for path in sorted(paths):
            target = root / path
            if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink():
                raise AcceptanceError("protected_test_modified", "protected path escapes checkout")
            snapshot[path] = (
                hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
            )
        return snapshot

    def _changed_paths(self, root: Path, *, agent_workspace: bool = False) -> list[str]:
        tracked = _git(root, "diff", "--name-only", "-z", "HEAD").decode("utf-8")
        untracked = _git(root, "ls-files", "--others", "-z").decode("utf-8")
        paths = {path for path in (tracked + untracked).split("\0") if path}
        if agent_workspace:
            # Normal local test runs generate bytecode; it is never copied to final checkout.
            paths = {
                path
                for path in paths
                if not ("__pycache__" in PurePosixPath(path).parts and path.endswith(".pyc"))
            }
        return sorted(paths)

    def _install_tests(self, root: Path) -> None:
        for item in self.protocol.files:
            target = root / item.path
            if (
                not target.resolve().is_relative_to(root.resolve())
                or target.exists()
                or target.is_symlink()
            ):
                raise AcceptanceError("acceptance_setup_error", "acceptance test path is not empty")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.content.encode("utf-8"))

    def _sandbox(self, root: Path):
        options = (
            {"image": self.spec.environment.image, "platform": self.spec.environment.platform}
            if self.spec.environment.backend == "docker"
            else {}
        )
        return self.sandbox_factory(self.spec.environment.backend, root, **options)

    async def _run(self, root: Path, key: str, command: str, marker: str) -> dict:
        result = await self._sandbox(root).exec(command, timeout_s=self.protocol.timeout_s)
        output = result.stdout + "\n" + result.stderr
        record = {
            "command": command,
            **transport_evidence(result),
            "duration_ms": result.duration_ms,
            "stdout": result.stdout[:8000],
            "stderr": result.stderr[:8000],
            "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
            "marker_found": marker in output,
        }
        self.receipt[key] = record
        return record

    @staticmethod
    def _matches(record: dict, code: int) -> bool:
        return record["exit_code"] == code and not record["timed_out"] and record["marker_found"]

    async def prepare(self) -> None:
        if self.root.exists():
            raise AcceptanceError("acceptance_setup_error", "acceptance workspace already exists")
        self.root.mkdir()
        self._owns_root = True
        for root in (self.baseline, self.final):
            clone_repository(self.workspace.as_uri(), root, base_commit=self.spec.base_commit)
            verify_checkout(root, self.spec.base_commit)
            verify_dependency_lock(root, self.spec.dependency_lock)
        self._install_tests(self.baseline)
        before = self._snapshot(self.baseline)
        target = await self._run(
            self.baseline,
            "baseline_target",
            self.protocol.target_command,
            self.protocol.failure_marker,
        )
        if not self._matches(target, 1):
            raise AcceptanceError(
                "baseline_not_reproduced",
                "baseline did not reproduce the declared assertion failure",
            )
        regression = await self._run(
            self.baseline,
            "baseline_regression",
            self.protocol.regression_command,
            self.protocol.regression_success_marker,
        )
        if not self._matches(regression, 0):
            raise AcceptanceError(
                "acceptance_environment_error", "baseline regression tests failed"
            )
        if self._snapshot(self.baseline) != before:
            raise AcceptanceError(
                "protected_test_modified", "baseline tests modified protected files"
            )
        self.receipt["baseline_reproduced"] = True

    async def verify(self, diff: str) -> None:
        self.receipt["patch_sha256"] = hashlib.sha256(diff.encode("utf-8")).hexdigest()
        if not diff.strip():
            raise AcceptanceError("acceptance_patch_error", "empty patch cannot pass acceptance")
        # Inspect actual Git paths, including staged edits; do not parse model diff headers.
        agent_paths = self._changed_paths(self.workspace, agent_workspace=True)
        if any(self._protected(path) for path in agent_paths):
            raise AcceptanceError(
                "protected_test_modified", "agent changed a protected test/config"
            )
        verify_checkout(self.final, self.spec.base_commit)
        _git(self.final, "apply", "--check", "--whitespace=nowarn", "-", stdin=diff)
        _git(self.final, "apply", "--whitespace=nowarn", "-", stdin=diff)
        self.receipt["patch_applied"] = True
        changed = self._changed_paths(self.final)
        self.receipt["changed_paths"] = changed
        if any(self._protected(path) for path in changed):
            raise AcceptanceError(
                "protected_test_modified", "patch changes a protected test/config"
            )
        verify_dependency_lock(self.final, self.spec.dependency_lock)
        verify_environment(self.spec.environment)
        self.receipt["environment_verified"] = True
        self._install_tests(self.final)
        before = self._snapshot(self.final)
        target = await self._run(
            self.final, "final_target", self.protocol.target_command, self.protocol.success_marker
        )
        regression = await self._run(
            self.final,
            "final_regression",
            self.protocol.regression_command,
            self.protocol.regression_success_marker,
        )
        self.receipt["protected_files_unchanged"] = self._snapshot(self.final) == before
        if not self.receipt["protected_files_unchanged"]:
            raise AcceptanceError(
                "protected_test_modified", "acceptance tests modified protected files"
            )
        if not self._matches(target, 0) or not self._matches(regression, 0):
            raise AcceptanceError(
                "acceptance_test_failed", "clean-checkout acceptance tests failed"
            )
        verify_checkout(self.final, self.spec.base_commit, require_clean=False)
        self.receipt["passed"] = True

    def cleanup(self) -> None:
        if not self._owns_root:
            return
        if (
            self.root.resolve().parent != self.workspace.parent
            or self.root.name != self.workspace.name + ".acceptance"
            or self.root.is_symlink()
        ):
            raise AcceptanceError("acceptance_setup_error", "unsafe acceptance cleanup target")
        if self.root.exists():
            root = self.root.resolve()

            def remove_readonly(function, path, exc):
                target = Path(path)
                if (
                    not target.resolve().is_relative_to(root)
                    or target.is_symlink()
                    or not isinstance(exc, PermissionError)
                ):
                    raise exc
                target.chmod(stat.S_IREAD | stat.S_IWRITE)
                function(path)

            shutil.rmtree(root, onexc=remove_readonly)
