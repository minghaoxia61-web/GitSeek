"""Benchmark harness for the fixer agent (M3 skeleton).

A manifest lists GitHub issues plus the gold patch's changed files; each instance becomes a
queued fixer run executed through :func:`workers.agent_runner.runner.process_run`, and the
harness scores locator Top-K file hits, patch presence, and end-to-end success. The official
SWE-bench Lite Docker evaluation is intentionally out of scope for this slice — see
``docs/agent/evaluation-protocol.md``.
"""

import argparse
import asyncio
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from packages.agent_core.acceptance import acceptance_passed
from packages.agent_core.execution import ExecutionSpec
from packages.agent_core.fixer import VERIFICATION_VERSION
from packages.database.session import create_db_engine, create_session_factory
from packages.domain.models.fixer import AgentBenchResultRecord, FixerPatchRecord, FixerRunRecord
from packages.domain.settings import get_settings
from workers.agent_runner.runner import claim_next_run, process_run

GOLD_FILE_RE = re.compile(r"^\+\+\+ b/(\S+)$", re.MULTILINE)
METRIC_LOCATOR_TOP_K = "locator_top{k}"
METRIC_PATCH_PRESENT = "patch_present"
METRIC_E2E_SUCCESS = "e2e_success"
METRIC_COST_USD = "cost_usd"
METRIC_ROUNDS = "rounds"


@dataclass(frozen=True)
class BenchInstance:
    instance_id: str
    repo_full_name: str
    issue_number: int
    gold_files: tuple[str, ...]
    test_command: str
    execution: ExecutionSpec


def load_manifest(path: Path) -> list[BenchInstance]:
    return _parse_manifest(Path(path).read_bytes())


def _parse_manifest(raw: bytes) -> list[BenchInstance]:
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("manifest must be a JSON array")
    instances: list[BenchInstance] = []
    for entry in payload:
        test_command = entry.get("test_command")
        if not isinstance(test_command, str) or not test_command.strip():
            raise ValueError(
                f"instance {entry.get('instance_id', '<unknown>')} "
                "requires a non-empty test_command"
            )
        execution = ExecutionSpec.model_validate(entry.get("execution"))
        if execution.acceptance is None:
            raise ValueError("benchmark execution requires evaluator-owned acceptance tests")
        instances.append(
            BenchInstance(
                instance_id=str(entry["instance_id"]),
                repo_full_name=str(entry["repo"]),
                issue_number=int(entry["issue_number"]),
                gold_files=tuple(entry.get("gold_files", [])),
                test_command=test_command,
                execution=execution,
            )
        )
    return instances


def diff_files(diff_text: str) -> list[str]:
    """Changed-file paths in a unified diff, in first-appearance order."""
    files: list[str] = []
    for match in GOLD_FILE_RE.finditer(diff_text or ""):
        path = match.group(1)
        if path != "/dev/null" and path not in files:
            files.append(path)
    return files


def topk_hit(predicted: list[str], gold: list[str], k: int) -> bool:
    gold_set = set(gold)
    return any(path in gold_set for path in predicted[:k])


async def run_benchmark(
    manifest_path: Path,
    *,
    backend: str | None = None,
    config_id: str = "fixer-v1",
    output_dir: str | Path = "eval-results",
    keep_workspace: bool = False,
    session_factory: sessionmaker | None = None,
) -> dict:
    manifest_bytes = Path(manifest_path).read_bytes()
    instances = _parse_manifest(manifest_bytes)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if backend and any(item.execution.environment.backend != backend for item in instances):
        raise ValueError("backend override does not match manifest execution environment")
    settings = get_settings()
    if session_factory is None:
        session_factory = create_session_factory(create_db_engine(settings.database_url))
    started_at = datetime.now(UTC)

    per_instance: list[dict] = []
    for instance in instances:
        run_id = str(uuid.uuid4())
        with session_factory() as session:
            session.add(
                FixerRunRecord(
                    id=run_id,
                    repo_full_name=instance.repo_full_name,
                    issue_number=instance.issue_number,
                    status="queued",
                    max_rounds=settings.fixer_max_rounds,
                    token_budget=settings.fixer_token_budget,
                    test_command=instance.test_command,
                    model=settings.fixer_model or settings.openai_model,
                    execution_spec={"spec": instance.execution.model_dump(),
                                    "manifest_sha256": manifest_sha256, "config_id": config_id},
                )
            )
            session.commit()
        claimed = claim_next_run(session_factory, run_id=run_id)
        if claimed != run_id:
            raise RuntimeError("bench run was not claimed; is another worker draining the queue?")
        await process_run(
            run_id,
            settings=settings,
            session_factory=session_factory,
            backend=backend,
            keep_workspace=keep_workspace,
        )

        with session_factory() as session:
            run = session.get(FixerRunRecord, run_id)
            locator_paths: list[str] = []
            for item in (run.result_json or {}).get("locator", []):
                if item.get("path") not in locator_paths:
                    locator_paths.append(item.get("path"))
            patch = session.execute(
                select_patch(run_id)
            ).scalar_one_or_none()
            predicted_patch_files = diff_files(patch.diff if patch else None)
            verification = (run.result_json or {}).get("verification", {})
            execution = (run.result_json or {}).get("execution", {})
            acceptance = (run.result_json or {}).get("acceptance") or {}
            billing = (run.result_json or {}).get("billing") or {}
            verified = (
                run.status == "succeeded" and run.success is True
                and verification.get("version") == VERIFICATION_VERSION
                and verification.get("scope") == "workspace_tests"
                and run.test_command == instance.test_command
                and execution.get("identity_verified") is True
                and execution.get("actual_commit") == instance.execution.base_commit
                and execution.get("final_commit") == instance.execution.base_commit
                and execution.get("index_source_commit") == instance.execution.base_commit
                and execution.get("requested") == run.execution_spec
                and run.execution_spec["manifest_sha256"] == manifest_sha256
                and verification.get("model_finished") is True
                and verification.get("patch_present") is True
                and verification.get("apply_ok") is True
                and verification.get("test_executed") is True
                and verification.get("test_ok") is True
                and verification.get("test_exit_code") == 0
                and verification.get("test_timed_out") is False
                and patch is not None and bool((patch.diff or "").strip())
                and patch.apply_ok is True and patch.test_ok is True
                and acceptance_passed(acceptance)
            )
            record = {
                "instance_id": instance.instance_id,
                "run_id": run_id,
                "status": run.status,
                "success": verified,
                "test_command": run.test_command,
                "verification": verification,
                "execution": execution,
                "acceptance": acceptance,
                "failure_category": run.failure_category,
                "rounds": run.rounds,
                "cost_usd": (billing.get("estimated_cost_usd")
                             if billing.get("version") == "provider-billing-v1" else None),
                "billing": billing,
                "gold_files": list(instance.gold_files),
                "locator_files": locator_paths,
                "patch_files": predicted_patch_files,
                "locator_top1": topk_hit(locator_paths, list(instance.gold_files), 1),
                "locator_top5": topk_hit(locator_paths, list(instance.gold_files), 5),
                "locator_top10": topk_hit(locator_paths, list(instance.gold_files), 10),
                "patch_present": patch is not None and bool((patch.diff or "").strip()),
                "error": run.error,
            }
        per_instance.append(record)
        _store_metrics(session_factory, config_id, instance, record)

    summary = _summarise(config_id, instances, per_instance, started_at)
    summary["manifest_sha256"] = manifest_sha256
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{config_id}-{started_at.strftime('%Y%m%d-%H%M%S')}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def select_patch(run_id: str):  # noqa: ANN201 - small SQLAlchemy statement helper
    return (
        select(FixerPatchRecord)
        .where(FixerPatchRecord.run_id == run_id)
        .order_by(FixerPatchRecord.created_at.desc(), FixerPatchRecord.id.desc())
        .limit(1)
    )


