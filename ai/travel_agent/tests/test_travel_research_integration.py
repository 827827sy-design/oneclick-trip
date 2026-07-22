from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.domain.models import Intent, ToolDataMode, ToolName, ToolResult, TravelEntities
from app.graph.builder import build_travel_graph
from app.memory.checkpoints import InMemoryCheckpointBackend
from app.tools.contracts import ToolContext
from app.tools.mock_tools import weather_tool
from app.tools.registry import ToolRegistry
from app.tools.research import TravelResearchTool
from app.tools.selector import ToolSelector


def research_result() -> ToolResult:
    return ToolResult(
        success=True,
        source="agent-reach/exa-multi-source",
        data_mode=ToolDataMode.REALTIME,
        confidence=0.91,
        data={
            "items": [
                {
                    "title": "Official travel notice",
                    "url": "https://www.ems517.com/notice",
                    "summary": "Official safety notice",
                    "platform": "web",
                    "source_tier": "official",
                    "authority_score": 0.98,
                }
            ],
            "evidence_claims": [],
        },
    )


def test_selector_does_not_expose_research_tools_to_general_qa() -> None:
    selector = ToolSelector(
        frozenset(
            {
                ToolName.WEATHER,
                ToolName.TRAVEL_RESEARCH,
                ToolName.XIAOHONGSHU_RESEARCH,
            }
        )
    )

    assert selector.for_query(Intent.GENERAL_QA, TravelEntities()) == []


def test_travel_research_tool_remains_available_for_offline_pipeline() -> None:
    class FakeCoordinator:
        def __init__(self) -> None:
            self.arguments = None

        def research(self, query: str, **kwargs) -> ToolResult:
            self.arguments = (query, kwargs)
            return research_result()

    coordinator = FakeCoordinator()
    tool = TravelResearchTool(coordinator, limit=4, fetch_top=1)
    result = tool(
        ToolContext(
            query="Emeishan hiking plan",
            entities=TravelEntities(destination="Emeishan", days=2, people=1),
        )
    )

    assert result.success is True
    assert result.bookable is False
    assert coordinator.arguments is not None
    assert result.data["usage_policy"]["read_only"] is True


def test_general_qa_never_executes_offline_research_collectors() -> None:
    calls = 0

    def research_tool(_: ToolContext) -> ToolResult:
        nonlocal calls
        calls += 1
        return research_result()

    registry = ToolRegistry({ToolName.TRAVEL_RESEARCH: research_tool})
    result = build_travel_graph(tool_registry=registry).invoke(
        {
            "conversation_id": "research-query",
            "user_id": "research-user",
            "messages": [HumanMessage(content="What should I know before hiking?")],
        }
    )

    assert calls == 0
    assert result["selected_tools"] == []
    assert result["tool_results"] == {}


def test_planning_never_attaches_offline_research_to_user_state() -> None:
    calls = 0

    def research_tool(_: ToolContext) -> ToolResult:
        nonlocal calls
        calls += 1
        return research_result()

    registry = ToolRegistry(
        {
            ToolName.WEATHER: weather_tool,
            ToolName.TRAVEL_RESEARCH: research_tool,
        }
    )
    result = build_travel_graph(tool_registry=registry).invoke(
        {
            "conversation_id": "research-plan",
            "user_id": "research-user",
            "messages": [
                HumanMessage(
                    content="帮我规划成都三日游，一个人，总预算3000，喜欢徒步"
                )
            ],
        }
    )

    phase1 = result["phase1_research"]
    assert calls == 0
    assert result["selected_tools"] == ["weather"]
    assert "travel_research" not in result["tool_results"]
    assert phase1.research_sources == []
    assert phase1.evidence_claims == []


def test_modify_never_executes_offline_research_collectors() -> None:
    calls = 0

    def research_tool(_: ToolContext) -> ToolResult:
        nonlocal calls
        calls += 1
        return research_result()

    registry = ToolRegistry(
        {
            ToolName.WEATHER: weather_tool,
            ToolName.TRAVEL_RESEARCH: research_tool,
        }
    )
    graph = build_travel_graph(
        InMemoryCheckpointBackend().create(),
        tool_registry=registry,
    )
    config = {"configurable": {"thread_id": "research-modify"}}
    request = {"conversation_id": "research-modify", "user_id": "research-user"}
    graph.invoke(
        {
            **request,
            "messages": [
                HumanMessage(
                    content="帮我规划成都三日游，两个人，总预算5000，喜欢美食"
                )
            ],
        },
        config=config,
    )
    calls = 0

    result = graph.invoke(
        {
            **request,
            "messages": [HumanMessage(content="把第二天上午换成熊猫基地")],
        },
        config=config,
    )

    assert calls == 0
    assert "travel_research" not in result["selected_tools"]
