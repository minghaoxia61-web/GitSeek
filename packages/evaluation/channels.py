from __future__ import annotations

import asyncio
import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.ranking import reciprocal_rank_fusion
from packages.retrieval import parse_search_constraints

from .annotations import assign_intent_splits, grades_for_query, load_retrieval_dataset

SNAPSHOT_SCHEMA_VERSION = "retrieval-channel-snapshot-v1"


def build_snapshot_from_responses(
    responses: list[dict[str, Any]],
    dataset: dict[str, Any],
    *,
    snapshot_id: str,
) -> dict[str, Any]:
    """Convert saved SearchResponse payloads into a reproducible channel snapshot."""

    query_ids = {
        query: f"{intent['id']}-{number:02d}"
        for intent in dataset["intents"]
        for number, query in enumerate(intent["queries"], start=1)
    }
    queries: list[dict[str, Any]] = []
    ranking_versions: set[str] = set()
    rank_constants: set[int] = set()
    for response in responses:
        query = response.get("query")
        if query not in query_ids:
            raise ValueError(f"response query is not part of the dataset: {query}")
        retrieval = response.get("retrieval", {})
        channels = retrieval.get("channel_top_results", {})
        if not channels:
            raise ValueError(f"response has no channel rankings: {query_ids[query]}")
        ranking_versions.add(response["ranking_version"])
        rank_constant = retrieval.get("fusion_rank_constant")
        if rank_constant is not None:
            rank_constants.add(int(rank_constant))
        queries.append(
            {
                "query_id": query_ids[query],
                "query": query,
                "channels": channels,
                "final_ranking": [item["full_name"] for item in response.get("results", [])],
                "final_results": [
                        {
                            "full_name": item["full_name"],
                            "score": item.get("score"),
                            "score_breakdown": item.get("score_breakdown", {}),
                    }
                    for item in response.get("results", [])
                ],
            }
        )
    if len(ranking_versions) != 1:
        raise ValueError("all responses in one snapshot must use the same ranking version")
    if len(rank_constants) > 1:
        raise ValueError("all responses in one snapshot must use the same RRF constant")
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "dataset_version": dataset["version"],
        "captured_at": datetime.now(UTC).isoformat(),
        "ranking_version": next(iter(ranking_versions)),
        "rrf_rank_constant": next(iter(rank_constants), 60),
        "query_count": len(queries),
        "queries": queries,
    }


