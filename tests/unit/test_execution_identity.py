import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from packages.agent_core.execution import (
    DependencyLock,
    ExecutionEnvironment,
    ExecutionIdentityError,
    ExecutionSpec,
    verify_dependency_lock,
    verify_environment,
)
from packages.agent_core.ingestion import IngestionError, clone_repository, verify_checkout
from packages.sandbox.docker import docker_command


def git(workspace, *args):
    return subprocess.run(["git", "-C", str(workspace), *args], check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()


def create_history(source: Path):
    source.mkdir()
    git(source, "init")
    git(source, "config", "core.autocrlf", "false")
    (source / "src").mkdir()
    (source / "src/auth.py").write_bytes(b"def login_user(token):\n    return token\n")
    lock = b"pytest==8.4.2\n"
    (source / "requirements.lock").write_bytes(lock)
    git(source, "add", ".")
    git(source, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-m", "buggy base")
    base = git(source, "rev-parse", "HEAD")
    (source / "src/auth.py").write_bytes(b"def login_user(token):\n    return bool(token)\n")
    git(source, "add", ".")
    git(source, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-m", "later fix")
    return base, git(source, "rev-parse", "HEAD"), hashlib.sha256(lock).hexdigest()


def test_shallow_clone_fetches_exact_historical_commit(tmp_path):
    source = tmp_path / "source"
    base, latest, lock_sha = create_history(source)
    workspace = tmp_path / "checkout"
    clone_repository(source.as_uri(), workspace, base_commit=base)
    assert verify_checkout(workspace, base) == base
    assert base != latest
    assert "bool(token)" not in (workspace / "src/auth.py").read_text()
    assert verify_dependency_lock(workspace, DependencyLock(
        path="requirements.lock", sha256=lock_sha,
    ))["sha256"] == lock_sha


def test_missing_commit_does_not_fall_back_to_default_branch(tmp_path):
    source = tmp_path / "source"
    create_history(source)
    workspace = tmp_path / "checkout"
    with pytest.raises(IngestionError, match="git clone failed"):
        clone_repository(source.as_uri(), workspace, base_commit="f" * 40)
    assert not (workspace / "src/auth.py").exists()


def test_checkout_rejects_wrong_head_and_dirty_bytes(tmp_path):
    source = tmp_path / "source"
    base, latest, _ = create_history(source)
    with pytest.raises(ExecutionIdentityError, match="HEAD"):
        verify_checkout(source, base)
    (source / "untracked.txt").write_text("dirty")
    with pytest.raises(ExecutionIdentityError, match="clean"):
        verify_checkout(source, latest)


@pytest.mark.parametrize("path", ["../lock", "/tmp/lock", "C:/lock", "a\\lock", ".git/config", ""])
def test_lock_path_must_be_repository_relative(path):
    with pytest.raises(ValidationError):
        DependencyLock(path=path, sha256="a" * 64)


def test_dependency_lock_hash_mismatch_fails(tmp_path):
    (tmp_path / "requirements.lock").write_bytes(b"modified\r\n")
    with pytest.raises(ExecutionIdentityError, match="bytes"):
        verify_dependency_lock(tmp_path, DependencyLock(path="requirements.lock", sha256="a" * 64))


@pytest.mark.parametrize("commit", ["main", "abc123", "HEAD", "A" * 40, "x" * 40])
def test_execution_spec_requires_full_commit_hash(commit):
    with pytest.raises(ValidationError):
        ExecutionSpec.model_validate({
            "dataset_version": "test-v1", "base_commit": commit,
            "environment": {"backend": "local", "runtime_sha256": "a" * 64},
            "dependency_lock": {"path": "requirements.lock", "sha256": "b" * 64},
        })


@pytest.mark.parametrize("image", ["python:3.12", "python:latest", "python@sha256:abc"])
def test_docker_environment_rejects_mutable_image(image):
    with pytest.raises(ValidationError):
        ExecutionEnvironment(backend="docker", image=image)


def test_docker_identity_checks_digest_and_disables_automatic_pull(monkeypatch, tmp_path):
    image = "python@sha256:" + "a" * 64
    calls = []

    def inspect_image(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, json.dumps([{
            "Id": "sha256:" + "b" * 64, "RepoDigests": [image],
            "Os": "linux", "Architecture": "amd64",
        }]))

    monkeypatch.setattr("packages.agent_core.execution.subprocess.run", inspect_image)
    actual = verify_environment(ExecutionEnvironment(
        backend="docker", image=image, platform="linux/amd64",
    ))
    assert actual["image"] == image
    assert calls == [["docker", "image", "inspect", image]]
    argv = docker_command("true", tmp_path, image=image, platform="linux/amd64")
    assert argv[argv.index("--pull") + 1] == "never"
    assert argv[argv.index("--platform") + 1] == "linux/amd64"


def test_docker_digest_mismatch_fails(monkeypatch):
    monkeypatch.setattr("packages.agent_core.execution.subprocess.run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args, 0, json.dumps([{
                            "Id": "sha256:" + "b" * 64, "RepoDigests": [],
                        }])))
    with pytest.raises(ExecutionIdentityError, match="digest"):
        verify_environment(ExecutionEnvironment(
            backend="docker", image="python@sha256:" + "a" * 64, platform="linux/amd64",
        ))


def test_docker_platform_mismatch_fails(monkeypatch):
    image = "python@sha256:" + "a" * 64
    monkeypatch.setattr("packages.agent_core.execution.subprocess.run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args, 0, json.dumps([{
                            "Id": "sha256:" + "b" * 64, "RepoDigests": [image],
                            "Os": "linux", "Architecture": "arm64",
                        }])))
    with pytest.raises(ExecutionIdentityError, match="platform"):
        verify_environment(ExecutionEnvironment(
            backend="docker", image=image, platform="linux/amd64",
        ))
