import asyncio
import re
from collections import Counter
from datetime import UTC, datetime

from packages.domain.contribution import (
    ContributionIssue,
    ContributionIssueMatch,
    ContributionIssueMatchResponse,
    ContributionIssueResponse,
    DeveloperProfile,
)
from packages.github_client import GitHubClient
from packages.github_client.schemas import GitHubIssue

BEGINNER_LABELS = {"good first issue", "good-first-issue", "beginner", "first-timers-only"}
HELP_LABELS = {"help wanted", "help-wanted"}
RISK_LABELS = {"security", "breaking change", "architecture", "migration"}
SKILL_ALIASES = {
    "typescript": {"typescript", " ts ", ".ts", "react", "next.js", "nextjs"},
    "javascript": {"javascript", " js ", ".js", "node.js", "nodejs"},
    "python": {"python", "pytest", "django", "fastapi", "flask"},
    "rust": {"rust", "cargo"},
    "go": {" golang", " go "},
    "java": {"java", "spring"},
    "documentation": {"documentation", " docs", "readme", "tutorial"},
    "testing": {" test", "pytest", "coverage", "regression"},
    "api": {" api", "rest", "graphql", "endpoint"},
    "database": {"database", "sql", "postgres", "mysql", "sqlite"},
    "frontend": {"frontend", "react", "vue", "css", "accessibility", " a11y"},
}


def _extract_skills(text: str) -> set[str]:
    normalized = f" {re.sub(r'[-_/]+', ' ', text.casefold())} "
    return {
        skill
        for skill, aliases in SKILL_ALIASES.items()
        if any(alias in normalized for alias in aliases)
    }


def _build_profile(user, repositories) -> DeveloperProfile:
    language_counts = Counter(
        repository.language for repository in repositories if repository.language
    )
    topic_counts = Counter(
        topic.casefold()
        for repository in repositories
        for topic in repository.topics
        if len(topic) <= 30
    )
    sampled_stars = sum(repository.stargazers_count for repository in repositories)
    if user.public_repos >= 20 or sampled_stars >= 100:
        experience_level = "advanced"
    elif user.public_repos >= 5:
        experience_level = "intermediate"
    else:
        experience_level = "beginner"
    return DeveloperProfile(
        username=user.login,
        name=user.name,
        html_url=user.html_url,
        experience_level=experience_level,
        public_repository_count=user.public_repos,
        sampled_repository_count=len(repositories),
        languages=dict(language_counts.most_common()),
        technologies=[topic for topic, _ in topic_counts.most_common(12)],
        limitations=[
            "画像只使用公开仓库的主要语言与 Topics，不读取私有贡献",
            "公开仓库较少时，技能缺失代表证据不足，不代表用户不会该技术",
        ],
    )


def _profile_skills(profile: DeveloperProfile) -> set[str]:
    text = " ".join([*profile.languages, *profile.technologies])
    return _extract_skills(text) | {language.casefold() for language in profile.languages}


def _score_issue(issue: GitHubIssue) -> ContributionIssue | None:
    if issue.state != "open" or issue.pull_request is not None or issue.assignees or issue.locked:
        return None

    labels = [label.name for label in issue.labels]
    normalized = {label.casefold() for label in labels}
    body = (issue.body or "").strip()
    score = 35.0
    reasons = ["Issue 仍处于开放状态且未被认领"]
    risks: list[str] = []

    if normalized & BEGINNER_LABELS:
        score += 30
        reasons.append("带有新人友好标签")
    elif normalized & HELP_LABELS:
        score += 18
        reasons.append("维护者标记为需要帮助")
    if len(body) >= 300:
        score += 18
        reasons.append("任务描述较完整")
    elif len(body) >= 100:
        score += 10
    else:
        risks.append("任务描述较短，开始前需要向维护者确认范围")
    if issue.comments <= 5:
        score += 10
    elif issue.comments >= 15:
        score -= 12
        risks.append("讨论较多，任务范围可能仍有争议")
    if normalized & RISK_LABELS:
        score -= 28
        risks.append("标签表明任务可能涉及安全、迁移或架构风险")

    if normalized & BEGINNER_LABELS and len(body) >= 300 and issue.comments <= 5:
        difficulty = "easy"
    elif normalized & RISK_LABELS or issue.comments >= 15:
        difficulty = "hard"
    else:
        difficulty = "medium"

    return ContributionIssue(
        number=issue.number,
        title=issue.title,
        html_url=issue.html_url,
        labels=labels,
        comments=issue.comments,
        updated_at=issue.updated_at,
        difficulty=difficulty,
        score=max(0.0, min(round(score, 1), 100.0)),
        reasons=reasons,
        risks=risks,
    )


