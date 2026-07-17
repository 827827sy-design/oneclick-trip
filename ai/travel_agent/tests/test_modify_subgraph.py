from decimal import Decimal

from langchain_core.messages import HumanMessage

from app.domain.models import NextAction
from app.graph.builder import build_travel_graph
from app.memory.checkpoints import InMemoryCheckpointBackend


INITIAL_PLAN = "帮我规划成都三日游，两个人，总预算5000，喜欢美食"


def build_versioned_plan(conversation_id: str):
    graph = build_travel_graph(InMemoryCheckpointBackend().create())
    config = {"configurable": {"thread_id": conversation_id}}
    first = graph.invoke(
        {
            "conversation_id": conversation_id,
            "user_id": f"user-{conversation_id}",
            "messages": [HumanMessage(content=INITIAL_PLAN)],
        },
        config=config,
    )
    return graph, config, first


def modify(graph, config, message: str):
    return graph.invoke(
        {
            "conversation_id": config["configurable"]["thread_id"],
            "user_id": f"user-{config['configurable']['thread_id']}",
            "messages": [HumanMessage(content=message)],
        },
        config=config,
    )


def test_replace_poi_uses_direct_model_path_and_saves_v2() -> None:
    graph, config, first = build_versioned_plan("modify-replace")
    result = modify(graph, config, "把第二天上午换成熊猫基地")

    assert first["plan_version"] == 1
    assert result["plan_saved"] is True
    assert result["plan_version"] == 2
    assert result["current_plan"].plan_id == first["current_plan"].plan_id
    assert result["selected_tools"] == []
    assert result["tool_results"] == {}
    assert result["current_plan"].days[1].items[0].name == "熊猫基地"
    all_location_ids = [
        item.location_id
        for day in result["current_plan"].days
        for item in day.items
    ]
    assert len(all_location_ids) == len(set(all_location_ids))


def test_budget_change_uses_no_tools_and_saves_new_version() -> None:
    graph, config, _ = build_versioned_plan("modify-budget")
    result = modify(graph, config, "预算降低1000")

    assert result["selected_tools"] == []
    assert result["tool_results"] == {}
    assert result["entities"].budget == Decimal("4000")
    assert result["plan_saved"] is True
    assert result["plan_version"] == 2


def test_invalid_low_budget_keeps_v1_after_two_revisions() -> None:
    graph, config, first = build_versioned_plan("modify-budget-fail")
    result = modify(graph, config, "预算降低4500")

    assert result["revision_count"] == 2
    assert result["plan_saved"] is False
    assert result["validation_exhausted"] is True
    assert result["plan_draft"] is None
    assert result["current_plan"] == first["current_plan"]
    assert result["plan_version"] == 1
    assert "BUDGET_EXCEEDED" in result["planning_errors"]


def test_swap_days_skips_poi_search_but_refreshes_dependencies() -> None:
    graph, config, first = build_versioned_plan("modify-swap")
    first_day_names = [item.name for item in first["current_plan"].days[0].items]
    second_day_names = [item.name for item in first["current_plan"].days[1].items]
    result = modify(graph, config, "把第一天和第二天交换")

    assert result["next_action"] is NextAction.COMPLETE
    assert result["selected_tools"] == []
    assert [item.name for item in result["current_plan"].days[0].items] == second_day_names
    assert [item.name for item in result["current_plan"].days[1].items] == first_day_names
    assert result["plan_version"] == 2


def test_named_replacement_is_applied_without_mock_candidate_lookup() -> None:
    graph, config, first = build_versioned_plan("modify-unknown")
    result = modify(graph, config, "把第二天上午换成月球基地")

    assert result["plan_saved"] is True
    assert result["next_action"] is NextAction.COMPLETE
    assert result["plan_version"] == 2
    assert result["selected_tools"] == []
    assert result["current_plan"].days[1].items[0].name == "月球基地"
