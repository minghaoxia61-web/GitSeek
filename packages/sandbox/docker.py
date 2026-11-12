"""Docker sandbox: every command runs in a fresh, restricted, network-less container.

Safety defaults per the GitSeek-agent design: no network, capability drop, no new
privileges, memory/CPU limits, workspace bind-mount only. The workspace directory is a
host bind-mount, so host-side ``write_file``/``read_file`` stay consistent with commands.
"""

import asyncio
import hashlib
import subprocess
import time
from pathlib import Path

from packages.sandbox.base import BaseSandbox, ExecResult

DEFAULT_IMAGE = "python:3.12"  # full build: the fixer loop needs git apply/git diff in-container


def docker_command(
    command: str,
    workspace: Path,
    *,
    image: str = DEFAULT_IMAGE,
    workdir: str = "/workspace",
    memory: str = "2g",
    cpus: str = "2.0",
    network_off: bool = True,
    platform: str | None = None,
) -> list[str]:
    """Pure builder so the hardened argv is unit-testable without Docker installed."""
    argv = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        memory,
        "--cpus",
        cpus,
    ]
    if network_off:
        argv += ["--network", "none"]
    if "@sha256:" in image:
        argv += ["--pull", "never"]
    if platform:
        argv += ["--platform", platform]
    argv += [
        "-v",
        f"{Path(workspace).resolve()}:{workdir}",
        "-w",
        workdir,
        image,
        "bash",
        "-c",
        command,
    ]
    return argv


class DockerSandbox(BaseSandbox):
    def __init__(
        self,
        workspace: Path,
        *,
        image: str = DEFAULT_IMAGE,
        memory: str = "2g",
        cpus: str = "2.0",
        platform: str | None = None,
    ) -> None:
        super().__init__(workspace)
        self.image = image
        self.memory = memory
        self.cpus = cpus
        self.platform = platform

    async def exec(
        self,
        command: str,
        *,
        stdin: str | None = None,
        timeout_s: float = 120.0,
    ) -> ExecResult:
        argv = docker_command(
            command,
            self.workspace,
            image=self.image,
            memory=self.memory,
            cpus=self.cpus,
            platform=self.platform,
        )
        started = time.monotonic()
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                argv,
                input=stdin.encode("utf-8") if stdin is not None else None,
                capture_output=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            return self._timeout_result(
                command, int((time.monotonic() - started) * 1000), exc.output, exc.stderr
            )
        return ExecResult(
            command=command,
            exit_code=completed.returncode,
            stdout=(completed.stdout or b"").decode("utf-8", errors="replace"),
            stderr=(completed.stderr or b"").decode("utf-8", errors="replace"),
            duration_ms=int((time.monotonic() - started) * 1000),
            stdout_sha256=hashlib.sha256(completed.stdout or b"").hexdigest(),
            stderr_sha256=hashlib.sha256(completed.stderr or b"").hexdigest(),
        )
