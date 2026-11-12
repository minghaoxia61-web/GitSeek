import json
from pathlib import Path

import pytest

from packages.agent_core.bench import diff_files, load_manifest, topk_hit
from tests.unit.test_clean_acceptance import acceptance_protocol


def test_diff_files_parses_and_skips_dev_null():
    diff = (
        "diff --git a/keep.py b/keep.py\n"
        "--- a/keep.py\n+++ b/keep.py\n"
        "diff --git a/gone.py b/dev/null\n"
        "--- a/gone.py\n+++ /dev/null\n"
        "diff --git a/keep.py b/other.py\n"
        "+++ b/other.py\n"
    )
    assert diff_files(diff) == ["keep.py", "other.py"]


def test_diff_files_handles_empty():
    assert diff_files("") == []
    assert diff_files(None) == []  # type: ignore[arg-type]


def test_topk_hit_matches_within_k():
    predicted = ["a.py", "b.py", "c.py"]
    assert topk_hit(predicted, ["b.py"], 2)
    assert not topk_hit(predicted, ["b.py"], 1)
    assert topk_hit(predicted, ["c.py"], 3)
    assert not topk_hit(predicted, ["missing.py"], 3)


def test_load_manifest_reads_instances(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{
        "instance_id": "owner__repo-1", "repo": "owner/repo", "issue_number": 1,
        "gold_files": ["src/a.py"], "test_command": "pytest -q",
        "execution": {
            "dataset_version": "test-v1", "base_commit": "a" * 40,
            "environment": {"backend": "local", "runtime_sha256": "b" * 64},
            "dependency_lock": {"path": "requirements.lock", "sha256": "c" * 64},
            "acceptance": acceptance_protocol(),
        },
    }]), encoding="utf-8")
    instances = load_manifest(manifest)
    assert len(instances) == 1
    assert instances[0].repo_full_name == "owner/repo"
    assert instances[0].gold_files == ("src/a.py",)
    assert instances[0].test_command == "pytest -q"


def test_load_manifest_rejects_non_array(tmp_path: Path):
    manifest = tmp_path / "bad.json"
    manifest.write_text("{\"not\": \"a list\"}", encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(manifest)


@pytest.mark.parametrize("command", [None, "", "  ", 42])
def test_manifest_requires_explicit_verification_command(tmp_path, command):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{
        "instance_id": "repo-1", "repo": "owner/repo", "issue_number": 1,
        "test_command": command,
    }]), encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty test_command"):
        load_manifest(manifest)


def test_manifest_rejects_unpinned_execution_before_running(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{
        "instance_id": "repo-1", "repo": "owner/repo", "issue_number": 1,
        "test_command": "pytest -q",
    }]), encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(manifest)