def _store_metrics(
    session_factory: sessionmaker,
    config_id: str,
    instance: BenchInstance,
    record: dict,
) -> None:
    rows = [
        ("locator_top1", 1.0 if record["locator_top1"] else 0.0, {}),
        ("locator_top5", 1.0 if record["locator_top5"] else 0.0, {}),
        ("locator_top10", 1.0 if record["locator_top10"] else 0.0, {}),
        (METRIC_PATCH_PRESENT, 1.0 if record["patch_present"] else 0.0, {}),
        (METRIC_E2E_SUCCESS, 1.0 if record["success"] else 0.0,
         {"category": record.get("failure_category"), "error": record.get("error")}),
        ("cost_known", float(record["cost_usd"] is not None), {}),
        (METRIC_ROUNDS, float(record["rounds"]), {}),
    ]
    if record["cost_usd"] is not None:
        rows.append((METRIC_COST_USD, record["cost_usd"], {"basis": "configured_rates_estimate"}))
    with session_factory() as session:
        for metric, value, details in rows:
            session.add(
                AgentBenchResultRecord(
                    config_id=config_id,
                    dataset="github-good-first-issues",
                    instance_id=instance.instance_id,
                    metric=metric,
                    value=value,
                    details_json=details,
                )
            )
        session.commit()


def _summarise(
    config_id: str,
    instances: list[BenchInstance],
    records: list[dict],
    started_at: datetime,
) -> dict:
    total = len(records) or 1
    costs = [record["cost_usd"] for record in records if record["cost_usd"] is not None]
    return {
        "config_id": config_id,
        "dataset": "github-good-first-issues",
        "instance_count": len(instances),
        "verification_scope": "clean_checkout_tests",
        "independent_acceptance": True,
        "local_development_instances": sum(
            item.execution.environment.backend == "local" for item in instances
        ),
        "started_at": started_at.isoformat(),
        "metrics": {
            "locator_top1": round(100.0 * sum(r["locator_top1"] for r in records) / total, 1),
            "locator_top5": round(100.0 * sum(r["locator_top5"] for r in records) / total, 1),
            "locator_top10": round(100.0 * sum(r["locator_top10"] for r in records) / total, 1),
            "patch_present": round(100.0 * sum(r["patch_present"] for r in records) / total, 1),
            "e2e_success": round(100.0 * sum(r["success"] for r in records) / total, 1),
            "avg_cost_usd": (round(sum(costs) / len(records), 6)
                             if records and len(costs) == len(records) else None),
            "cost_known_instances": len(costs),
            "cost_unknown_instances": len(records) - len(costs),
            "known_cost_subtotal_usd": sum(costs),
            "avg_rounds": round(sum(r["rounds"] for r in records) / total, 2),
        },
        "instances": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fixer-agent benchmark")
    parser.add_argument("--manifest", required=True, help="path to the dataset manifest JSON")
    parser.add_argument("--backend", choices=["local", "docker"], default=None)
    parser.add_argument("--config-id", default="fixer-v1")
    parser.add_argument("--output-dir", default="eval-results")
    parser.add_argument("--keep-workspaces", action="store_true")
    args = parser.parse_args()
    summary = asyncio.run(
        run_benchmark(
            Path(args.manifest),
            backend=args.backend,
            config_id=args.config_id,
            output_dir=args.output_dir,
            keep_workspace=args.keep_workspaces,
        )
    )
    print(json.dumps(summary["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
