"""Sandbox primitives shared by local and Docker execution backends."""

from pathlib import Path

from packages.sandbox.base import BaseSandbox, ExecResult, SandboxError
from packages.sandbox.docker import DEFAULT_IMAGE, DockerSandbox, docker_command
from packages.sandbox.local import LocalSandbox

__all__ = [
    "DEFAULT_IMAGE",
    "BaseSandbox",
    "DockerSandbox",
    "ExecResult",
    "LocalSandbox",
    "SandboxError",
    "create_sandbox",
    "docker_command",
]


def create_sandbox(backend: str, workspace: Path, *, image: str = DEFAULT_IMAGE,
                   platform: str | None = None) -> BaseSandbox:
    """``docker`` runs each command in a restricted container; ``local`` is dev-only."""
    if backend == "docker":
        return DockerSandbox(workspace, image=image, platform=platform)
    return LocalSandbox(workspace)
