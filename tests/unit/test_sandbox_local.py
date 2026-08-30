import pytest

from packages.sandbox import LocalSandbox, SandboxError, create_sandbox, docker_command
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
