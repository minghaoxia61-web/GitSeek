from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from packages.sandbox import LocalSandbox, SandboxError, create_sandbox, docker_command
from packages.sandbox import docker as docker_module
from packages.sandbox.docker import DockerSandbox


def test_local_sandbox_executes_and_captures(tmp_path):
    sandbox = LocalSandbox(tmp_path)
    result = sandbox.exec.__self__ and __import__("asyncio").run(sandbox.exec("echo hello"))
    assert result.exit_code == 0
    assert "hello" in result.stdout


def test_local_sandbox_reports_exit_codes(tmp_path):
    import asyncio

    sandbox = LocalSandbox(tmp_path)
    result = asyncio.run(sandbox.exec("exit 3"))
    assert result.exit_code == 3


def test_local_sandbox_stdin(tmp_path):
    import asyncio

    sandbox = LocalSandbox(tmp_path)
    result = asyncio.run(sandbox.exec("cat", stdin="patch-bytes"))
    assert "patch-bytes" in result.stdout


def test_workspace_file_helpers(tmp_path):
    sandbox = LocalSandbox(tmp_path)
    sandbox.write_file("pkg/mod.py", "print('hi')\n")
    assert sandbox.read_file("pkg/mod.py") == "print('hi')\n"
    with pytest.raises(SandboxError):
        sandbox.resolve_path("../outside.txt")


def test_create_sandbox_backend_choice(tmp_path):
    assert isinstance(create_sandbox("local", tmp_path), LocalSandbox)
    assert isinstance(create_sandbox("docker", tmp_path), DockerSandbox)


def test_docker_command_is_hardened(tmp_path):
    argv = docker_command("pytest -q", tmp_path)
    joined = " ".join(argv)
    assert argv[0] == "docker"
    assert "--network none" in joined
    assert "--cap-drop ALL" in joined
    assert "no-new-privileges" in joined
    assert "--memory 2g" in joined
    assert argv[-1] == "pytest -q"


@pytest.mark.parametrize(
    ("platform", "uid", "gid", "user_args"),
    [
        ("posix", 1234, 5678, ["--user", "1234:5678"]),
        ("posix", 0, 0, ["--user", "0:0"]),
        ("nt", 1234, 5678, []),
    ],
)
def test_docker_command_uses_workspace_owner_only_on_posix(
    monkeypatch, tmp_path, platform, uid, gid, user_args,
):
    # Replace only docker's module references: patching global os.name breaks pathlib on Windows.
    monkeypatch.setattr(docker_module, "os", SimpleNamespace(name=platform))
    workspace = MagicMock(spec=Path)
    workspace.resolve.return_value = workspace
    workspace.__str__.return_value = str(tmp_path.resolve())
    workspace.stat.return_value = SimpleNamespace(st_uid=uid, st_gid=gid)
    monkeypatch.setattr(docker_module, "Path", Mock(return_value=workspace))

    argv = docker_command("pytest -q", tmp_path)

    assert argv == [
        "docker", "run", "--rm", "-i",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--memory", "2g",
        "--cpus", "2.0",
        "--network", "none",
        *user_args,
        "-v", f"{tmp_path.resolve()}:/workspace",
        "-w", "/workspace",
        "python:3.12", "bash", "-c", "pytest -q",
    ]
    if platform == "posix":
        workspace.stat.assert_called_once_with()
    else:
        workspace.stat.assert_not_called()
