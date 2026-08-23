from typing import Any

__all__ = ["build_evaluation_summary", "evaluate_external_embeddings"]


def __getattr__(name: str) -> Any:
    if name == "build_evaluation_summary":
        from packages.evaluation.service import build_evaluation_summary

        return build_evaluation_summary
    if name == "evaluate_external_embeddings":
        from packages.evaluation.external import evaluate_external_embeddings

        return evaluate_external_embeddings
    raise AttributeError(name)
