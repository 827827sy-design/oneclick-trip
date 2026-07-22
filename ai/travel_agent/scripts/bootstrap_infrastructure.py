from __future__ import annotations

import asyncio

from app.config import load_settings
from app.database import MySQLRepositories
from app.memory import PlainRedisCheckpointBackend
from app.vectorstore import ChromaTravelKnowledgeBase


async def main() -> None:
    settings = load_settings()
    statuses: dict[str, str] = {}

    if settings.mysql_dsn:
        repositories = MySQLRepositories(settings.mysql_dsn)
        try:
            await repositories.create_schema()
            await repositories.ping()
            statuses["mysql"] = "ok"
        finally:
            await repositories.close()
    else:
        statuses["mysql"] = "not-configured"

    if settings.redis_url:
        redis_backend = PlainRedisCheckpointBackend(settings.redis_url)
        try:
            statuses["redis"] = "ok" if redis_backend.ping() else "unavailable"
        finally:
            redis_backend.close()
    else:
        statuses["redis"] = "not-configured"

    knowledge_base = ChromaTravelKnowledgeBase(
        settings.chroma_persist_directory,
        collection_prefix=settings.chroma_collection,
    )
    knowledge_base.remove_documents_by_source("demo-seed")
    statuses["chroma"] = f"ok ({knowledge_base.count('poi')} poi documents)"

    for name, status in statuses.items():
        print(f"{name}: {status}")


if __name__ == "__main__":
    asyncio.run(main())
