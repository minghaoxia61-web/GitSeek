"""Deterministic issue-text analysis for the fixer agent.

Regex extraction runs first so the locator always has signals even without an LLM;
``enrich_issue`` optionally adds structured understanding on top.
"""

import json
import re
from dataclasses import dataclass, field, replace

TRACEBACK_FILE_RE = re.compile(r'File "([^"\n]+)", line (\d+)')
PY_PATH_RE = re.compile(r"\b[\w\-./\\]+\.py\b")
BACKTICK_RE = re.compile(r"`([^`\n]{2,120})`")
SNAKE_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
CAMEL_RE = re.compile(r"\b[a-z]+(?:[A-Z][a-z0-9]+){1,}\b")

STOPWORDS = {
    "about", "after", "again", "against", "because", "been", "before", "below", "both",
    "cannot", "could", "does", "doing", "down", "during", "each", "error", "expected",
    "failed", "fails", "failure", "found", "from", "have", "here", "into", "issue",
    "just", "like", "more", "most", "none", "only", "over", "same", "should", "some",
    "such", "than", "that", "their", "them", "then", "there", "these", "they", "this",
    "those", "under", "until", "very", "want", "were", "what", "when", "which", "while",
    "will", "with", "would", "your", "traceback", "raise", "assert", "value", "self",
}

ENRICH_PROMPT = """You analyse a GitHub issue for a code-repair agent.
Return ONLY JSON with this shape:
{{"expected": "one sentence describing correct behaviour",
 "actual": "one sentence describing the reported broken behaviour",
 "module_keywords": ["up to 6 code-level keywords such as module or function names"]}}
Issue title: {title}
Issue body:
{body}"""


@dataclass(frozen=True)
class IssueAnalysis:
    title: str
    traceback_paths: tuple[str, ...] = ()
    file_hints: tuple[str, ...] = ()
    identifiers: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    expected: str | None = None
    actual: str | None = None
    module_keywords: tuple[str, ...] = ()
    extra_terms: tuple[str, ...] = field(default=())

    @property
    def search_terms(self) -> list[str]:
        """Ordered, de-duplicated retrieval terms: paths first (strongest), then identifiers."""
        terms: list[str] = []
        for hint in (*self.traceback_paths, *self.file_hints):
            normalized = hint.replace("\\", "/").strip("./")
            if normalized and normalized not in terms:
                terms.append(normalized)
            basename = normalized.rsplit("/", 1)[-1]
            if basename and basename not in terms:
                terms.append(basename)
        for term in (*self.identifiers, *self.module_keywords, *self.keywords, *self.extra_terms):
            if term and term not in terms:
                terms.append(term)
        return terms[:24]


def _clean_path(value: str) -> str:
    path = value.replace("\\", "/").strip()
    for marker in ("site-packages/", "<", ">", '"'):
        path = path.replace(marker, "")
    return path.strip("/")


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9_]{3,}", text)


def parse_issue(title: str, body: str | None) -> IssueAnalysis:
    text = body or ""
    traceback_paths: list[str] = []
    for match in TRACEBACK_FILE_RE.finditer(text):
        path = _clean_path(match.group(1))
        if path and path not in traceback_paths:
            traceback_paths.append(path)

    file_hints: list[str] = []
    for match in PY_PATH_RE.finditer(f"{title}\n{text}"):
        path = _clean_path(match.group(0))
        if path and path not in file_hints and path not in traceback_paths:
            file_hints.append(path)
    file_hints = file_hints[:10]

    identifiers: list[str] = []
    for token in BACKTICK_RE.findall(text):
        token = token.strip()
        if len(token) > 60 or " " in token:
            continue
        if SNAKE_RE.fullmatch(token) or CAMEL_RE.fullmatch(token):
            if token.lower() not in identifiers and token.lower() not in STOPWORDS:
                identifiers.append(token.lower())
    for match in SNAKE_RE.finditer(text):
        token = match.group(0).lower()
        if token not in identifiers and token not in STOPWORDS:
            identifiers.append(token)
    identifiers = identifiers[:12]

    keywords: list[str] = []
    for word in _words(title) + _words(text[:800]):
        token = word.lower()
        if token in STOPWORDS or token in keywords or token in identifiers:
            continue
        keywords.append(token)
    keywords = keywords[:8]

    return IssueAnalysis(
        title=title,
        traceback_paths=tuple(traceback_paths),
        file_hints=tuple(file_hints),
        identifiers=tuple(identifiers),
        keywords=tuple(keywords),
    )


async def enrich_issue(
    analysis: IssueAnalysis,
    client: object,
    *,
    body: str | None = None,
    max_tokens: int = 512,
) -> IssueAnalysis:
    """Merge LLM understanding into the regex analysis; returns the input unchanged on failure."""
    if client is None:
        return analysis
    try:
        prompt = ENRICH_PROMPT.format(title=analysis.title, body=(body or "")[:4000])
        result = await client.complete(  # type: ignore[attr-defined]
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        payload = json.loads(_extract_json(result.content))
        module_keywords = tuple(
            str(item).strip().lower()
            for item in payload.get("module_keywords", [])[:6]
            if isinstance(item, str) and item.strip()
        )
        return replace(
            analysis,
            expected=str(payload.get("expected") or "")[:300] or None,
            actual=str(payload.get("actual") or "")[:300] or None,
            module_keywords=module_keywords,
            extra_terms=tuple(t for t in module_keywords if t not in analysis.identifiers),
        )
    except Exception:  # noqa: BLE001 - enrichment is best-effort by design
        return analysis


def _extract_json(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found")
    return candidate[start : end + 1]
