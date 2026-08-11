import json
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from packages.domain.evaluation import (
    EvaluationCategory,
    EvaluationFailure,
    EvaluationMetric,
    EvaluationSummary,
)
from packages.retrieval import parse_search_constraints

DATASET_PATH = Path(__file__).parent / "datasets" / "parser-constraints-v2.json"
CATEGORY_LABELS = {
    "language": "编程语言",
    "technology": "技术栈",
    "license": "许可证",
    "purpose": "使用目的",
    "time_budget": "时间预算",
    "platform": "运行平台",
    "activity": "活跃时间",
    "archive": "归档策略",
}


def _load_dataset() -> dict[str, Any]:
    with DATASET_PATH.open(encoding="utf-8") as dataset_file:
        return json.load(dataset_file)


def _display(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return str(value)


def _matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return all(item in actual for item in expected)
    if isinstance(actual, date):
        return actual.isoformat() == expected
    return actual == expected


def build_evaluation_summary() -> EvaluationSummary:
    dataset = _load_dataset()
    reference_date = date.fromisoformat(dataset["reference_date"])
    failures: list[EvaluationFailure] = []
    category_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    passed_fields = 0
    total_fields = 0
    passed_cases = 0

    for item in dataset["cases"]:
        constraints = parse_search_constraints(item["query"], today=reference_date)
        case_passed = True
        for key, expected in item["expected"].items():
            actual = getattr(constraints, key)
            total_fields += 1
            category_counts[item["category"]][1] += 1
            if _matches(actual, expected):
                passed_fields += 1
                category_counts[item["category"]][0] += 1
                continue
            case_passed = False
            failures.append(
                EvaluationFailure(
                    case_id=item["id"],
                    category=item["category"],
                    case=item["query"],
                    expected=_display(expected),
                    actual=_display(actual),
                )
            )
        if case_passed:
            passed_cases += 1

    accuracy = round(passed_fields / total_fields * 100, 1) if total_fields else 0.0
    case_rate = round(passed_cases / len(dataset["cases"]) * 100, 1)
    categories = [
        EvaluationCategory(
            key=key,
            label=CATEGORY_LABELS.get(key, key),
            passed_fields=counts[0],
            total_fields=counts[1],
            accuracy=round(counts[0] / counts[1] * 100, 1),
        )
        for key, counts in category_counts.items()
    ]
    return EvaluationSummary(
        version="parser-rules-v3",
        dataset_version=dataset["version"],
        sample_count=len(dataset["cases"]),
        generated_at=datetime.now(UTC),
        metrics=[
            EvaluationMetric(
                key="constraint_accuracy",
                label="约束字段准确率",
                value=accuracy,
                unit="%",
                target=95.0,
                passed=accuracy >= 95.0,
            ),
            EvaluationMetric(
                key="case_pass_rate",
                label="完整用例通过率",
                value=case_rate,
                unit="%",
                target=90.0,
                passed=case_rate >= 90.0,
            ),
        ],
        categories=categories,
        failures=failures,
    )
