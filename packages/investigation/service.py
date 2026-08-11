import asyncio
import base64
import binascii
from datetime import UTC, datetime
from statistics import median

from packages.domain.investigation import (
    ActivitySignals,
    EngineeringSignals,
    EvidenceItem,
    InvestigationScores,
    RepositoryInvestigation,
)
from packages.github_client import GitHubClient, GitHubNotFoundError
from packages.github_client.schemas import GitHubCommunityProfile, GitHubContentItem

DEPENDENCY_FILES = {
    "requirements.txt",
    "requirements-dev.txt",
    "poetry.lock",
    "pdm.lock",
    "uv.lock",
    "pipfile",
}
DOCKER_FILES = {
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}
QUICKSTART_MARKERS = (
    "## installation",
    "## install",
    "## quickstart",
    "## quick start",
    "## getting started",
    "## usage",
)


def _decode_content(item: GitHubContentItem | None) -> str:
    if item is None or item.encoding != "base64" or not item.content:
        return ""
    try:
        return base64.b64decode(item.content).decode("utf-8", errors="replace")
    except (ValueError, binascii.Error):
        return ""


def _score_documentation(signals: EngineeringSignals) -> float:
    return float(
        signals.has_readme * 30
        + signals.has_contributing * 25
        + signals.has_issue_template * 15
        + signals.has_pull_request_template * 10
        + signals.has_code_of_conduct * 10
        + signals.has_security_policy * 10
    )


def _score_engineering(signals: EngineeringSignals) -> float:
    return float(
        signals.has_tests * 30
        + signals.has_ci * 25
        + signals.has_pyproject * 20
        + signals.has_dependency_file * 15
        + signals.has_docker * 10
    )


def _score_learning(signals: EngineeringSignals) -> float:
    return float(
        signals.has_contributing * 25
        + signals.has_issue_template * 20
        + signals.has_tests * 20
        + signals.readme_has_quickstart * 20
        + signals.has_code_of_conduct * 15
    )


def _score_maintenance(activity: ActivitySignals, fetched_at: datetime) -> float:
    score = 0.0
    if activity.latest_release_at is not None:
        release_age = (fetched_at - activity.latest_release_at).days
        score += 25 if release_age <= 180 else 10 if release_age <= 365 else 0
    if activity.median_release_interval_days is not None:
        score += 20 if activity.median_release_interval_days <= 180 else 10
    if activity.merged_pull_request_ratio is not None:
        score += activity.merged_pull_request_ratio * 25
    if activity.median_pull_request_resolution_hours is not None:
        hours = activity.median_pull_request_resolution_hours
        score += 20 if hours <= 168 else 10 if hours <= 720 else 0
    if activity.contributor_continuity == "distributed":
        score += 10
    elif activity.contributor_continuity == "concentrated":
        score += 4
    return round(min(score, 100.0), 1)