async def capture_live_snapshot(
    dataset: dict[str, Any],
    *,
    snapshot_id: str,
    split: str = "test",
    live_query_limit: int = 1,
    github_timeout_seconds: float = 3.0,
    include_github: bool = True,
) -> dict[str, Any]:
    """Run fixed queries through the real local and GitHub recall implementation."""

    from datetime import date

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from packages.domain.models import Base, Repository
    from packages.domain.search import SearchRequest
    from packages.domain.settings import get_settings
    from packages.github_client import GitHubAPIError, GitHubClient
    from packages.retrieval import RepositoryIndex
    from packages.search import SearchService

    if split not in {"train", "dev", "test", "all"}:
        raise ValueError("split must be train, dev, test, or all")
    reference_date = date.fromisoformat(dataset["reference_date"])
    reference_time = datetime.combine(reference_date, datetime.min.time(), tzinfo=UTC)
    split_by_intent = assign_intent_splits(intent["id"] for intent in dataset["intents"])
    selected_queries = [
        query
        for intent in dataset["intents"]
        if split == "all" or split_by_intent[intent["id"]] == split
        for query in intent["queries"]
    ]

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = get_settings()
    responses: list[dict[str, Any]] = []
    try:
        with Session(engine) as session:
            for repository_id, item in enumerate(dataset["repositories"], start=1):
                owner, name = item["full_name"].split("/", 1)
                session.add(
                    Repository(
                        github_id=repository_id,
                        full_name=item["full_name"],
                        owner=owner,
                        name=name,
                        description=item["description"],
                        html_url=f"https://github.com/{item['full_name']}",
                        default_branch="main",
                        primary_language=item["language"],
                        topics=item["topics"],
                        license_spdx=item["license"],
                        stars=item["stars"],
                        forks=0,
                        open_issues=item["open_issues"],
                        archived=False,
                        pushed_at=reference_time,
                        github_created_at=reference_time,
                        github_updated_at=reference_time,
                        fetched_at=reference_time,
                        source_etag=None,
                        raw_metadata=item,
                    )
                )
            session.commit()

            async def run_queries(client: Any) -> None:
                service = SearchService(client, repository_index=RepositoryIndex(session))
                for query in selected_queries:
                    response = await service.search(
                        SearchRequest(
                            query=query,
                            limit=10,
                            live_query_limit=live_query_limit,
                        ),
                        today=reference_date,
                    )
                    responses.append(response.model_dump(mode="json"))

            if include_github:
                async with GitHubClient(
                    token=settings.github_token,
                    base_url=settings.github_api_url,
                    api_version=settings.github_api_version,
                    timeout=github_timeout_seconds,
                ) as client:
                    await run_queries(client)
            else:
                class OfflineGitHubClient:
                    async def search_repositories(self, *_args: Any, **_kwargs: Any) -> Any:
                        raise GitHubAPIError("offline evaluation capture")

                await run_queries(OfflineGitHubClient())
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()

    snapshot = build_snapshot_from_responses(responses, dataset, snapshot_id=snapshot_id)
    snapshot["capture_config"] = {
        "split": split,
        "live_query_limit": live_query_limit,
        "github_timeout_seconds": github_timeout_seconds,
        "include_github": include_github,
        "candidate_corpus": (
            f"{dataset['version']} plus GitHub live results"
            if include_github
            else f"{dataset['version']} only"
        ),
        "metric_scope": "judged repositories only; unjudged live results receive grade 0",
    }
    return snapshot


def validate_channel_snapshot(snapshot: dict[str, Any], dataset: dict[str, Any]) -> None:
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("unsupported channel snapshot schema")
    if snapshot.get("dataset_version") != dataset["version"]:
        raise ValueError("channel snapshot targets a different retrieval dataset")
    if not snapshot.get("snapshot_id"):
        raise ValueError("channel snapshot requires snapshot_id")
    if int(snapshot.get("rrf_rank_constant", 0)) < 1:
        raise ValueError("channel snapshot requires a positive RRF constant")

    valid_query_ids = {
        f"{intent['id']}-{number:02d}"
        for intent in dataset["intents"]
        for number, _query in enumerate(intent["queries"], start=1)
    }
    seen: set[str] = set()
    for item in snapshot.get("queries", []):
        query_id = item.get("query_id")
        if query_id not in valid_query_ids:
            raise ValueError(f"unknown snapshot query_id: {query_id}")
        if query_id in seen:
            raise ValueError(f"duplicate snapshot query_id: {query_id}")
        seen.add(query_id)
        if not item.get("channels"):
            raise ValueError(f"snapshot query has no channel rankings: {query_id}")
        for channel, ranking in item["channels"].items():
            if not channel or not isinstance(ranking, list):
                raise ValueError(f"invalid channel ranking for {query_id}")
            if len(ranking) != len(set(ranking)):
                raise ValueError(f"channel {channel} contains duplicate repositories")


