from datetime import UTC, datetime

from packages.domain.contribution import ContributionIssue, ContributionIssueResponse
from packages.github_client import GitHubClient
from packages.github_client.schemas import GitHubIssue

BEGINNER_LABELS = {"good first issue", "good-first-issue", "beginner", "first-timers-only"}
HELP_LABELS = {"help wanted", "help-wanted"}
RISK_LABELS = {"security", "breaking change", "architecture", "migration"}


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
