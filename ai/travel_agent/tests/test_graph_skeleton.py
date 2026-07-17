from langchain_core.messages import HumanMessage

from app.domain.models import Intent, NextAction
from app.graph.builder import build_travel_graph
from app.memory.checkpoints import InMemoryCheckpointBackend


def test_phase_one_graph_runs_and_persists_thread_state() -> None:
    graph = build_travel_graph(InMemoryCheckpointBackend().create())
    config = {"configurable": {"thread_id": "conversation-1"}}

    result = graph.invoke(
        {
            "conversation_id": "conversation-1",
            "user_id": "user-1",
            "messages": [HumanMessage(content="帮我规划成都三日游")],
        },
        config=config,
    )

    assert result["intent"] == Intent.TRIP_PLAN
    assert result["next_action"] == NextAction.ASK_USER
    assert result["missing_fields"] == ["people", "budget"]
    assert graph.get_state(config).values["conversation_id"] == "conversation-1"


def test_same_thread_appends_messages_through_checkpoint() -> None:
    graph = build_travel_graph(InMemoryCheckpointBackend().create())
    config = {"configurable": {"thread_id": "conversation-2"}}

    for content in ["成都有什么景点？", "那明天天气呢？"]:
        graph.invoke(
            {
                "conversation_id": "conversation-2",
                "user_id": "user-2",
                "messages": [HumanMessage(content=content)],
            },
            config=config,
        )

    snapshot = graph.get_state(config)
    assert len(snapshot.values["messages"]) == 4
    assert snapshot.values["intent"] == Intent.WEATHER_QUERY
    assert snapshot.values["entities"].destination == "成都"
    assert snapshot.values["next_action"] == NextAction.QUERY_FLOW
