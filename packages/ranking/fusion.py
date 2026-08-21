from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class FusionResult:
    """Scores produced by reciprocal-rank fusion across independent recall channels."""

    scores: dict[str, float]
    channel_hits: dict[str, int]


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[str]],
    *,
    rank_constant: int = 60,
) -> FusionResult:
    """Fuse ranked repository identifiers without requiring calibrated channel scores.

    Duplicate identifiers inside one channel count once. A repository returned by several
    independent channels receives evidence from each channel, which makes the fusion robust to the
    very different score scales used by GitHub Search, PostgreSQL FTS, and semantic retrieval.
    """

    if rank_constant < 1:
        raise ValueError("rank_constant must be positive")

    scores: dict[str, float] = {}
    channel_hits: dict[str, int] = {}
    for items in rankings.values():
        seen: set[str] = set()
        for rank, identifier in enumerate(items, start=1):
            if identifier in seen:
                continue
            seen.add(identifier)
            scores[identifier] = scores.get(identifier, 0.0) + 1.0 / (rank_constant + rank)
            channel_hits[identifier] = channel_hits.get(identifier, 0) + 1
    return FusionResult(scores=scores, channel_hits=channel_hits)