class RepositoryInvestigator:
    def __init__(self, client: GitHubClient) -> None:
        self._client = client

    async def investigate(self, owner: str, repo: str) -> RepositoryInvestigation:
        fetched_at = datetime.now(UTC)
        repository = await self._client.get_repository(owner, repo)

        community: GitHubCommunityProfile | None = None
        root: list[GitHubContentItem] = []
        workflows: list[GitHubContentItem] = []
        readme: GitHubContentItem | None = None
        releases = []
        pull_requests = []
        contributors = []
        activity_limitations: list[str] = []
        successful_sources = 1

        try:
            community = await self._client.get_community_profile(owner, repo)
            successful_sources += 1
        except GitHubNotFoundError:
            pass
        try:
            root = await self._client.list_repository_contents(
                owner,
                repo,
                ref=repository.default_branch,
            )
            successful_sources += 1
        except GitHubNotFoundError:
            pass
        try:
            readme = await self._client.get_readme(owner, repo)
            successful_sources += 1
        except GitHubNotFoundError:
            pass
        release_result, pull_result, contributor_result = await asyncio.gather(
            self._client.list_releases(owner, repo, per_page=10),
            self._client.list_pull_requests(owner, repo, per_page=20),
            self._client.list_contributors(owner, repo, per_page=30),
            return_exceptions=True,
        )
        if isinstance(release_result, Exception):
            activity_limitations.append("Release 数据暂不可用")
        else:
            releases = release_result
        if isinstance(pull_result, Exception):
            activity_limitations.append("Pull Request 数据暂不可用")
        else:
            pull_requests = pull_result
        if isinstance(contributor_result, Exception):
            activity_limitations.append("贡献者数据暂不可用")
        else:
            contributors = contributor_result

        root_names = {item.name.casefold() for item in root}
        if ".github" in root_names:
            try:
                workflows = await self._client.list_repository_contents(
                    owner,
                    repo,
                    path=".github/workflows",
                    ref=repository.default_branch,
                )
            except GitHubNotFoundError:
                pass

        files = community.files if community else None
        readme_text = _decode_content(readme).casefold()
        signals = EngineeringSignals(
            has_readme=bool((files and files.readme) or readme),
            has_contributing=bool(files and files.contributing),
            has_code_of_conduct=bool(
                files and (files.code_of_conduct or files.code_of_conduct_file)
            ),
            has_issue_template=bool(files and files.issue_template),
            has_pull_request_template=bool(files and files.pull_request_template),
            has_security_policy=(
                bool(files and files.security_policy) or "security.md" in root_names
            ),
            has_license=bool(files and files.license)
            or any(name.startswith("license") for name in root_names),
            has_tests=any(name in {"test", "tests"} for name in root_names),
            has_ci=any(item.type == "file" for item in workflows),
            has_pyproject="pyproject.toml" in root_names,
            has_dependency_file=bool(root_names & DEPENDENCY_FILES),
            has_docker=bool(root_names & DOCKER_FILES),
            readme_has_quickstart=any(marker in readme_text for marker in QUICKSTART_MARKERS),
        )

        published_releases = sorted(
            (
                release
                for release in releases
                if not release.draft and not release.prerelease and release.published_at
            ),
            key=lambda release: release.published_at or fetched_at,
            reverse=True,
        )
        release_intervals = [
            (newer.published_at - older.published_at).total_seconds() / 86_400
            for newer, older in zip(published_releases, published_releases[1:], strict=False)
            if newer.published_at and older.published_at
        ]
        resolved_pull_requests = [item for item in pull_requests if item.closed_at]
        resolution_hours = [
            (item.closed_at - item.created_at).total_seconds() / 3_600
            for item in resolved_pull_requests
            if item.closed_at
        ]
        total_contributions = sum(item.contributions for item in contributors)
        top_contributor_share = (
            max((item.contributions for item in contributors), default=0) / total_contributions
            if total_contributions
            else None
        )
        if len(contributors) < 2 or top_contributor_share is None:
            contributor_continuity = "unknown"
        elif len(contributors) >= 3 and top_contributor_share <= 0.8:
            contributor_continuity = "distributed"
        else:
            contributor_continuity = "concentrated"
        activity = ActivitySignals(
            releases_sampled=len(published_releases),
            latest_release_at=(published_releases[0].published_at if published_releases else None),
            median_release_interval_days=(
                round(median(release_intervals), 1) if release_intervals else None
            ),
            pull_requests_sampled=len(resolved_pull_requests),
            merged_pull_request_ratio=(
                round(
                    sum(item.merged_at is not None for item in resolved_pull_requests)
                    / len(resolved_pull_requests),
                    3,
                )
                if resolved_pull_requests
                else None
            ),
            median_pull_request_resolution_hours=(
                round(median(resolution_hours), 1) if resolution_hours else None
            ),
            contributors_sampled=len(contributors),
            top_contributor_share=(
                round(top_contributor_share, 3) if top_contributor_share is not None else None
            ),
            contributor_continuity=contributor_continuity,
        )

        source_root = f"{repository.html_url}/tree/{repository.default_branch}"
        source_community = f"https://api.github.com/repos/{owner}/{repo}/community/profile"
        evidence = [
            EvidenceItem(
                id="community-health",
                fact="GitHub community profile completeness",
                value=community.health_percentage if community else 0,
                source_url=source_community,
                fetched_at=fetched_at,
                confidence="high" if community else "low",
            ),
            EvidenceItem(
                id="contributing-guide",
                fact="Contribution guide detected",
                value=signals.has_contributing,
                source_url=(
                    files.contributing.html_url
                    if files and files.contributing and files.contributing.html_url
                    else source_community
                ),
                fetched_at=fetched_at,
                confidence="high" if community else "low",
            ),
            EvidenceItem(
                id="test-directory",
                fact="Root test directory detected",
                value=signals.has_tests,
                source_url=source_root,
                fetched_at=fetched_at,
                confidence="high" if root else "low",
            ),
            EvidenceItem(
                id="ci-workflows",
                fact="GitHub Actions workflow detected",
                value=signals.has_ci,
                source_url=f"{source_root}/.github/workflows",
                fetched_at=fetched_at,
                confidence="high" if ".github" in root_names else "medium",
            ),
            EvidenceItem(
                id="python-project-config",
                fact="pyproject.toml detected",
                value=signals.has_pyproject,
                source_url=source_root,
                fetched_at=fetched_at,
                confidence="high" if root else "low",
            ),
            EvidenceItem(
                id="readme-quickstart",
                fact="README quick-start section detected",
                value=signals.readme_has_quickstart,
                source_url=readme.html_url if readme and readme.html_url else repository.html_url,
                fetched_at=fetched_at,
                confidence="high" if readme_text else "low",
            ),
            EvidenceItem(
                id="release-cadence",
                fact="Published release cadence",
                value=(
                    f"{activity.median_release_interval_days} days"
                    if activity.median_release_interval_days is not None
                    else f"{activity.releases_sampled} published releases sampled"
                ),
                source_url=f"{repository.html_url}/releases",
                fetched_at=fetched_at,
                confidence="high" if releases else "low",
            ),
            EvidenceItem(
                id="pull-request-resolution",
                fact="Closed pull request resolution time",
                value=(
                    f"{activity.median_pull_request_resolution_hours} hours median"
                    if activity.median_pull_request_resolution_hours is not None
                    else "No closed pull requests sampled"
                ),
                source_url=f"{repository.html_url}/pulls?q=is%3Apr+is%3Aclosed",
                fetched_at=fetched_at,
                confidence="high" if pull_requests else "low",
            ),
            EvidenceItem(
                id="contributor-continuity",
                fact="Contributor activity distribution",
                value=activity.contributor_continuity,
                source_url=f"{repository.html_url}/graphs/contributors",
                fetched_at=fetched_at,
                confidence="medium" if contributors else "low",
            ),
        ]

        risks: list[str] = []
        if not signals.has_contributing:
            risks.append("未发现贡献指南，首次贡献准备路径可能不明确")
        if not signals.has_tests:
            risks.append("根目录未发现 tests/test，仍需进一步检查嵌套测试结构")
        if not signals.has_ci:
            risks.append("未发现 GitHub Actions 工作流，自动化质量信号不足")
        if not signals.has_security_policy:
            risks.append("未发现安全策略文件")
        if activity.latest_release_at is None:
            risks.append("未发现已发布的正式版本，版本节奏无法确认")
        elif (fetched_at - activity.latest_release_at).days > 365:
            risks.append("最近一次正式版本发布已超过一年")
        if activity.contributor_continuity == "concentrated":
            risks.append("近期贡献主要集中于少数贡献者，维护连续性需进一步确认")

        if successful_sources == 4:
            confidence = "high"
        elif successful_sources >= 2:
            confidence = "medium"
        else:
            confidence = "low"
        return RepositoryInvestigation(
            full_name=repository.full_name,
            description=repository.description,
            html_url=repository.html_url,
            default_branch=repository.default_branch,
            fetched_at=fetched_at,
            confidence=confidence,
            signals=signals,
            activity=activity,
            scores=InvestigationScores(
                community_health=float(community.health_percentage if community else 0),
                documentation=_score_documentation(signals),
                engineering=_score_engineering(signals),
                learning_friendliness=_score_learning(signals),
                maintenance=_score_maintenance(activity, fetched_at),
            ),
            evidence=evidence,
            risks=risks,
            limitations=[
                "仅进行静态公开信息调查，不克隆或执行仓库代码",
                "根目录文件信号不能完全替代代码级结构分析",
                "外部仓库内容被视为不可信数据，不作为系统指令执行",
                *activity_limitations,
            ],
        )
