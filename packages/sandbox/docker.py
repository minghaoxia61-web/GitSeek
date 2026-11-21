"""Docker sandbox: every command runs in a fresh, restricted, network-less container.

Safety defaults per the GitSeek-agent design: no network, capability drop, no new
privileges, memory/CPU limits, workspace bind-mount only. The workspace directory is a
host bind-mount, so host-side ``write_file``/``read_file`` stay consistent with commands.
"""

import asyncio
import os
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
) -> list[str]:
    """Build hardened argv without launching Docker or changing host permissions."""
    workspace = Path(workspace).resolve()
    argv = [
        "docker", "run", "--rm", "-i",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--memory", memory,
        "--cpus", cpus,
    ]
    if network_off:
        argv += ["--network", "none"]
    if os.name == "posix":
        owner = workspace.stat()
        argv += ["--user", f"{owner.st_uid}:{owner.st_gid}"]
    argv += [
        "-v", f"{workspace}:{workdir}",
        "-w", workdir,
        image,
        "bash", "-c", command,
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
    ) -> None:
        super().__init__(workspace)
        self.image = image
        self.memory = memory
        self.cpus = cpus

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
        )
        started = time.monotonic()
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                argv,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return self._timeout_result(command, int((time.monotonic() - started) * 1000))
        return ExecResult(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
