"""Validated benchmark inputs and observed execution identity (no model calls)."""

import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.sandbox.local import local_shell_executable

COMMIT_RE = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
PINNED_IMAGE_RE = re.compile(r"[^\s@]+@sha256:[0-9a-f]{64}\Z")


class ExecutionIdentityError(RuntimeError):
    pass


class DependencyLock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def relative_path(self) -> "DependencyLock":
        path = PurePosixPath(self.path)
        if (not self.path or "\\" in self.path or ":" in self.path
                or path.is_absolute() or ".." in path.parts
                or not path.parts or path.parts[0] == ".git"):
            raise ValueError("dependency lock path must stay inside the repository")
        return self


class ExecutionEnvironment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    backend: Literal["docker", "local"]
    image: str | None = None
    runtime_sha256: str | None = None
    platform: Literal["linux/amd64", "linux/arm64"] | None = None

    @model_validator(mode="after")
    def pinned_identity(self) -> "ExecutionEnvironment":
        if self.backend == "docker":
            if not self.image or not PINNED_IMAGE_RE.fullmatch(self.image):
                raise ValueError("docker environment requires an image pinned by @sha256 digest")
            if self.runtime_sha256 is not None:
                raise ValueError("docker environment cannot declare a local runtime fingerprint")
            if self.platform is None:
                raise ValueError("docker environment requires a fixed linux platform")
        elif (not self.runtime_sha256 or not SHA256_RE.fullmatch(self.runtime_sha256)
              or self.image is not None or self.platform is not None):
            raise ValueError("local environment requires runtime_sha256 and no docker image")
        return self


class AcceptanceFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str
    content: str = Field(min_length=1, max_length=200_000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def trusted_test_bytes(self) -> "AcceptanceFile":
        DependencyLock(path=self.path, sha256=self.sha256)
        if not self.path.startswith("_gitseek_acceptance/"):
            raise ValueError("acceptance files must use the reserved _gitseek_acceptance directory")
        if hashlib.sha256(self.content.encode("utf-8")).hexdigest() != self.sha256:
            raise ValueError("acceptance file content does not match sha256")
        return self


class AcceptanceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    files: tuple[AcceptanceFile, ...] = Field(min_length=1, max_length=100)
    target_command: str = Field(min_length=1, max_length=4000)
    regression_command: str = Field(min_length=1, max_length=4000)
    failure_marker: str = Field(min_length=1, max_length=500)
    success_marker: str = Field(min_length=1, max_length=500)
    regression_success_marker: str = Field(min_length=1, max_length=500)
    protected_paths: tuple[str, ...] = ()
    timeout_s: int = Field(default=600, ge=1, le=1800)

    @model_validator(mode="after")
    def complete_protocol(self) -> "AcceptanceSpec":
        for value in (self.target_command, self.regression_command, self.failure_marker,
                      self.success_marker, self.regression_success_marker):
            if not value.strip():
                raise ValueError("acceptance commands and markers cannot be blank")
        if len({item.path.casefold() for item in self.files}) != len(self.files):
            raise ValueError("acceptance file paths must be unique")
        if sum(len(item.content.encode("utf-8")) for item in self.files) > 2_000_000:
            raise ValueError("acceptance test bundle exceeds 2 MB")
        for path in self.protected_paths:
            DependencyLock(path=path, sha256="0" * 64)
        return self


class ExecutionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    dataset_version: str = Field(min_length=1, max_length=120)
    base_commit: str
    environment: ExecutionEnvironment
    dependency_lock: DependencyLock
    # Optional for existing queued/product tasks; mandatory for new benchmark manifests.
    acceptance: AcceptanceSpec | None = None

    @model_validator(mode="after")
    def fixed_commit(self) -> "ExecutionSpec":
        if not COMMIT_RE.fullmatch(self.base_commit):
            raise ValueError("base_commit must be a full lowercase 40- or 64-character commit hash")
        if not self.dataset_version.strip():
            raise ValueError("dataset_version cannot be blank")
        return self


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def local_runtime_identity() -> dict:
    """Diagnostic local identity, not an isolation or complete OS reproducibility guarantee."""
    shell = local_shell_executable()
    identity = {
        "python": sys.version,
        "python_binary_sha256": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "shell_sha256": hashlib.sha256(Path(shell).read_bytes()).hexdigest() if shell else None,
        "git_version": subprocess.run(
            ["git", "--version"], check=True, capture_output=True, text=True, timeout=30,
        ).stdout.strip(),
        "packages": sorted(
            (dist.metadata.get("Name", ""), dist.version)
            for dist in importlib.metadata.distributions()
        ),
    }
    return {"backend": "local", "runtime_sha256": canonical_sha256(identity),
            "runtime": identity, "isolated": False}


def verify_environment(environment: ExecutionEnvironment) -> dict:
    if environment.backend == "local":
        actual = local_runtime_identity()
        if actual["runtime_sha256"] != environment.runtime_sha256:
            raise ExecutionIdentityError("local runtime fingerprint does not match execution spec")
        return actual
    try:
        completed = subprocess.run(
            ["docker", "image", "inspect", environment.image],
            check=True, capture_output=True, text=True, timeout=30,
        )
        image = json.loads(completed.stdout)[0]
        digest = environment.image.rsplit("@", 1)[1]
        if not any(ref.endswith("@" + digest) for ref in image.get("RepoDigests", [])):
            raise ExecutionIdentityError(
                "installed Docker image digest does not match execution spec"
            )
        if f"{image.get('Os')}/{image.get('Architecture')}" != environment.platform:
            raise ExecutionIdentityError(
                "installed Docker image platform does not match execution spec"
            )
        return {"backend": "docker", "image": environment.image,
                "image_id": image["Id"], "os": image.get("Os"),
                "architecture": image.get("Architecture"), "isolated": True}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError) as exc:
        raise ExecutionIdentityError(
            "cannot verify pinned Docker image locally; no image pulled"
        ) from exc


def verify_dependency_lock(workspace: Path, lock: DependencyLock) -> dict:
    root = workspace.resolve()
    target = (root / lock.path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ExecutionIdentityError("dependency lock file is missing or escapes workspace")
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != lock.sha256:
        raise ExecutionIdentityError("dependency lock bytes do not match execution spec")
    return {"path": lock.path, "sha256": actual}
