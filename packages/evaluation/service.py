import json
import math
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
from packages.github_client.schemas import GitHubRepository
from packages.ranking import rank_repositories
from packages.retrieval import parse_search_constraints

DATASET_PATH = Path(__file__).parent / "datasets" / "parser-constraints-v2.json"
RETRIEVAL_DATASET_PATH = Path(__file__).parent / "datasets" / "retrieval-relevance-v1.json"
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


def _load_retrieval_dataset() -> dict[str, Any]:
    with RETRIEVAL_DATASET_PATH.open(encoding="utf-8") as dataset_file:
        return json.load(dataset_file)


def _retrieval_metrics() -> tuple[dict[str, float], str, int, int]:
    dataset = _load_retrieval_dataset()
    reference_date = date.fromisoformat(dataset["reference_date"])
    reference_time = datetime.combine(reference_date, datetime.min.time(), tzinfo=UTC)
    repositories = []
    for repository_id, item in enumerate(dataset["repositories"], start=1):
        owner, name = item["full_name"].split("/", 1)
        repositories.append(
            GitHubRepository.model_validate(
                {
                    "id": repository_id,
                    "name": name,
                    "full_name": item["full_name"],
                    "owner": {"login": owner},
                    "description": item["description"],
                    "html_url": f"https://github.com/{item['full_name']}",
                    "language": item["language"],
                    "topics": item["topics"],
                    "license": {"spdx_id": item["license"]},
                    "stargazers_count": item["stars"],
                    "open_issues_count": item["open_issues"],
                    "archived": False,
                    "pushed_at": f"{dataset['reference_date']}T00:00:00Z",
                    "created_at": "2018-01-01T00:00:00Z",
                    "updated_at": f"{dataset['reference_date']}T00:00:00Z",
                }
            )
        )

    def evaluate(*, semantic: bool) -> tuple[dict[str, float], int]:
        recalls: list[float] = []
        ndcgs: list[float] = []
        reciprocal_ranks: list[float] = []
        case_count = 0
        repositories_by_name = {item.full_name: item for item in repositories}
        for intent in dataset["intents"]:
            grades = intent["grades"]
            for query in intent["queries"]:
                constraints = parse_search_constraints(query, today=reference_date)
                relevant = {
                    name
                    for name, grade in grades.items()
                    if grade > 0
                    and (
                        constraints.language == "Any"
                        or repositories_by_name[name].language == constraints.language
                    )
                    and (
                        not constraints.licenses
                        or (
                            repositories_by_name[name].license is not None
                            and repositories_by_name[name].license.spdx_id
                            in constraints.licenses
                        )
                    )
                }
                if not relevant:
                    continue
                ideal_grades = sorted(
                    (grade for name, grade in grades.items() if name in relevant),
                    reverse=True,
                )[:10]
                ideal_dcg = sum(
                    (2**grade - 1) / math.log2(rank + 1)
                    for rank, grade in enumerate(ideal_grades, start=1)
                )
                ranked, _ = rank_repositories(
                    repositories,
                    constraints,
                    limit=10,
                    now=reference_time,
                    query=query if semantic else None,
                )
                names = [item.full_name for item in ranked]
                recalls.append(len(relevant.intersection(names)) / len(relevant))
                dcg = sum(
                    (2 ** grades.get(name, 0) - 1) / math.log2(rank + 1)
                    for rank, name in enumerate(names, start=1)
                )
                ndcgs.append(dcg / ideal_dcg if ideal_dcg else 0.0)
                first_relevant = next(
                    (rank for rank, name in enumerate(names, start=1) if name in relevant),
                    None,
                )
                reciprocal_ranks.append(1 / first_relevant if first_relevant else 0.0)
                case_count += 1
        return (
            {
                "recall_at_10": round(sum(recalls) / len(recalls) * 100, 1),
                "ndcg_at_10": round(sum(ndcgs) / len(ndcgs) * 100, 1),
                "mrr_at_10": round(
                    sum(reciprocal_ranks) / len(reciprocal_ranks) * 100,
                    1,
                ),
            },
            case_count,
        )

    keyword_metrics, case_count = evaluate(semantic=False)
    metrics, _ = evaluate(semantic=True)
    metrics["keyword_ndcg_at_10"] = keyword_metrics["ndcg_at_10"]
    metrics["ndcg_lift"] = round(
        metrics["ndcg_at_10"] - keyword_metrics["ndcg_at_10"],
        1,
    )
    judgment_count = case_count * len(repositories)
    return metrics, dataset["version"], case_count, judgment_count


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
    retrieval, retrieval_version, retrieval_cases, judgments = _retrieval_metrics()
    return EvaluationSummary(
        version="parser-rules-v3",
        dataset_version=dataset["version"],
        sample_count=len(dataset["cases"]),
        generated_at=datetime.now(UTC),
        retrieval_dataset_version=retrieval_version,
        retrieval_case_count=retrieval_cases,
        relevance_judgment_count=judgments,
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
            EvaluationMetric(
                key="recall_at_10",
                label="Recall@10",
                value=retrieval["recall_at_10"],
                unit="%",
                target=85.0,
                passed=retrieval["recall_at_10"] >= 85.0,
            ),
            EvaluationMetric(
                key="ndcg_at_10",
                label="nDCG@10",
                value=retrieval["ndcg_at_10"],
                unit="%",
                target=75.0,
                passed=retrieval["ndcg_at_10"] >= 75.0,
            ),
            EvaluationMetric(
                key="mrr_at_10",
                label="MRR@10",
                value=retrieval["mrr_at_10"],
                unit="%",
                target=80.0,
                passed=retrieval["mrr_at_10"] >= 80.0,
            ),
            EvaluationMetric(
                key="keyword_ndcg_at_10",
                label="关键词基线 nDCG@10",
                value=retrieval["keyword_ndcg_at_10"],
                unit="%",
                target=75.0,
                passed=retrieval["keyword_ndcg_at_10"] >= 75.0,
            ),
            EvaluationMetric(
                key="ndcg_lift",
                label="向量混排提升",
                value=retrieval["ndcg_lift"],
                unit="pp",
                target=5.0,
                passed=retrieval["ndcg_lift"] >= 5.0,
            ),
        ],
        categories=categories,
        failures=failures,
    )
