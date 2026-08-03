from packages.domain.search import SearchConstraints


def build_github_query(constraints: SearchConstraints) -> str:
    parts = [*constraints.technologies, f"language:{constraints.language}"]
    if constraints.exclude_archived:
        parts.append("archived:false")
    if constraints.pushed_after:
        parts.append(f"pushed:>{constraints.pushed_after.isoformat()}")
    return " ".join(parts)

