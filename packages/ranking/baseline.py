import math
import re
from datetime import UTC, datetime

from packages.domain.search import Recommendation, SearchConstraints
from packages.github_client.schemas import GitHubRepository
from packages.ranking.semantic import semantic_similarity


def _constraint_matches(
    repository: GitHubRepository,
    constraints: SearchConstraints,
) -> dict[str, str]:
    matches: dict[str, str] = {}

    if constraints.language != "Any":
        if repository.language is None:
            matches["language"] = "UNKNOWN"
        elif repository.language.casefold() == constraints.language.casefold():
            matches["language"] = "MATCH"
        else:
            matches["language"] = "MISMATCH"

    matches["archived"] = (
        "MISMATCH" if constraints.exclude_archived and repository.archived else "MATCH"
    )

    if constraints.licenses:
        if repository.license is None or repository.license.spdx_id is None:
            matches["license"] = "UNKNOWN"
        elif repository.license.spdx_id in constraints.licenses:
            matches["license"] = "MATCH"
        else:
            matches["license"] = "MISMATCH"

    if constraints.pushed_after:
        if repository.pushed_at is None:
            matches["activity"] = "UNKNOWN"
        elif repository.pushed_at.date() > constraints.pushed_after:
            matches["activity"] = "MATCH"
        else:
            matches["activity"] = "MISMATCH"

    return matches


def _is_eligible(matches: dict[str, str]) -> bool:
    return all(value == "MATCH" for value in matches.values())


def _matches_any_search_term(
    repository: GitHubRepository,
    search_terms: list[str],
) -> bool:
    corpus = " ".join(
        [
            repository.name,
            repository.description or "",
            repository.language or "",
            *repository.topics,
        ]
    ).casefold()
    normalized_corpus = re.sub(r"[-_/]+", " ", corpus)
    for term in search_terms:
        tokens = re.findall(r"[a-z][a-z0-9.+#-]*|[\u4e00-\u9fff]{2,}", term.casefold())
        if tokens and all(token.replace("-", " ") in normalized_corpus for token in tokens):
            return True
    return False


def _score(
    repository: GitHubRepository,
    constraints: SearchConstraints,
    now: datetime,
    query: str | None = None,
    external_similarity: float | None = None,
) -> tuple[float, dict[str, float]]:
    corpus = " ".join(
        [
            repository.name,
            repository.description or "",
            " ".join(repository.topics),
        ]
    ).casefold()
    if constraints.technologies:
        matched = sum(technology.casefold() in corpus for technology in constraints.technologies)
        relevance = 35.0 * matched / len(constraints.technologies)
    else:
        relevance = 20.0
    if query:
        repository_text = " ".join(
            [repository.name, repository.description or "", *repository.topics]
        )
        relevance = max(
            relevance,
            min(35.0, 70.0 * semantic_similarity(query, repository_text)),
        )
    if external_similarity is not None:
        normalized_similarity = max(0.0, min(1.0, (external_similarity - 0.15) / 0.65))
        relevance = max(relevance, 35.0 * normalized_similarity)

    if repository.pushed_at is None:
        activity = 0.0
    else:
        pushed_at = repository.pushed_at
        if pushed_at.tzinfo is None:
            pushed_at = pushed_at.replace(tzinfo=UTC)
        age_days = max((now - pushed_at).days, 0)
        activity = max(30.0 * math.exp(-age_days / 180), 0.0)

    popularity = min(math.log10(repository.stargazers_count + 1) / 5, 1.0) * 15.0
    metadata_fields = [
        repository.description,
        repository.topics,
        repository.language,
        repository.license,
    ]
    metadata = sum(bool(value) for value in metadata_fields) / len(metadata_fields) * 10.0
    license_score = 10.0 if repository.license and repository.license.spdx_id else 0.0

    breakdown = {
        "relevance": round(relevance, 2),
        "activity": round(activity, 2),
        "popularity": round(popularity, 2),
        "metadata": round(metadata, 2),
        "license": round(license_score, 2),
    }
    return round(sum(breakdown.values()), 2), breakdown


def rank_repositories(
    repositories: list[GitHubRepository],
    constraints: SearchConstraints,
    *,
    limit: int,
    now: datetime | None = None,
    query: str | None = None,
    semantic_scores: dict[str, float] | None = None,
    required_search_terms: list[str] | None = None,
) -> tuple[list[Recommendation], int]:
    reference_time = now or datetime.now(UTC)
    scored: list[tuple[GitHubRepository, float, dict[str, float], dict[str, str]]] = []

    for repository in repositories:
        matches = _constraint_matches(repository, constraints)
        if not _is_eligible(matches):
            continue
        if required_search_terms and not _matches_any_search_term(
            repository,
            required_search_terms,
        ):
            continue
        score, breakdown = _score(
            repository,
            constraints,
            reference_time,
            query,
            (semantic_scores or {}).get(repository.full_name),
        )
        scored.append((repository, score, breakdown, matches))

    scored.sort(key=lambda item: (item[1], item[0].stargazers_count), reverse=True)
    results: list[Recommendation] = []
    for rank, (repository, score, breakdown, matches) in enumerate(scored[:limit], start=1):
        reasons = [f"主要语言为 {repository.language}"] if repository.language else []
        if constraints.technologies:
            matched_technologies = [
                technology
                for technology in constraints.technologies
                if technology.casefold()
                in " ".join(
                    [repository.name, repository.description or "", *repository.topics]
                ).casefold()
            ]
            if matched_technologies:
                reasons.append(f"匹配技术栈：{', '.join(matched_technologies)}")
        if repository.pushed_at:
            reasons.append(f"最近推送时间：{repository.pushed_at.date().isoformat()}")
        if repository.license and repository.license.spdx_id:
            reasons.append(f"许可证：{repository.license.spdx_id}")

        risks: list[str] = []
        if not repository.topics:
            risks.append("仓库未配置 Topics，语义判断证据较少")
        if repository.open_issues_count == 0:
            risks.append("当前没有开放 Issue，不一定适合首次贡献")
        risks.append("当前为仓库元数据 Baseline，尚未验证 README、测试和贡献指南")

        results.append(
            Recommendation(
                rank=rank,
                full_name=repository.full_name,
                description=repository.description,
                html_url=repository.html_url,
                score=score,
                stars=repository.stargazers_count,
                language=repository.language,
                license_spdx=(repository.license.spdx_id if repository.license else None),
                pushed_at=repository.pushed_at,
                constraint_match=matches,
                score_breakdown=breakdown,
                reasons=reasons,
                risks=risks,
            )
        )

    return results, len(scored)
