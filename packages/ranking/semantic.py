import hashlib
import math
import re
from functools import lru_cache

VECTOR_DIMENSIONS = 192
CONCEPTS = (
    ("fastapi", "fastapi"),
    ("django", "django"),
    ("cli", "cli", "command line", "命令行", "terminal", "终端"),
    (
        "dataframe",
        "dataframe",
        "data analysis",
        "数据分析",
        "数据处理",
        "表格数据",
        "pandas",
        "polars",
        "data manipulation",
        "scientific data",
    ),
    ("machine-learning", "machine learning", "机器学习", "data science", "人工智能"),
    ("nlp", "nlp", "natural language", "自然语言", "文本模型", "transformer", "llm"),
    (
        "testing",
        "test",
        "testing",
        "测试",
        "pytest",
        "单元测试",
        "property based",
        "test framework",
        "测试框架",
    ),
    (
        "async-http",
        "async http",
        "asyncio",
        "异步",
        "http client",
        "http library",
        "http 库",
        "网络编程",
        "networking",
        "httpx",
        "aiohttp",
    ),
    (
        "workflow",
        "workflow",
        "工作流",
        "scheduler",
        "调度",
        "orchestration",
        "编排",
        "task queue",
        "任务队列",
        "airflow",
    ),
    ("pipeline", "pipeline", "数据管道", "data engineering", "数据工程"),
    ("database", "database", "数据库", "sql", "orm", "object relational"),
    ("scraping", "scraping", "scrapy", "crawler", "爬虫", "抓取", "采集"),
    ("beginner", "beginner", "初学", "新手", "入门", "第一个"),
    ("contribution", "contribution", "contributor", "贡献", "提交", "pull request", "pr"),
)


def _features(text: str) -> list[str]:
    normalized = " ".join(text.casefold().split())
    tokens = re.findall(r"[a-z][a-z0-9.+#-]{1,}|[\u4e00-\u9fff]{2,}", normalized)
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    tokens.extend(chinese[index : index + 2] for index in range(max(len(chinese) - 1, 0)))
    return tokens


@lru_cache(maxsize=8192)
def text_embedding(text: str) -> tuple[float, ...]:
    """Create a stable local vector for mixed Chinese/English repository text."""
    normalized = " ".join(text.casefold().split())
    concept_text = re.sub(r"[-_/]+", " ", normalized)
    vector = [0.0] * VECTOR_DIMENSIONS
    for index, concept in enumerate(CONCEPTS):
        if any(alias in concept_text for alias in concept[1:]):
            vector[index] = 3.0
    lexical_offset = len(CONCEPTS)
    lexical_dimensions = VECTOR_DIMENSIONS - lexical_offset
    for token in _features(normalized):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = lexical_offset + int.from_bytes(digest[:4], "big") % lexical_dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return tuple(vector)
    return tuple(value / norm for value in vector)


def semantic_similarity(left: str, right: str) -> float:
    left_vector = text_embedding(left)
    right_vector = text_embedding(right)
    return sum(a * b for a, b in zip(left_vector, right_vector, strict=True))
