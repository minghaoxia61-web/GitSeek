import copy

import pytest

from packages.evaluation.annotations import (
    assign_intent_splits,
    build_agreement_report,
    build_blind_annotation_packet,
    build_dataset_profile,
    iter_primary_judgments,
    load_retrieval_dataset,
    validate_annotation_packet,
)


def test_dataset_profile_keeps_intent_paraphrases_in_one_split() -> None:
    dataset = load_retrieval_dataset()
    profile = build_dataset_profile(dataset)

    assert profile["repository_count"] == 23
    assert profile["intent_count"] == 10
    assert profile["query_count"] == 100
    assert profile["judgment_count"] == 2300
    assert profile["queries_by_split"] == {"train": 70, "dev": 10, "test": 20}
    assert sum(profile["queries_by_language"].values()) == 100

    assignments = assign_intent_splits(intent["id"] for intent in dataset["intents"])
    assert set(assignments.values()) == {"train", "dev", "test"}


def test_blind_packet_is_stratified_and_does_not_leak_primary_grades() -> None:
    dataset = load_retrieval_dataset()
    packet = build_blind_annotation_packet(
        dataset,
        annotator_id="reviewer-02",
        sample_rate=0.30,
    )

    assert packet["blind"] is True
    assert packet["task_count"] == 30 * 23
    assert all(task["grade"] is None for task in packet["tasks"])
    assert len({task["intent_id"] for task in packet["tasks"]}) == 10


def test_agreement_report_detects_conflicts_and_returns_kappa() -> None:
    dataset = load_retrieval_dataset()
    packet = build_blind_annotation_packet(
        dataset,
        annotator_id="reviewer-02",
        sample_rate=0.10,
    )
    primary_grades = {item.key: item.grade for item in iter_primary_judgments(dataset)}
    for task in packet["tasks"]:
        task["grade"] = primary_grades[(task["query_id"], task["repository"])]
    packet["tasks"][0]["grade"] = (packet["tasks"][0]["grade"] + 1) % 4

    report = build_agreement_report(packet, dataset)

    assert report["judgment_count"] == 10 * 23
    assert report["query_count"] == 10
    assert report["conflict_count"] == 1
    assert 0 <= report["cohen_kappa"] < 1
    assert 0 <= report["quadratic_weighted_kappa"] < 1


def test_annotation_validation_rejects_incomplete_grades() -> None:
    dataset = load_retrieval_dataset()
    packet = build_blind_annotation_packet(dataset, annotator_id="reviewer-02", sample_rate=0.10)

    with pytest.raises(ValueError, match="grade must be"):
        validate_annotation_packet(packet, dataset)

    wrong_dataset = copy.deepcopy(packet)
    wrong_dataset["dataset_version"] = "another-version"
    with pytest.raises(ValueError, match="different dataset"):
        validate_annotation_packet(wrong_dataset, dataset)
