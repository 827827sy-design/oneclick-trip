import asyncio
from pathlib import Path

from app.config import Settings
from app.domain.models import Intent, TravelEntities
from app.llm import build_agent_overrides
from app.llm.factory import _FallbackQueryPresenterAgent


def settings(api_key: str | None) -> Settings:
    return Settings(
        app_env="test",
        infra_mode="memory",
        mysql_dsn=None,
        redis_url=None,
        chroma_persist_directory=Path(".data/test-chroma"),
        chroma_collection="test",
        deepseek_api_key=api_key,
        deepseek_base_url="https://api.deepseek.com",
        deepseek_flash_model="deepseek-v4-flash",
        deepseek_pro_model="deepseek-v4-pro",
        business_backend="java",
        java_backend_base_url="http://127.0.0.1:8080",
        java_internal_service_secret="test-internal-secret",
    )


def test_missing_key_keeps_rule_agents() -> None:
    overrides = build_agent_overrides(settings(None))

    assert overrides.mode == "rules"
    assert overrides.graph_kwargs() == {}


def test_configured_key_builds_deepseek_agent_overrides_without_network_call() -> None:
    overrides = build_agent_overrides(settings("test-key-not-sent"))

    assert overrides.mode == "deepseek"
    assert set(overrides.graph_kwargs()) == {
        "intent_agent",
        "clarification_agent",
        "memory_candidate_agent",
        "candidate_selector",
        "query_presenter",
        "phase1_research_agent",
        "phase2_research_agent",
        "direct_modify_agent",
        "planner_agent",
        "plan_presenter",
        "reviewer_agent",
        "revision_agent",
        "modify_analyzer_agent",
    }


def test_query_presenter_fallback_preserves_conversation_context() -> None:
    class FailingPresenter:
        async def apresent(self, *args):
            raise ValueError("model unavailable")

    class RecordingPresenter:
        def __init__(self) -> None:
            self.context = None

        async def apresent(
            self,
            query,
            intent,
            entities,
            results,
            conversation_context=None,
        ):
            self.context = conversation_context
            return "fallback reply"

    fallback = RecordingPresenter()
    agent = _FallbackQueryPresenterAgent(FailingPresenter(), fallback)

    reply = asyncio.run(
        agent.apresent(
            "成都天气怎么样？",
            Intent.WEATHER_QUERY,
            TravelEntities(destination="成都"),
            {},
            ["用户：我明天出发"],
        )
    )

    assert reply == "fallback reply"
    assert fallback.context == ["用户：我明天出发"]
