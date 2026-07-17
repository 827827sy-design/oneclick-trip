from __future__ import annotations

import asyncio
from uuid import uuid4

from langchain_core.messages import HumanMessage

from app.config import load_settings
from app.database import MySQLRepositories
from app.graph.builder import build_travel_graph
from app.memory import PlainRedisCheckpointBackend


async def main() -> None:
    settings = load_settings()
    if not settings.mysql_dsn or not settings.redis_url:
        raise RuntimeError("MYSQL_DSN and REDIS_URL are required")
    repositories = MySQLRepositories(settings.mysql_dsn)
    redis_backend = PlainRedisCheckpointBackend(settings.redis_url)
    graph = build_travel_graph(
        checkpointer=redis_backend.create(),
        plan_repository=repositories,
        preference_repository=repositories,
    )
    suffix = uuid4().hex[:8]
    user_id = f"verify-user-{suffix}"
    conversation_id = f"verify-conversation-{suffix}"
    config = {"configurable": {"thread_id": conversation_id}}
    try:
        await repositories.create_schema()
        first = await graph.ainvoke(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "messages": [
                    HumanMessage(
                        content="帮我规划成都三日游，两个人，总预算5000，喜欢美食"
                    )
                ],
            },
            config=config,
        )
        print(f"plan_saved: {first['plan_saved']}")
        print(f"plan_version: {first['plan_version']}")

        second = await graph.ainvoke(
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "messages": [HumanMessage(content="预算降低1000")],
            },
            config=config,
        )
        print(f"modified_version: {second['plan_version']}")
        print(f"redis_checkpoint: {redis_backend.ping()}")
    finally:
        await repositories.close()
        redis_backend.close()


if __name__ == "__main__":
    asyncio.run(main())
