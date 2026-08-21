import pytest

from packages.ranking import reciprocal_rank_fusion


def test_rrf_rewards_repositories_recalled_by_multiple_channels() -> None:
    result = reciprocal_rank_fusion(
        {
            "keyword": ["example/keyword-only", "example/shared"],
            "semantic": ["example/semantic-only", "example/shared"],
            "github": ["example/shared", "example/live-only"],
        }
    )

    assert result.scores["example/shared"] > result.scores["example/keyword-only"]
    assert result.channel_hits["example/shared"] == 3


def test_rrf_ignores_duplicates_inside_a_channel() -> None:
    result = reciprocal_rank_fusion({"keyword": ["example/a", "example/a"]})

    assert result.scores["example/a"] == pytest.approx(1 / 61)
    assert result.channel_hits["example/a"] == 1


def test_rrf_rejects_invalid_rank_constant() -> None:
    with pytest.raises(ValueError, match="rank_constant"):
        reciprocal_rank_fusion({}, rank_constant=0)
