from datetime import UTC, date, datetime

from packages.domain.evaluation import EvaluationFailure, EvaluationMetric, EvaluationSummary
from packages.retrieval import parse_search_constraints

CASES = [
    (
        "Python FastAPI，MIT，最近半年更新",
        {"technology": "FastAPI", "license": "MIT", "purpose": "learning"},
    ),
    (
        "每周 5 小时，第一次贡献 Django 项目",
        {"technology": "Django", "hours": 5, "purpose": "contribution"},
    ),
    ("Windows 可运行的中文 OCR Python 项目", {"platform": "Windows", "purpose": "learning"}),
    ("Apache 2.0 许可证的 RAG 工具，近一年活跃", {"technology": "RAG", "license": "Apache-2.0"}),
    ("找一个 GPL-3.0 的 Python 安全工具", {"license": "GPL-3.0"}),
    ("我想学习 PyTorch 模型部署", {"technology": "PyTorch", "purpose": "learning"}),
    ("最近 30 天更新的 Flask 项目", {"technology": "Flask"}),
    ("寻找 PostgreSQL 和 Redis 后端项目", {"technology": "PostgreSQL"}),
    ("贡献一个 help wanted 的 LLM 项目", {"technology": "LLM", "purpose": "contribution"}),
    ("包含归档仓库的 FastAPI 搜索", {"exclude_archived": False}),
]


def build_evaluation_summary() -> EvaluationSummary:
    failures: list[EvaluationFailure] = []
    reference_date = date(2026, 8, 1)
    passed_fields = 0
    total_fields = 0

    for query, expected in CASES:
        constraints = parse_search_constraints(query, today=reference_date)
        for key, value in expected.items():
            total_fields += 1
            if key == "technology":
                actual: object = value in constraints.technologies
                expected_value: object = True
            elif key == "license":
                actual = value in constraints.licenses
                expected_value = True
            elif key == "hours":
                actual = constraints.weekly_hours
                expected_value = value
            else:
                actual = getattr(constraints, key)
                expected_value = value
            if actual == expected_value:
                passed_fields += 1
            else:
                failures.append(
                    EvaluationFailure(case=query, expected=str(expected_value), actual=str(actual))
                )

    accuracy = round(passed_fields / total_fields * 100, 1) if total_fields else 0.0
    return EvaluationSummary(
        version="parser-rules-v2",
        dataset_version="smoke-queries-v1",
        sample_count=len(CASES),
        generated_at=datetime.now(UTC),
        metrics=[
            EvaluationMetric(
                key="constraint_accuracy",
                label="约束解析准确率",
                value=accuracy,
                unit="%",
                target=95.0,
                passed=accuracy >= 95.0,
            ),
            EvaluationMetric(
                key="case_pass_rate",
                label="完整用例通过率",
                value=round(
                    (len(CASES) - len({item.case for item in failures}))
                    / len(CASES)
                    * 100,
                    1,
                ),
                unit="%",
                target=90.0,
                passed=len({item.case for item in failures}) <= 1,
            ),
        ],
        failures=failures,
    )
