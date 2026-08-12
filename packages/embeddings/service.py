import hashlib
import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from packages.domain.models import Repository, RepositoryEmbedding
from packages.github_client.schemas import GitHubRepository

from .client import EmbeddingAPIError, OpenAIEmbeddingClient


def repository_text(repository: GitHubRepository) -> str:
    return "\n".join(
        [
            repository.full_name,
            repository.description or "",
            " ".join(repository.topics),
            repository.language or "",
        ]
    )


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


@dataclass(frozen=True)
class ExternalSimilarityResult:
    scores: dict[str, float]
    model: str
    cached_repositories: int
    embedded_repositories: int


class ExternalEmbeddingService:
    def __init__(self, session: Session, client: OpenAIEmbeddingClient) -> None:
        self._session = session
        self._client = client

    @property
    def model(self) -> str:
        return self._client.model

    async def similarities(
        self,
        query: str,
        repositories: list[GitHubRepository],
    ) -> ExternalSimilarityResult:
        if not repositories:
            return ExternalSimilarityResult({}, self.model, 0, 0)
        cached = self._cached_vectors(repositories)
        missing = [item for item in repositories if item.full_name not in cached]
        inputs = [query, *(repository_text(item) for item in missing)]
        vectors = await self._client.embed(inputs)
        query_vector = vectors[0]
        new_vectors = dict(
            zip((item.full_name for item in missing), vectors[1:], strict=True)
        )
        self._save_vectors(missing, new_vectors)
        all_vectors = {**cached, **new_vectors}
        return ExternalSimilarityResult(
            scores={
                item.full_name: cosine_similarity(query_vector, all_vectors[item.full_name])
                for item in repositories
                if item.full_name in all_vectors
            },
            model=self.model,
            cached_repositories=len(cached),
            embedded_repositories=len(new_vectors),
        )

    def _cached_vectors(self, repositories: list[GitHubRepository]) -> dict[str, list[float]]:
        hashes = {item.full_name: content_hash(repository_text(item)) for item in repositories}
        try:
            rows = self._session.execute(
                select(Repository.full_name, RepositoryEmbedding)
                .join(RepositoryEmbedding, RepositoryEmbedding.repo_id == Repository.id)
                .where(Repository.full_name.in_(hashes))
                .where(RepositoryEmbedding.model == self.model)
            ).all()
        except SQLAlchemyError:
            self._session.rollback()
            return {}
        return {
            name: embedding.vector_json
            for name, embedding in rows
            if embedding.content_hash == hashes[name]
        }

    def _save_vectors(
        self,
        repositories: list[GitHubRepository],
        vectors: dict[str, list[float]],
    ) -> None:
        if not vectors:
            return
        try:
            records = {
                item.full_name: item
                for item in self._session.scalars(
                    select(Repository).where(Repository.full_name.in_(vectors))
                )
            }
            for repository in repositories:
                record = records.get(repository.full_name)
                if record is None:
                    continue
                embedding = self._session.get(RepositoryEmbedding, record.id)
                values = {
                    "model": self.model,
                    "content_hash": content_hash(repository_text(repository)),
                    "dimensions": len(vectors[repository.full_name]),
                    "vector_json": vectors[repository.full_name],
                }
                if embedding is None:
                    self._session.add(RepositoryEmbedding(repo_id=record.id, **values))
                else:
                    for key, value in values.items():
                        setattr(embedding, key, value)
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()


__all__ = [
    "EmbeddingAPIError",
    "ExternalEmbeddingService",
    "ExternalSimilarityResult",
    "OpenAIEmbeddingClient",
]
