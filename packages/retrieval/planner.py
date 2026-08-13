from packages.domain.search import SearchConstraints

INTENT_QUERY_EXPANSIONS = (
    (("fastapi",), ("fastapi", "fastapi template", "fastapi example")),
    (("django",), ("django", "django cms", "django contribution")),
    (("命令行", "终端", " cli ", "command line"), ("python cli", "command line", "terminal")),
    (
        ("dataframe", "数据分析", "数据处理", "表格数据", "pandas", "polars"),
        ("dataframe", "pandas", "polars"),
    ),
    (
        ("机器学习", "自然语言", "文本模型", "machine learning", "transformer", " nlp "),
        ("machine learning", "transformers", "scikit-learn"),
    ),
    (
        ("测试", "pytest", "unit test", "property based"),
        ("pytest", "python testing", "test framework"),
    ),
    (
        ("异步", "http 客户端", "http client", "asyncio", "httpx", "aiohttp", "网络编程"),
        ("httpx", "aiohttp", "async http"),
    ),
    (
        ("工作流", "调度", "任务队列", "数据管道", "workflow", "scheduler", "orchestration"),
        ("workflow", "scheduler", "task queue"),
    ),
    (
        ("数据库", " orm ", "sql toolkit", "object relational", "sqlalchemy"),
        ("sqlalchemy", "python orm", "database toolkit"),
    ),
    (
        ("爬虫", "抓取", "采集", "scraping", "crawler", "scrapy"),
        ("scrapy", "web scraping", "crawler"),
    ),
)


def infer_github_terms(query: str) -> list[str]:
    """Expand common bilingual intents into precise, free GitHub search terms."""
    normalized = f" {' '.join(query.casefold().split())} "
    terms: list[str] = []
    for triggers, expansions in INTENT_QUERY_EXPANSIONS:
        if any(trigger in normalized for trigger in triggers):
            terms.extend(expansions)
    return list(dict.fromkeys(terms))[:3]


def build_github_query(
    constraints: SearchConstraints,
    search_terms: list[str] | None = None,
) -> str:
    terms = search_terms if search_terms else constraints.technologies
    parts = [*dict.fromkeys(terms)]
    if constraints.language != "Any":
        parts.append(f"language:{constraints.language}")
    if constraints.exclude_archived:
        parts.append("archived:false")
    if constraints.pushed_after:
        parts.append(f"pushed:>{constraints.pushed_after.isoformat()}")
    if constraints.project_size == "small":
        parts.append("stars:<5000")
    elif constraints.project_size == "medium":
        parts.append("stars:1000..30000")
    elif constraints.project_size == "large":
        parts.append("stars:>10000")
    return " ".join(parts)


def build_github_queries(
    constraints: SearchConstraints,
    search_terms: list[str] | None = None,
) -> list[str]:
    terms = list(dict.fromkeys(search_terms if search_terms else constraints.technologies))[:3]
    if not terms:
        return [build_github_query(constraints, [])]
    return [build_github_query(constraints, [term]) for term in terms]