def _query_context(dataset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    repositories = {item["full_name"]: item for item in dataset["repositories"]}
    contexts: dict[str, dict[str, Any]] = {}
    for intent in dataset["intents"]:
        for number, query in enumerate(intent["queries"], start=1):
            constraints = parse_search_constraints(query)
            query_grades = grades_for_query(dataset, intent, number)
            grades = {
                name: grade
                for name, grade in query_grades.items()
                if grade > 0
                and (
                    constraints.language == "Any"
                    or repositories[name]["language"] == constraints.language
                )
                and (
                    not constraints.licenses
                    or repositories[name]["license"] in constraints.licenses
                )
            }
            contexts[f"{intent['id']}-{number:02d}"] = {"query": query, "grades": grades}
    return contexts


def _query_metrics(ranking: list[str], grades: dict[str, int]) -> tuple[float, float, float]:
    top = ranking[:10]
    relevant = {name for name, grade in grades.items() if grade >= 2}
    recall = len(relevant.intersection(top)) / len(relevant) if relevant else 0.0
    ideal = sorted(grades.values(), reverse=True)[:10]
    ideal_dcg = sum(
        (2**grade - 1) / math.log2(rank + 1)
        for rank, grade in enumerate(ideal, start=1)
    )
    dcg = sum(
        (2 ** grades.get(name, 0) - 1) / math.log2(rank + 1)
        for rank, name in enumerate(top, start=1)
    )
    first = next((rank for rank, name in enumerate(top, start=1) if name in relevant), None)
    return recall, dcg / ideal_dcg if ideal_dcg else 0.0, 1 / first if first else 0.0


def evaluate_channel_snapshot(snapshot: dict[str, Any], dataset: dict[str, Any]) -> dict[str, Any]:
    validate_channel_snapshot(snapshot, dataset)
    contexts = _query_context(dataset)
    values: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    channel_coverage: defaultdict[str, int] = defaultdict(int)
    diagnostics: list[dict[str, Any]] = []
    total_queries = len(snapshot["queries"])

    for item in snapshot["queries"]:
        grades = contexts[item["query_id"]]["grades"]
        query_channel_metrics: dict[str, tuple[float, float, float]] = {}
        for channel, ranking in item["channels"].items():
            channel_metrics = _query_metrics(ranking, grades)
            query_channel_metrics[channel] = channel_metrics
            values[channel].append(channel_metrics)
            if ranking:
                channel_coverage[channel] += 1
        fusion = reciprocal_rank_fusion(
            item["channels"], rank_constant=int(snapshot["rrf_rank_constant"])
        )
        rrf_ranking = sorted(fusion.scores, key=lambda name: (-fusion.scores[name], name))
        rrf_metrics = _query_metrics(rrf_ranking, grades)
        final_ranking = item.get("final_ranking", [])
        final_metrics = _query_metrics(final_ranking, grades)
        values["rrf_fusion"].append(rrf_metrics)
        values["final_reranker"].append(final_metrics)

        relevant = {name for name, grade in grades.items() if grade >= 2}
        missing = sorted(relevant.difference(final_ranking[:10]))
        empty_channels = sorted(
            channel for channel, ranking in item["channels"].items() if not ranking
        )
        category = None
        severity = "low"
        summary = ""
        suggestion = ""
        if final_metrics[0] < rrf_metrics[0]:
            category = "reranker_recall_loss"
            severity = "high"
            summary = "最终重排移除了 RRF 已召回的相关仓库"
            suggestion = "检查硬过滤、Top 10 截断和重排特征权重，并保留被移除候选的原因。"
        elif final_metrics[1] + 0.05 < rrf_metrics[1]:
            category = "reranker_order_regression"
            severity = "medium"
            summary = "最终重排的相关结果顺序低于 RRF"
            suggestion = "检查热度、活跃度和次级特征是否压过查询相关性。"
        elif rrf_metrics[0] < 1.0:
            category = "fusion_recall_gap"
            severity = "high" if rrf_metrics[0] == 0 else "medium"
            summary = "所有召回通道融合后仍缺少相关仓库"
            suggestion = "扩展召回词、同义词和候选池，并检查硬约束是否过早过滤。"
        elif empty_channels:
            category = "empty_retrieval_channel"
            severity = "low"
            summary = f"召回通道无结果：{', '.join(empty_channels)}"
            suggestion = "检查该通道的查询改写、阈值和降级状态。"
        if category:
            diagnostics.append(
                {
                    "query_id": item["query_id"],
                    "query": contexts[item["query_id"]]["query"],
                    "category": category,
                    "severity": severity,
                    "summary": summary,
                    "expected_repositories": sorted(relevant),
                    "missing_repositories": missing,
                    "evidence": {
                        "rrf_recall_at_10": round(rrf_metrics[0] * 100, 1),
                        "rrf_ndcg_at_10": round(rrf_metrics[1] * 100, 1),
                        "final_recall_at_10": round(final_metrics[0] * 100, 1),
                        "final_ndcg_at_10": round(final_metrics[1] * 100, 1),
                        **{
                            f"{channel}_recall_at_10": round(metrics[0] * 100, 1)
                            for channel, metrics in query_channel_metrics.items()
                        },
                    },
                    "suggestion": suggestion,
                }
            )

    variants: dict[str, dict[str, float | int]] = {}
    for name, samples in values.items():
        variants[name] = {
            "query_count": len(samples),
            "coverage": round(channel_coverage.get(name, total_queries) / total_queries * 100, 1),
            "recall_at_10": round(sum(item[0] for item in samples) / len(samples) * 100, 1),
            "ndcg_at_10": round(sum(item[1] for item in samples) / len(samples) * 100, 1),
            "mrr_at_10": round(sum(item[2] for item in samples) / len(samples) * 100, 1),
        }
    channel_names = [name for name in variants if name not in {"rrf_fusion", "final_reranker"}]
    best_channel = max(channel_names, key=lambda name: float(variants[name]["ndcg_at_10"]))
    return {
        "schema_version": "retrieval-channel-evaluation-v1",
        "snapshot_id": snapshot["snapshot_id"],
        "dataset_version": snapshot["dataset_version"],
        "ranking_version": snapshot["ranking_version"],
        "query_count": total_queries,
        "best_single_channel": best_channel,
        "rrf_ndcg_lift_vs_best_channel": round(
            float(variants["rrf_fusion"]["ndcg_at_10"])
            - float(variants[best_channel]["ndcg_at_10"]),
            1,
        ),
        "variants": variants,
        "diagnostic_count": len(diagnostics),
        "diagnostics": sorted(
            diagnostics,
            key=lambda item: (
                {"high": 0, "medium": 1, "low": 2}[item["severity"]],
                item["query_id"],
            ),
        ),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="GitSeek channel snapshot tools")
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture", help="convert saved search responses to a snapshot")
    capture.add_argument("--responses", type=Path, required=True)
    capture.add_argument("--snapshot-id", required=True)
    capture.add_argument("--output", type=Path, required=True)
    live_capture = commands.add_parser(
        "live-capture", help="capture fixed queries through local and GitHub recall"
    )
    live_capture.add_argument("--snapshot-id", required=True)
    live_capture.add_argument("--split", choices=("train", "dev", "test", "all"), default="test")
    live_capture.add_argument("--live-query-limit", type=int, choices=(1, 2, 3), default=1)
    live_capture.add_argument("--github-timeout", type=float, default=3.0)
    live_capture.add_argument("--offline", action="store_true")
    live_capture.add_argument("--output", type=Path, required=True)
    evaluate = commands.add_parser("evaluate", help="evaluate a channel snapshot")
    evaluate.add_argument("--snapshot", type=Path, required=True)
    evaluate.add_argument("--output", type=Path)
    args = parser.parse_args()

    dataset = load_retrieval_dataset()
    if args.command == "capture":
        responses = json.loads(args.responses.read_text(encoding="utf-8"))
        payload = build_snapshot_from_responses(
            responses, dataset, snapshot_id=args.snapshot_id
        )
    elif args.command == "live-capture":
        payload = asyncio.run(
            capture_live_snapshot(
                dataset,
                snapshot_id=args.snapshot_id,
                split=args.split,
                live_query_limit=args.live_query_limit,
                github_timeout_seconds=max(args.github_timeout, 0.1),
                include_github=not args.offline,
            )
        )
    else:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        payload = evaluate_channel_snapshot(snapshot, dataset)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
