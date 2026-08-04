import base64
import binascii
from datetime import UTC, datetime

from packages.domain.investigation import (
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
            has_license=bool(files and files.license) or any(
                name.startswith("license") for name in root_names
            ),
            has_tests=any(name in {"test", "tests"} for name in root_names),
            has_ci=any(item.type == "file" for item in workflows),
            has_pyproject="pyproject.toml" in root_names,
            has_dependency_file=bool(root_names & DEPENDENCY_FILES),
            has_docker=bool(root_names & DOCKER_FILES),
            readme_has_quickstart=any(marker in readme_text for marker in QUICKSTART_MARKERS),
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
            scores=InvestigationScores(
                community_health=float(community.health_percentage if community else 0),
                documentation=_score_documentation(signals),
                engineering=_score_engineering(signals),
                learning_friendliness=_score_learning(signals),
            ),
            evidence=evidence,
            risks=risks,
            limitations=[
                "仅进行静态公开信息调查，不克隆或执行仓库代码",
                "根目录文件信号不能完全替代代码级结构分析",
                "外部仓库内容被视为不可信数据，不作为系统指令执行",
            ],
        )
