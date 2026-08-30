"""Sandbox contract: a workspace directory plus an async exec primitive."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


class SandboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


class BaseSandbox(ABC):
    """Commands always run inside ``workspace``; files are accessed on the host volume.

    ``write_file`` / ``read_file`` use the host filesystem because every backend mounts the
    same workspace directory, so mutations are visible to container processes immediately.
    """

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    async def exec(
        self,
        command: str,
        *,
        stdin: str | None = None,
        timeout_s: float = 120.0,
    ) -> ExecResult:
        """Execute one shell command inside the sandbox."""

    def resolve_path(self, relative: str) -> Path:
        candidate = (self.workspace / relative).resolve()
        if not candidate.is_relative_to(self.workspace.resolve()):
            raise SandboxError(f"path escapes workspace: {relative}")
        return candidate

    def write_file(self, relative: str, content: str) -> None:
        target = self.resolve_path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def read_file(self, relative: str) -> str:
        target = self.resolve_path(relative)
        if not target.is_file():
            raise SandboxError(f"file not found in workspace: {relative}")
        return target.read_text(encoding="utf-8", errors="ignore")

    @staticmethod
    def _timeout_result(command: str, duration_ms: int) -> ExecResult:
        return ExecResult(
            command=command,
            exit_code=124,
            stdout="",
            stderr=f"command timed out after {duration_ms}ms",
            duration_ms=duration_ms,
            timed_out=True,
        )


__all__ = ["BaseSandbox", "ExecResult", "SandboxError"]
