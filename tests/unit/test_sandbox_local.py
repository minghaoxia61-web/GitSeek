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


def test_sandbox_stdin_preserves_utf8_and_lf_bytes(tmp_path):
    import asyncio

    sandbox = LocalSandbox(tmp_path)
    payload = "上下文\n+new\n \n"
    result = asyncio.run(sandbox.exec("cat > payload.diff", stdin=payload))
    assert result.exit_code == 0
    assert (tmp_path / "payload.diff").read_bytes() == payload.encode("utf-8")


def test_workspace_file_helpers(tmp_path):
    sandbox = LocalSandbox(tmp_path)
    sandbox.write_file("pkg/mod.py", "print('hi')\n")
    assert (tmp_path / "pkg/mod.py").read_bytes() == b"print('hi')\n"
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


@pytest.mark.parametrize("backend", ["local", "docker"])
def test_timeout_preserves_captured_partial_bytes(tmp_path, monkeypatch, backend):
    import asyncio
    import hashlib
    import subprocess

    from packages.sandbox.base import transport_evidence

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("command", 1, output=b"partial\r\n", stderr=b"warning\r\n")

    monkeypatch.setattr(subprocess, "run", timeout)
    result = asyncio.run(create_sandbox(backend, tmp_path).exec("command", timeout_s=1))
    assert result.stdout == "partial\r\n"
    assert result.stderr == "warning\r\n"
    assert result.timed_out and result.exit_code == 124
    metadata = transport_evidence(result)
    assert metadata["stdout_sha256"] == hashlib.sha256(b"partial\r\n").hexdigest()
    assert metadata["output_complete"] is False
    assert metadata["exit_code_kind"] == "timeout_sentinel"


@pytest.mark.parametrize("backend", ["local", "docker"])
def test_output_hash_uses_raw_bytes_before_utf8_replacement(tmp_path, monkeypatch, backend):
    import asyncio
    import hashlib
    import subprocess

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, b"\xff\r\n", b"error\r\n"),
    )
    result = asyncio.run(create_sandbox(backend, tmp_path).exec("command"))
    assert result.stdout == "\ufffd\r\n"
    assert result.stdout_sha256 == hashlib.sha256(b"\xff\r\n").hexdigest()
