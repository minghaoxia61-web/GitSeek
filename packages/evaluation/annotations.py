from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_DATASET_PATH = Path(__file__).parent / "datasets" / "retrieval-relevance-v2.json"
GRADE_VALUES = (0, 1, 2, 3)
SPLIT_SEED = "gitseek-retrieval-split-v1"


@dataclass(frozen=True)
class Judgment:
    query_id: str
    intent_id: str
    query: str
    repository: str
    grade: int
    split: str
    language_bucket: str

    @property
    def key(self) -> tuple[str, str]:
        return self.query_id, self.repository


def load_retrieval_dataset(path: Path = DEFAULT_DATASET_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as dataset_file:
        dataset = json.load(dataset_file)
    validate_retrieval_dataset(dataset)
    return dataset


def validate_retrieval_dataset(dataset: dict[str, Any]) -> None:
    required = {"version", "reference_date", "repositories", "intents"}
    missing = required.difference(dataset)
    if missing:
        raise ValueError(f"retrieval dataset is missing fields: {sorted(missing)}")

    repository_names = [item.get("full_name") for item in dataset["repositories"]]
    if any(not name for name in repository_names):
        raise ValueError("every repository must have a full_name")
    if len(repository_names) != len(set(repository_names)):
        raise ValueError("repository full_name values must be unique")

    intent_ids: set[str] = set()
    query_texts: set[str] = set()
    repository_set = set(repository_names)
    for intent in dataset["intents"]:
        intent_id = intent.get("id")
        if not intent_id or intent_id in intent_ids:
            raise ValueError("intent ids must be present and unique")
        intent_ids.add(intent_id)
        if not intent.get("queries"):
            raise ValueError(f"intent {intent_id} has no queries")
        unknown = set(intent.get("grades", {})).difference(repository_set)
        if unknown:
            raise ValueError(f"intent {intent_id} grades unknown repositories: {sorted(unknown)}")
        for grade in intent.get("grades", {}).values():
            if grade not in GRADE_VALUES:
                raise ValueError(f"intent {intent_id} has grade outside 0..3")
        for query in intent["queries"]:
            if query in query_texts:
                raise ValueError(f"duplicate query text: {query}")
            query_texts.add(query)
    valid_query_ids = {
        f"{intent['id']}-{number:02d}"
        for intent in dataset["intents"]
        for number, _query in enumerate(intent["queries"], start=1)
    }
    for query_id, grades in dataset.get("query_grade_overrides", {}).items():
        if query_id not in valid_query_ids:
            raise ValueError(f"query grade override has unknown query id: {query_id}")
        unknown = set(grades).difference(repository_set)
        if unknown:
            raise ValueError(f"query {query_id} grades unknown repositories: {sorted(unknown)}")
        if any(grade not in GRADE_VALUES for grade in grades.values()):
            raise ValueError(f"query {query_id} has grade outside 0..3")


def grades_for_query(
    dataset: dict[str, Any], intent: dict[str, Any], query_number: int
) -> dict[str, int]:
    query_id = f"{intent['id']}-{query_number:02d}"
    return dataset.get("query_grade_overrides", {}).get(query_id, intent["grades"])


def assign_intent_splits(intent_ids: Iterable[str]) -> dict[str, str]:
    """Create a stable 70/15/15 split while keeping paraphrases together."""

    unique_ids = sorted(set(intent_ids))
    ordered = sorted(
        unique_ids,
        key=lambda item: hashlib.sha256(f"{SPLIT_SEED}:{item}".encode()).hexdigest(),
    )
    count = len(ordered)
    train_count = round(count * 0.70)
    dev_count = int(count * 0.15)
    if count >= 3:
        train_count = min(max(train_count, 1), count - 2)
        dev_count = min(max(dev_count, 1), count - train_count - 1)
    assignments: dict[str, str] = {}
    for position, intent_id in enumerate(ordered):
        if position < train_count:
            split = "train"
        elif position < train_count + dev_count:
            split = "dev"
        else:
            split = "test"
        assignments[intent_id] = split
    return assignments


def query_language_bucket(query: str) -> str:
    return "zh" if any("\u4e00" <= character <= "\u9fff" for character in query) else "en"


def iter_primary_judgments(dataset: dict[str, Any]) -> Iterable[Judgment]:
    split_by_intent = assign_intent_splits(intent["id"] for intent in dataset["intents"])
    repositories = [item["full_name"] for item in dataset["repositories"]]
    for intent in dataset["intents"]:
        intent_id = intent["id"]
        for query_number, query in enumerate(intent["queries"], start=1):
            query_id = f"{intent_id}-{query_number:02d}"
            grades = grades_for_query(dataset, intent, query_number)
            for repository in repositories:
                yield Judgment(
                    query_id=query_id,
                    intent_id=intent_id,
                    query=query,
                    repository=repository,
                    grade=int(grades.get(repository, 0)),
                    split=split_by_intent[intent_id],
                    language_bucket=query_language_bucket(query),
                )


def build_dataset_profile(dataset: dict[str, Any]) -> dict[str, Any]:
    judgments = list(iter_primary_judgments(dataset))
    queries = {
        (item.query_id, item.intent_id, item.split, item.language_bucket)
        for item in judgments
    }
    return {
        "dataset_version": dataset["version"],
        "repository_count": len(dataset["repositories"]),
        "intent_count": len(dataset["intents"]),
        "query_count": len(queries),
        "judgment_count": len(judgments),
        "queries_by_split": dict(Counter(item[2] for item in queries)),
        "queries_by_language": dict(Counter(item[3] for item in queries)),
        "queries_by_intent": dict(Counter(item[1] for item in queries)),
    }


def _sample_query_ids(
    judgments: list[Judgment],
    *,
    sample_rate: float,
    seed: str,
) -> set[str]:
    if not 0 < sample_rate <= 1:
        raise ValueError("sample_rate must be in the interval (0, 1]")
    query_ids_by_intent: dict[str, set[str]] = defaultdict(set)
    for judgment in judgments:
        query_ids_by_intent[judgment.intent_id].add(judgment.query_id)

    selected: set[str] = set()
    for _intent_id, query_ids in query_ids_by_intent.items():
        ordered = sorted(
            query_ids,
            key=lambda item: hashlib.sha256(f"{seed}:{item}".encode()).hexdigest(),
        )
        sample_count = min(len(ordered), max(1, round(len(ordered) * sample_rate)))
        selected.update(ordered[:sample_count])
    return selected


def build_blind_annotation_packet(
    dataset: dict[str, Any],
    *,
    annotator_id: str,
    sample_rate: float = 0.30,
    seed: str = "gitseek-secondary-annotation-v1",
) -> dict[str, Any]:
    if not annotator_id.strip():
        raise ValueError("annotator_id must not be blank")
    judgments = list(iter_primary_judgments(dataset))
    selected_query_ids = _sample_query_ids(judgments, sample_rate=sample_rate, seed=seed)
    tasks = [
        {
            "query_id": item.query_id,
            "intent_id": item.intent_id,
            "query": item.query,
            "repository": item.repository,
            "split": item.split,
            "language_bucket": item.language_bucket,
            "grade": None,
        }
        for item in judgments
        if item.query_id in selected_query_ids
    ]
    return {
        "schema_version": "retrieval-annotations-v1",
        "dataset_version": dataset["version"],
        "annotator_id": annotator_id,
        "blind": True,
        "grade_scale": {
            "0": "不相关",
            "1": "弱相关",
            "2": "相关",
            "3": "高度相关",
        },
        "sampling": {"strategy": "stratified-by-intent", "rate": sample_rate, "seed": seed},
        "task_count": len(tasks),
        "tasks": tasks,
    }


def validate_annotation_packet(packet: dict[str, Any], dataset: dict[str, Any]) -> None:
    if packet.get("schema_version") != "retrieval-annotations-v1":
        raise ValueError("unsupported annotation schema_version")
    if packet.get("dataset_version") != dataset["version"]:
        raise ValueError("annotation packet targets a different dataset version")
    if not packet.get("annotator_id"):
        raise ValueError("annotation packet has no annotator_id")

    primary = {item.key: item for item in iter_primary_judgments(dataset)}
    seen: set[tuple[str, str]] = set()
    for task in packet.get("tasks", []):
        key = (task.get("query_id"), task.get("repository"))
        if key in seen:
            raise ValueError(f"duplicate annotation task: {key}")
        seen.add(key)
        if key not in primary:
            raise ValueError(f"annotation task is not part of the dataset: {key}")
        grade = task.get("grade")
        if grade not in GRADE_VALUES:
            raise ValueError(f"annotation grade must be an integer from 0 to 3: {key}")


def _cohen_kappa(first: list[int], second: list[int]) -> float:
    observed = sum(left == right for left, right in zip(first, second, strict=True)) / len(first)
    first_counts = Counter(first)
    second_counts = Counter(second)
    expected = sum(
        (first_counts[grade] / len(first)) * (second_counts[grade] / len(second))
        for grade in GRADE_VALUES
    )
    return 1.0 if expected == 1.0 and observed == 1.0 else (observed - expected) / (1 - expected)


def _quadratic_weighted_kappa(first: list[int], second: list[int]) -> float:
    maximum_distance = (max(GRADE_VALUES) - min(GRADE_VALUES)) ** 2
    observed_disagreement = sum(
        (left - right) ** 2 for left, right in zip(first, second, strict=True)
    )
    first_counts = Counter(first)
    second_counts = Counter(second)
    expected_disagreement = sum(
        first_counts[left] * second_counts[right] * (left - right) ** 2
        for left in GRADE_VALUES
        for right in GRADE_VALUES
    ) / len(first)
    if maximum_distance == 0 or expected_disagreement == 0:
        return 1.0 if observed_disagreement == 0 else 0.0
    return 1 - observed_disagreement / expected_disagreement


def build_agreement_report(packet: dict[str, Any], dataset: dict[str, Any]) -> dict[str, Any]:
    validate_annotation_packet(packet, dataset)
    primary = {item.key: item for item in iter_primary_judgments(dataset)}
    first: list[int] = []
    second: list[int] = []
    conflicts: list[dict[str, Any]] = []
    for task in packet["tasks"]:
        item = primary[(task["query_id"], task["repository"])]
        secondary_grade = int(task["grade"])
        first.append(item.grade)
        second.append(secondary_grade)
        if item.grade != secondary_grade:
            conflicts.append(
                {
                    "query_id": item.query_id,
                    "query": item.query,
                    "repository": item.repository,
                    "primary_grade": item.grade,
                    "secondary_grade": secondary_grade,
                    "absolute_difference": abs(item.grade - secondary_grade),
                }
            )
    exact_agreement = (
        sum(left == right for left, right in zip(first, second, strict=True)) / len(first)
    )
    return {
        "schema_version": "retrieval-agreement-v1",
        "dataset_version": dataset["version"],
        "annotator_id": packet["annotator_id"],
        "generated_at": datetime.now(UTC).isoformat(),
        "judgment_count": len(first),
        "query_count": len({task["query_id"] for task in packet["tasks"]}),
        "exact_agreement": round(exact_agreement, 4),
        "cohen_kappa": round(_cohen_kappa(first, second), 4),
        "quadratic_weighted_kappa": round(_quadratic_weighted_kappa(first, second), 4),
        "conflict_count": len(conflicts),
        "conflicts": sorted(
            conflicts,
            key=lambda item: (-item["absolute_difference"], item["query_id"], item["repository"]),
        ),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="GitSeek retrieval annotation utilities")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    commands = parser.add_subparsers(dest="command", required=True)

    profile_parser = commands.add_parser("profile", help="print dataset split and bucket counts")
    profile_parser.add_argument("--output", type=Path)

    export_parser = commands.add_parser("export", help="export a blind secondary annotation packet")
    export_parser.add_argument("--annotator", required=True)
    export_parser.add_argument("--sample-rate", type=float, default=0.30)
    export_parser.add_argument("--seed", default="gitseek-secondary-annotation-v1")
    export_parser.add_argument("--output", type=Path, required=True)

    agreement_parser = commands.add_parser(
        "agreement", help="validate labels and compute agreement"
    )
    agreement_parser.add_argument("--annotations", type=Path, required=True)
    agreement_parser.add_argument("--output", type=Path)

    args = parser.parse_args()
    dataset = load_retrieval_dataset(args.dataset)
    if args.command == "profile":
        payload = build_dataset_profile(dataset)
    elif args.command == "export":
        payload = build_blind_annotation_packet(
            dataset,
            annotator_id=args.annotator,
            sample_rate=args.sample_rate,
            seed=args.seed,
        )
    else:
        with args.annotations.open(encoding="utf-8") as annotation_file:
            payload = build_agreement_report(json.load(annotation_file), dataset)

    output = getattr(args, "output", None)
    if output:
        _write_json(output, payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
