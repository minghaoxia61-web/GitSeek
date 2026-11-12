"""Local subprocess sandbox for development only.

There is NO isolation guarantee: commands run directly on the host inside the workspace
directory. Production/evaluation workloads must use :class:`packages.sandbox.DockerSandbox`.
"""

import asyncio
import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path

from packages.sandbox.base import BaseSandbox, ExecResult

_SANDBOX_ENV_KEYS = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "COMSPEC", "TEMP", "TMP")


def _sandbox_env() -> dict[str, str]:
    env = {key: value for key in _SANDBOX_ENV_KEYS if (value := os.environ.get(key))}
    env.setdefault("LANG", "C.UTF-8")
    # Proxy variables are stripped so local runs do not silently route through a proxy.
    for proxy_key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        os.environ.pop(proxy_key, None)
        env.pop(proxy_key, None)
    return env


def local_shell_executable() -> str:
    if os.name == "nt":
        # System32/bash.exe launches WSL: its Python/paths are not the host runtime.
        git = shutil.which("git")
        if git:
            root = Path(git).resolve().parent.parent
            for candidate in (root / "bin/bash.exe", root / "usr/bin/bash.exe"):
                if candidate.is_file():
                    return str(candidate)
        return shutil.which("cmd") or "cmd"
    return shutil.which("bash") or "/bin/sh"


def _shell_argv(command: str) -> list[str]:
    shell = local_shell_executable()
    switch = "/c" if Path(shell).name.casefold() in {"cmd", "cmd.exe"} else "-c"
    return [shell, switch, command]


class LocalSandbox(BaseSandbox):
    async def exec(
        self,
        command: str,
        *,
        stdin: str | None = None,
        timeout_s: float = 120.0,
    ) -> ExecResult:
        argv = _shell_argv(command)
        started = time.monotonic()
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                argv,
                cwd=str(self.workspace),
                input=stdin.encode("utf-8") if stdin is not None else None,
                capture_output=True,
                timeout=timeout_s,
                env=_sandbox_env(),
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
