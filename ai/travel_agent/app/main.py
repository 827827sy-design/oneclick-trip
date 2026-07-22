from contextlib import asynccontextmanager
from dataclasses import replace
from typing import AsyncIterator

from fastapi import FastAPI

from app.api.routes import router
from app.booking import BookingBackend, JavaBookingBackend, MockJavaBookingBackend
from app.config import Settings, load_settings
from app.database import (
    JavaBusinessRepositories,
    MySQLRepositories,
    PlanRepository,
    UserPreferenceRepository,
)
from app.graph.builder import build_travel_graph
from app.knowledge_pipeline import JsonKnowledgeBatchRepository, KnowledgePipelineService
from app.llm import build_agent_overrides
from app.memory.checkpoints import (
    CheckpointBackend,
    InMemoryCheckpointBackend,
    PlainRedisCheckpointBackend,
)
from app.vectorstore import (
    BgeSmallZhV15EmbeddingFunction,
    ChromaTravelKnowledgeBase,
    HashEmbeddingFunction,
)
from app.tools.factory import build_knowledge_research_registry, build_live_tool_registry
from app.tools.mock_tools import build_allowed_demo_registry


def create_app(
    checkpoint_backend: CheckpointBackend | None = None,
    booking_backend: BookingBackend | None = None,
    plan_repository: PlanRepository | None = None,
    preference_repository: UserPreferenceRepository | None = None,
    knowledge_pipeline_service: KnowledgePipelineService | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    isolated_mode = checkpoint_backend is not None
    configured_settings = settings or load_settings()
    if isolated_mode and settings is None:
        configured_settings = replace(configured_settings, deepseek_api_key=None)
    agent_overrides = build_agent_overrides(configured_settings)
    agent_kwargs = agent_overrides.graph_kwargs()
    mysql_repositories: MySQLRepositories | None = None
    java_repositories: JavaBusinessRepositories | None = None
    java_booking_backend: JavaBookingBackend | None = None
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
        if (
            configured_settings.business_backend == "java"
            and plan_repository is None
            and preference_repository is None
        ):
            java_repositories = JavaBusinessRepositories(
                configured_settings.java_backend_base_url,
                configured_settings.java_internal_service_secret,
                timeout_seconds=configured_settings.tool_http_timeout_seconds,
            )
            plan_repository = java_repositories
            preference_repository = java_repositories
            java_booking_backend = JavaBookingBackend(
                configured_settings.java_backend_base_url,
                configured_settings.java_internal_service_secret,
                timeout_seconds=configured_settings.tool_http_timeout_seconds,
                redis_url=configured_settings.redis_url,
            )
            infrastructure_status["mysql"] = "java-owned"
        elif plan_repository is None and preference_repository is None and configured_settings.mysql_dsn:
            mysql_repositories = MySQLRepositories(configured_settings.mysql_dsn)
            plan_repository = mysql_repositories
            preference_repository = mysql_repositories
        if configured_settings.embedding_backend == "bge-small-zh-v1.5":
            embedding_function = BgeSmallZhV15EmbeddingFunction(
                configured_settings.bge_model_directory,
                auto_download=configured_settings.bge_auto_download,
            )
        elif configured_settings.embedding_backend == "hash":
            embedding_function = HashEmbeddingFunction()
        else:
            raise ValueError(
                f"Unsupported embedding backend: {configured_settings.embedding_backend}"
            )
        knowledge_base = ChromaTravelKnowledgeBase(
            configured_settings.chroma_persist_directory,
            collection_prefix=configured_settings.chroma_collection,
            embedding_function=embedding_function,
            server_url=configured_settings.chroma_server_url,
        )
        knowledge_pipeline_service = knowledge_pipeline_service or KnowledgePipelineService(
            knowledge_base,
            research_registry=build_knowledge_research_registry(configured_settings),
            repository=JsonKnowledgeBatchRepository(
                configured_settings.chroma_persist_directory.parent / "knowledge_batches.json"
            ),
        )

    checkpointer = backend.create()
    configured_booking_backend = (
        booking_backend or java_booking_backend or MockJavaBookingBackend()
    )
    configured_tool_registry = (
        build_allowed_demo_registry()
        if isolated_mode
        else build_live_tool_registry(configured_settings, knowledge_base)
    )

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
                    tool_registry=configured_tool_registry,
                    **agent_kwargs,
                )
        if knowledge_base is not None:
            try:
                knowledge_base.remove_documents_by_source("demo-seed")
                infrastructure_status["chroma"] = "ok"
            except Exception:
                infrastructure_status["chroma"] = "unavailable"
                if configured_settings.require_external_infrastructure:
                    raise
        application.state.infrastructure_status = infrastructure_status
        yield
        if mysql_repositories is not None:
            await mysql_repositories.close()
        if java_repositories is not None:
            await java_repositories.close()
        if java_booking_backend is not None:
            java_booking_backend.close()
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
    application.state.java_repositories = java_repositories
    application.state.knowledge_base = knowledge_base
    application.state.knowledge_pipeline = knowledge_pipeline_service
    application.state.infrastructure_status = infrastructure_status
    application.state.llm_mode = agent_overrides.mode
    application.state.agent_jobs = {}
    application.state.agent_job_tasks = {}
    application.state.travel_graph = build_travel_graph(
        checkpointer=checkpointer,
        booking_backend=configured_booking_backend,
        plan_repository=plan_repository,
        preference_repository=preference_repository,
        tool_registry=configured_tool_registry,
        **agent_kwargs,
    )
    application.include_router(router)
    return application


app = create_app()
