import re
from datetime import date, timedelta

from packages.domain.search import SearchConstraints

TECHNOLOGY_ALIASES = {
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "rag": "RAG",
    "llm": "LLM",
    "postgresql": "PostgreSQL",
    "redis": "Redis",
    "docker": "Docker",
}

LICENSE_PATTERNS = {
    "MIT": (r"\bmit\b",),
    "Apache-2.0": (r"apache[ -]?2(?:\.0)?",),
    "GPL-3.0": (r"gpl[ -]?3(?:\.0)?",),
    "BSD-3-Clause": (r"bsd[ -]?3",),
}


def _parse_activity_date(query: str, today: date) -> date | None:
    lowered = query.casefold()
    if "最近半年" in query or "近半年" in query:
        return today - timedelta(days=183)
    if "最近一年" in query or "近一年" in query:
        return today - timedelta(days=365)

    days_match = re.search(r"(?:最近|近)\s*(\d+)\s*天", query)
    if days_match:
        return today - timedelta(days=int(days_match.group(1)))

    months_match = re.search(r"(?:最近|近)\s*(\d+)\s*个?月", query)
    if months_match:
        return today - timedelta(days=int(months_match.group(1)) * 30)

    if "recently updated" in lowered or "recently active" in lowered:
        return today - timedelta(days=183)
    return None


def parse_search_constraints(query: str, *, today: date | None = None) -> SearchConstraints:
    reference_date = today or date.today()
    lowered = query.casefold()

    technologies = [
        canonical
        for alias, canonical in TECHNOLOGY_ALIASES.items()
        if alias in lowered
    ]
    licenses = [
        spdx
        for spdx, patterns in LICENSE_PATTERNS.items()
        if any(re.search(pattern, lowered) for pattern in patterns)
    ]

    return SearchConstraints(
        language="Python",
        technologies=technologies,
        licenses=licenses,
        exclude_archived="包含归档" not in query and "include archived" not in lowered,
        pushed_after=_parse_activity_date(query, reference_date),
    )

