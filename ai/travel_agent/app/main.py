from contextlib import asynccontextmanager
from dataclasses import replace
from typing import AsyncIterator

from fastapi import FastAPI

from app.api.routes import router
from app.booking import BookingBackend, MockJavaBookingBackend
from app.config import Settings, load_settings
from app.database import MySQLRepositories, PlanRepository, UserPreferenceRepository
from app.graph.builder import build_travel_graph
from app.llm import build_agent_overrides
from app.memory.checkpoints import (
    CheckpointBackend,
    InMemoryCheckpointBackend,
    PlainRedisCheckpointBackend,
)
from app.vectorstore import ChromaTravelKnowledgeBase


def create_app(
    checkpoint_backend: CheckpointBackend | None = None,
    booking_backend: BookingBackend | None = None,
    plan_repository: PlanRepository | None = None,
    preference_repository: UserPreferenceRepository | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    isolated_mode = checkpoint_backend is not None
    configured_settings = settings or load_settings()
    if isolated_mode and settings is None:
        configured_settings = replace(configured_settings, deepseek_api_key=None)
    agent_overrides = build_agent_overrides(configured_settings)
    agent_kwargs = agent_overrides.graph_kwargs()
    mysql_repositories: MySQLRepositories | None = None
    knowledge_base: ChromaTravelKnowledgeBase | None = None
    infrastructure_status = {
        "mysql": "memory",
        "redis": "memory",
        "chroma": "disabled",
        "llm": agent_overrides.mode,
    }

    backend = checkpoint_backend
    if backend is None and configured_settings.use_external_infrastructure and configured_settings.redis_url:
        candidate = PlainRedisCheckpointBackend(configured_settings.redis_url)
        try:
            candidate.ping()
            backend = candidate
            infrastructure_status["redis"] = "ok"
        except Exception:
            candidate.close()
            if configured_settings.require_external_infrastructure:
                raise
            backend = InMemoryCheckpointBackend()
            infrastructure_status["redis"] = "fallback-memory"
    backend = backend or InMemoryCheckpointBackend()

    if not isolated_mode and configured_settings.use_external_infrastructure:
        if plan_repository is None and preference_repository is None and configured_settings.mysql_dsn:
            mysql_repositories = MySQLRepositories(configured_settings.mysql_dsn)
            plan_repository = mysql_repositories
            preference_repository = mysql_repositories
        knowledge_base = ChromaTravelKnowledgeBase(
            configured_settings.chroma_persist_directory,
            collection_prefix=configured_settings.chroma_collection,
        )

    checkpointer = backend.create()
    configured_booking_backend = booking_backend or MockJavaBookingBackend()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if mysql_repositories is not None:
            try:
                await mysql_repositories.create_schema()
                await mysql_repositories.ping()
                infrastructure_status["mysql"] = "ok"
            except Exception:
                infrastructure_status["mysql"] = "unavailable"
                if configured_settings.require_external_infrastructure:
                    raise
                application.state.travel_graph = build_travel_graph(
                    checkpointer=checkpointer,
                    booking_backend=configured_booking_backend,
                    **agent_kwargs,
                )
        if knowledge_base is not None:
            try:
                knowledge_base.seed_demo_documents()
                infrastructure_status["chroma"] = "ok"
            except Exception:
                infrastructure_status["chroma"] = "unavailable"
                if configured_settings.require_external_infrastructure:
                    raise
        application.state.infrastructure_status = infrastructure_status
        yield
        if mysql_repositories is not None:
            await mysql_repositories.close()
        if isinstance(backend, PlainRedisCheckpointBackend):
            backend.close()

    application = FastAPI(
        title="OneClick Trip Agent",
        version="0.8.0",
        description="Phase 8 MySQL, Redis checkpoint, and embedded Chroma infrastructure.",
        lifespan=lifespan,
    )
    application.state.checkpointer = checkpointer
    application.state.booking_backend = configured_booking_backend
    application.state.mysql_repositories = mysql_repositories
    application.state.knowledge_base = knowledge_base
    application.state.infrastructure_status = infrastructure_status
    application.state.llm_mode = agent_overrides.mode
    application.state.travel_graph = build_travel_graph(
        checkpointer=checkpointer,
        booking_backend=configured_booking_backend,
        plan_repository=plan_repository,
        preference_repository=preference_repository,
        **agent_kwargs,
    )
    application.include_router(router)
    return application


app = create_app()
