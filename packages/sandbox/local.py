"""Local subprocess sandbox for development only.

There is NO isolation guarantee: commands run directly on the host inside the workspace
directory. Production/evaluation workloads must use :class:`packages.sandbox.DockerSandbox`.
"""

import asyncio
import os
import shutil
import subprocess
import time

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


def _shell_argv(command: str) -> list[str]:
    if shutil.which("bash") is not None:
        return ["bash", "-c", command]
    return ["cmd", "/c", command]


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
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env=_sandbox_env(),
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
