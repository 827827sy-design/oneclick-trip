from langchain_core.messages import HumanMessage

from app.domain.models import Intent, NextAction, ToolName, ToolResult, TravelEntities
from app.graph.builder import build_travel_graph
from app.memory.checkpoints import InMemoryCheckpointBackend
from app.tools.contracts import ToolContext
from app.tools.executor import ToolExecutor
from app.tools.mock_tools import build_mock_tool_registry, weather_tool
from app.tools.selector import ToolSelector


def test_tool_selector_filters_unknown_and_disallowed_tools() -> None:
    selected = ToolSelector().for_query(
        Intent.WEATHER_QUERY,
        TravelEntities(destination="成都"),
        requested_tools=["weather", "hotel_search", "unknown_tool"],
    )

    assert selected == [ToolName.WEATHER]


def test_weather_query_executes_only_weather_tool() -> None:
    result = build_travel_graph().invoke(
        {
            "conversation_id": "query-weather",
            "user_id": "user-weather",
            "messages": [HumanMessage(content="成都明天天气怎么样？")],
        }
    )

    assert result["selected_tools"] == ["weather"]
    assert set(result["tool_results"]) == {"weather"}
    assert result["tool_attempts"] == {"weather": 1}
    assert "成都预计多云" in result["messages"][-1].content


def test_planning_uses_weather_interface_and_ai_research_stages() -> None:
    result = build_travel_graph().invoke(
        {
            "conversation_id": "planning-tools",
            "user_id": "user-planning-tools",
            "messages": [
                HumanMessage(content="帮我规划成都三日游，两个人，总预算5000，喜欢美食")
            ],
        }
    )

    assert result["selected_tools"] == ["weather"]
    assert set(result["tool_results"]) == {"weather"}
    assert result["phase1_research"].data_mode == "OFFLINE_FALLBACK"
    assert result["candidate_selection"] is not None
    assert result["phase2_research"].data_mode == "OFFLINE_FALLBACK"
    assert result["plan_draft"] is not None


def test_retryable_tool_is_retried_at_most_once() -> None:
    registry = build_mock_tool_registry()
    calls = 0

    def flaky_weather(context: ToolContext) -> ToolResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            return ToolResult(
                success=False,
                data={"message": "temporary timeout"},
                error_code="TIMEOUT",
                retryable=True,
            )
        return weather_tool(context)

    registry.register(ToolName.WEATHER, flaky_weather)
    outcome = ToolExecutor(registry).execute(
        ToolName.WEATHER,
        ToolContext(entities=TravelEntities(destination="成都")),
    )

    assert calls == 2
    assert outcome.attempts == 2
    assert outcome.result.success is True
    assert len(outcome.errors) == 1


def test_failed_weather_uses_fallback_after_one_retry() -> None:
    registry = build_mock_tool_registry()
    calls = 0

    def unavailable_weather(_: ToolContext) -> ToolResult:
        nonlocal calls
        calls += 1
        return ToolResult(
            success=False,
            data={"message": "provider unavailable"},
            error_code="UPSTREAM_UNAVAILABLE",
            retryable=True,
        )

    registry.register(ToolName.WEATHER, unavailable_weather)
    outcome = ToolExecutor(registry).execute(
        ToolName.WEATHER,
        ToolContext(entities=TravelEntities(destination="成都")),
    )

    assert calls == 2
    assert outcome.attempts == 2
    assert len(outcome.errors) == 2
    assert outcome.result.success is True
    assert outcome.result.error_code == "FALLBACK_USED"
    assert outcome.abort_requested is False


def test_planning_ignores_non_weather_mock_registry_entries() -> None:
    registry = build_mock_tool_registry()

    def unavailable_poi(_: ToolContext) -> ToolResult:
        return ToolResult(
            success=False,
            data={"message": "poi index unavailable"},
            error_code="POI_UNAVAILABLE",
            retryable=False,
        )

    registry.register(ToolName.POI_SEARCH, unavailable_poi)
    result = build_travel_graph(tool_registry=registry).invoke(
        {
            "conversation_id": "planning-abort",
            "user_id": "user-planning-abort",
            "messages": [HumanMessage(content="帮我规划成都三日游，两个人，总预算5000")],
        }
    )

    assert result["next_action"] == NextAction.COMPLETE
    assert result.get("plan_draft") is not None
    assert result["selected_tools"] == ["weather"]
    assert set(result["tool_results"]) == {"weather"}
    assert result["tool_errors"] == []


def test_new_query_clears_previous_turn_tool_state() -> None:
    graph = build_travel_graph(InMemoryCheckpointBackend().create())
    config = {"configurable": {"thread_id": "query-reset"}}
    graph.invoke(
        {
            "conversation_id": "query-reset",
            "user_id": "user-reset",
            "messages": [HumanMessage(content="成都明天天气怎么样？")],
        },
        config=config,
    )
    result = graph.invoke(
        {
            "conversation_id": "query-reset",
            "user_id": "user-reset",
            "messages": [HumanMessage(content="成都酒店推荐")],
        },
        config=config,
    )

    assert result["selected_tools"] == []
    assert result["tool_results"] == {}
    assert result["tool_attempts"] == {}
    assert "没有使用 Mock" in result["messages"][-1].content
