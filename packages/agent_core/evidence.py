"""Attempt-scoped local receipts survive workspace cleanup and database write failures."""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4


def source_identity() -> dict:
    root = Path(__file__).resolve().parents[2]
    files = {}
    for directory in (
        "packages/agent_core",
        "packages/sandbox",
        "packages/observability",
        "workers/agent_runner",
    ):
        for path in sorted((root / directory).glob("*.py")):
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for relative in ("packages/domain/settings.py", "packages/domain/models/fixer.py"):
        files[relative] = hashlib.sha256((root / relative).read_bytes()).hexdigest()
    try:
        commit = (
            subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True,
                timeout=10,
                check=True,
            )
            .stdout.decode()
            .strip()
        )
    except (OSError, subprocess.SubprocessError):
        commit = None
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {"git_commit": commit, "source_sha256": digest, "files": files}


class EvidenceArchive:
    def __init__(self, root: Path, run_id: str):
        self.root = (
            root.resolve() / hashlib.sha256(run_id.encode("utf-8")).hexdigest() / uuid4().hex
        )
        self.root.mkdir(parents=True, exist_ok=False)

    def event(self, kind: str, payload: dict) -> None:
        with (self.root / "events.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps({"event": kind, **payload}, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def receipt(self, payload: dict) -> None:
        target = self.root / "receipt.json"
        temporary = target.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)

    def patch(self, diff: str, *, name: str = "patch.diff") -> dict:
        raw = diff.encode("utf-8")
        if name not in {"patch.diff", "working.diff"}:
            raise ValueError("unknown evidence patch artifact")
        (self.root / name).write_bytes(raw)
        return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
