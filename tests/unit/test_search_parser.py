from datetime import date

from packages.retrieval import build_github_queries, build_github_query, parse_search_constraints


def test_parses_chinese_search_constraints() -> None:
    constraints = parse_search_constraints(
        "找一个适合 Python 初学者学习 FastAPI 的项目，MIT 或 Apache-2.0，最近半年有更新",
        today=date(2026, 8, 3),
    )

    assert constraints.language == "Python"
    assert constraints.technologies == ["FastAPI"]
    assert constraints.licenses == ["MIT", "Apache-2.0"]
    assert constraints.exclude_archived is True
    assert constraints.pushed_after == date(2026, 2, 1)
    assert build_github_query(constraints) == (
        "FastAPI language:Python archived:false pushed:>2026-02-01"
    )


def test_archived_repositories_can_be_explicitly_included() -> None:
    constraints = parse_search_constraints("Python 项目，包含归档仓库")

    assert constraints.exclude_archived is False
    assert "archived:false" not in build_github_query(constraints)


def test_model_terms_create_broad_independent_queries() -> None:
    constraints = parse_search_constraints("Python FastAPI 项目")

    assert build_github_queries(constraints, ["fastapi", "tutorial", "example"]) == [
        "fastapi language:Python archived:false",
        "tutorial language:Python archived:false",
        "example language:Python archived:false",
    ]
