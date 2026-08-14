from datetime import date

from packages.retrieval import (
    build_github_queries,
    build_github_query,
    infer_github_terms,
    parse_search_constraints,
)


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


def test_does_not_default_to_python_when_language_is_unspecified() -> None:
    constraints = parse_search_constraints("找一个适合初学者的命令行音乐播放器")

    assert constraints.language == "Any"
    assert "language:" not in build_github_query(constraints)


def test_infers_common_non_python_language() -> None:
    constraints = parse_search_constraints("Rust 写的终端音乐播放器")

    assert constraints.language == "Rust"
    assert "language:Rust" in build_github_query(constraints)


def test_expands_bilingual_intents_without_a_model_call() -> None:
    assert infer_github_terms("Python 异步 HTTP 客户端") == [
        "httpx",
        "aiohttp",
        "async http",
    ]
    assert infer_github_terms("适合新手的网页爬虫") == [
        "scrapy",
        "web scraping",
        "crawler",
    ]
    assert infer_github_terms("Python 数据分析 DataFrame 项目") == [
        "dataframe",
        "pandas",
        "polars",
    ]
    assert infer_github_terms("想做一个微信小程序") == [
        "wechat miniprogram",
        "taro",
        "uni-app",
    ]
    assert infer_github_terms("适合 Windows 的 Rust GUI 项目") == [
        "egui",
        "iced",
        "rust gui",
    ]
    assert infer_github_terms("Android Jetpack Compose 入门") == [
        "android",
        "kotlin android",
        "jetpack compose",
    ]
