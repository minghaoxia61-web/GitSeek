import copy

import pytest

from packages.evaluation.annotations import load_retrieval_dataset
from packages.evaluation.channels import (
    build_snapshot_from_responses,
    evaluate_channel_snapshot,
    validate_channel_snapshot,
)


def _snapshot() -> tuple[dict, dict]:
    dataset = load_retrieval_dataset()
    query = dataset["intents"][0]["queries"][0]
    responses = [
        {
            "query": query,
            "ranking_version": "hybrid-rrf-v12",
            "retrieval": {
                "fusion_rank_constant": 60,
                "channel_top_results": {
                    "local_keyword": ["pallets/flask", "fastapi/fastapi"],
                    "local_semantic": [
                        "fastapi/fastapi",
                        "fastapi/full-stack-fastapi-template",
                    ],
                },
            },
            "results": [
                {"full_name": "fastapi/fastapi"},
                {"full_name": "fastapi/full-stack-fastapi-template"},
            ],
        }
    ]
    return build_snapshot_from_responses(
        responses, dataset, snapshot_id="unit-test-snapshot"
    ), dataset


def test_build_and_evaluate_channel_snapshot() -> None:
    snapshot, dataset = _snapshot()

    report = evaluate_channel_snapshot(snapshot, dataset)

    assert snapshot["query_count"] == 1
    assert report["best_single_channel"] == "local_semantic"
    assert report["variants"]["local_keyword"]["recall_at_10"] < 100
    assert report["variants"]["local_semantic"]["recall_at_10"] == 100
    assert report["variants"]["rrf_fusion"]["query_count"] == 1
    assert report["variants"]["final_reranker"]["ndcg_at_10"] == 100
    assert report["diagnostic_count"] == 0


def test_snapshot_rejects_duplicate_channel_results() -> None:
    snapshot, dataset = _snapshot()
    broken = copy.deepcopy(snapshot)
    broken["queries"][0]["channels"]["local_keyword"] = [
        "fastapi/fastapi",
        "fastapi/fastapi",
    ]

    with pytest.raises(ValueError, match="duplicate repositories"):
        validate_channel_snapshot(broken, dataset)


def test_snapshot_capture_rejects_unversioned_channel_diagnostics() -> None:
    dataset = load_retrieval_dataset()
    query = dataset["intents"][0]["queries"][0]

    with pytest.raises(ValueError, match="no channel rankings"):
        build_snapshot_from_responses(
            [
                {
                    "query": query,
                    "ranking_version": "hybrid-rrf-v12",
                    "retrieval": {"fusion_rank_constant": 60},
                    "results": [],
                }
            ],
            dataset,
            snapshot_id="missing-rankings",
        )
