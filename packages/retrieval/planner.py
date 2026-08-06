from packages.domain.search import SearchConstraints


def build_github_query(constraints: SearchConstraints) -> str:
    parts = [*constraints.technologies, f"language:{constraints.language}"]
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