class ContributionIssueService:
    def __init__(self, client: GitHubClient) -> None:
        self._client = client

    async def recommend(
        self,
        owner: str,
        repo: str,
        *,
        limit: int = 5,
    ) -> ContributionIssueResponse:
        issues = await self._client.list_repository_issues(owner, repo, state="open", per_page=100)
        recommendations = [item for issue in issues if (item := _score_issue(issue)) is not None]
        recommendations.sort(key=lambda item: (item.score, item.updated_at), reverse=True)
        return ContributionIssueResponse(
            full_name=f"{owner}/{repo}",
            fetched_at=datetime.now(UTC),
            issues=recommendations[:limit],
            limitations=[
                "难度来自标签、描述长度和讨论规模等静态信号",
                "开始贡献前仍需阅读完整讨论并确认没有关联 Pull Request",
            ],
        )

    async def match_for_user(
        self,
        owner: str,
        repo: str,
        username: str,
        *,
        limit: int = 5,
    ) -> ContributionIssueMatchResponse:
        user, user_repositories, target_repository, issues = await asyncio.gather(
            self._client.get_user(username),
            self._client.list_user_repositories(username, per_page=100),
            self._client.get_repository(owner, repo),
            self._client.list_repository_issues(owner, repo, state="open", per_page=100),
        )
        profile = _build_profile(user, user_repositories)
        known_skills = _profile_skills(profile)
        repository_skills = _extract_skills(
            " ".join(
                [
                    target_repository.language or "",
                    target_repository.description or "",
                    *target_repository.topics,
                ]
            )
        )
        matches: list[ContributionIssueMatch] = []
        for issue in issues:
            baseline = _score_issue(issue)
            if baseline is None:
                continue
            issue_skills = _extract_skills(
                " ".join([issue.title, issue.body or "", *(label.name for label in issue.labels)])
            )
            required_skills = issue_skills | repository_skills
            matched = sorted(required_skills & known_skills)
            missing = sorted(required_skills - known_skills)
            coverage = len(matched) / len(required_skills) if required_skills else 0.5
            fit_score = round(0.6 * baseline.score + 40.0 * coverage, 1)
            reasons = list(baseline.reasons)
            if matched:
                reasons.append(f"公开项目经历匹配：{', '.join(matched)}")
            elif required_skills:
                reasons.append("公开仓库中暂未发现直接匹配技能")
            baseline_payload = baseline.model_dump()
            baseline_payload["reasons"] = reasons
            matches.append(
                ContributionIssueMatch(
                    **baseline_payload,
                    fit_score=max(0.0, min(fit_score, 100.0)),
                    matched_skills=matched,
                    missing_skills=missing[:5],
                    start_checklist=[
                        "阅读完整 Issue 讨论并确认没有关联 Pull Request",
                        "按 CONTRIBUTING 与 README 在本地复现问题",
                        "在编码前向维护者确认实现范围",
                    ],
                )
            )
        matches.sort(key=lambda item: (item.fit_score, item.score, item.updated_at), reverse=True)
        return ContributionIssueMatchResponse(
            full_name=f"{owner}/{repo}",
            profile=profile,
            fetched_at=datetime.now(UTC),
            issues=matches[:limit],
            limitations=[
                *profile.limitations,
                "匹配分是公开证据的启发式排序，不是对开发者能力的测评",
            ],
        )
