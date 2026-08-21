import argparse
import asyncio

from sqlalchemy import func, select

from packages.database import create_db_engine, create_session_factory
from packages.domain.models import Repository
from packages.domain.settings import get_settings
from packages.github_client import GitHubClient
from workers.sync.repositories import RepositorySynchronizer

SEED_QUERIES = [
    "language:Python archived:false stars:>=10000",
    "language:Python archived:false stars:3000..9999",
    "language:Python archived:false stars:1000..2999",
    "language:Python archived:false stars:300..999",
    "language:Python archived:false stars:100..299",
    "language:Python archived:false stars:30..99",
    "language:Python archived:false stars:10..29",
    "language:Python archived:false stars:1..9",
    "language:Python archived:false stars:0",
]


async def seed_index(target: int, pages_per_query: int) -> int:
    settings = get_settings()
    engine = create_db_engine()
    session_factory = create_session_factory(engine)
    async with GitHubClient(
        token=settings.github_token,
        base_url=settings.github_api_url,
        api_version=settings.github_api_version,
    ) as client:
        with session_factory() as session:
            synchronizer = RepositorySynchronizer(session, client)
            for query in SEED_QUERIES:
                await synchronizer.sync_query(query, pages=pages_per_query)
                indexed = session.scalar(select(func.count(Repository.id))) or 0
                print(f"indexed={indexed} target={target} query={query}")
                if indexed >= target:
                    return indexed
            return session.scalar(select(func.count(Repository.id))) or 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the initial GitSeek repository index")
    parser.add_argument("--target", type=int, default=3000)
    parser.add_argument("--pages-per-query", type=int, default=5)
    args = parser.parse_args()
    indexed = asyncio.run(seed_index(max(args.target, 1), max(args.pages_per_query, 1)))
    print(f"seed complete: indexed={indexed}")


if __name__ == "__main__":
    main()
