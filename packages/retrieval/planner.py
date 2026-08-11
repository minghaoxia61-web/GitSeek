from packages.domain.search import SearchConstraints


def build_github_query(
    constraints: SearchConstraints,
    search_terms: list[str] | None = None,
) -> str:
    terms = search_terms if search_terms else constraints.technologies
    parts = [*dict.fromkeys(terms)]
    if constraints.language != "Any":
        parts.append(f"language:{constraints.language}")
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


def build_github_queries(
    constraints: SearchConstraints,
    search_terms: list[str] | None = None,
) -> list[str]:
    terms = list(dict.fromkeys(search_terms if search_terms else constraints.technologies))[:3]
    if not terms:
        return [build_github_query(constraints, [])]
    return [build_github_query(constraints, [term]) for term in terms]
